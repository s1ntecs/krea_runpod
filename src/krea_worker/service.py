from __future__ import annotations

import json
import logging
import threading
import time
from pathlib import Path, PurePosixPath
from typing import Any

from .comfy_client import ComfyClient
from .errors import InputError, ModelFileError
from .lora_registry import LoraRegistry
from .output import OutputManager
from .request import GenerationRequest
from .settings import Settings
from .workflow import build_edit_workflow, build_workflow

logger = logging.getLogger(__name__)

_GENERATION_LOCK = threading.Lock()
_FALLBACK_MIN_MODEL_BYTES = 1024 * 1024


class KreaService:
    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or Settings.from_env()
        self.registry = LoraRegistry(
            self.settings.lora_root,
            self.settings.catalog_path,
            self.settings.max_loras,
        )
        self.client = ComfyClient(
            self.settings.comfy_base_url,
            self.settings.output_root,
            self.settings.request_timeout_seconds,
            self.settings.poll_interval_seconds,
        )
        self.output = OutputManager(
            self.settings.output_mode, self.settings.clean_outputs
        )

    @staticmethod
    def _safe_relative(category: str, filename: str) -> str:
        normalized = filename.replace("\\", "/").strip()
        child = PurePosixPath(normalized)
        if not normalized or child.is_absolute() or ".." in child.parts:
            raise ModelFileError(f"Unsafe configured model filename: {filename!r}")
        return (PurePosixPath(category) / child).as_posix()

    def _manifest_index(self) -> dict[str, dict[str, Any]]:
        path = self.settings.manifest_path
        if not path.is_file():
            raise ModelFileError(
                "Model manifest is missing",
                details={"manifest_path": str(path)},
            )
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise ModelFileError(
                "Model manifest is not valid JSON",
                details={"manifest_path": str(path)},
            ) from exc
        artifacts = data.get("artifacts")
        if not isinstance(artifacts, list):
            raise ModelFileError("Model manifest field 'artifacts' must be an array")

        index: dict[str, dict[str, Any]] = {}
        for artifact in artifacts:
            if not isinstance(artifact, dict):
                continue
            target = artifact.get("target")
            if not isinstance(target, str) or not target.strip():
                continue
            normalized = target.replace("\\", "/").strip()
            posix = PurePosixPath(normalized)
            if posix.is_absolute() or ".." in posix.parts:
                raise ModelFileError(
                    "Unsafe target in model manifest",
                    details={"target": target},
                )
            index[posix.as_posix().lower()] = artifact
        return index

    def model_file_specs(self) -> dict[str, dict[str, Any]]:
        manifest = self._manifest_index()
        configured = {
            "diffusion_model": self._safe_relative(
                "diffusion_models", self.settings.unet_name
            ),
            "text_encoder": self._safe_relative(
                "text_encoders", self.settings.text_encoder_name
            ),
            "vae": self._safe_relative("vae", self.settings.vae_name),
        }
        root = self.settings.model_root.resolve()
        result: dict[str, dict[str, Any]] = {}
        for logical_name, relative in configured.items():
            target = (root / Path(*PurePosixPath(relative).parts)).resolve()
            if root not in target.parents:
                raise ModelFileError(
                    "Configured model path escapes MODEL_ROOT",
                    details={"relative_path": relative},
                )
            artifact = manifest.get(relative.lower(), {})
            result[logical_name] = {
                "path": target,
                "relative_path": relative,
                "artifact_id": artifact.get("id"),
                "minimum_bytes": int(
                    artifact.get("min_bytes", _FALLBACK_MIN_MODEL_BYTES)
                ),
                "sha256": artifact.get("sha256"),
            }
        return result

    def model_files(self) -> dict[str, Path]:
        return {
            name: spec["path"] for name, spec in self.model_file_specs().items()
        }

    def _model_status(self) -> dict[str, dict[str, Any]]:
        status: dict[str, dict[str, Any]] = {}
        for name, spec in self.model_file_specs().items():
            path: Path = spec["path"]
            exists = path.is_file()
            size = path.stat().st_size if exists else 0
            minimum = int(spec["minimum_bytes"])
            status[name] = {
                "path": str(path),
                "relative_path": spec["relative_path"],
                "artifact_id": spec["artifact_id"],
                "exists": exists,
                "size_bytes": size if exists else None,
                "minimum_bytes": minimum,
                "valid": exists and size >= minimum,
                "expected_sha256": spec["sha256"],
            }
        return status

    def validate_model_files(self) -> dict[str, dict[str, Any]]:
        status = self._model_status()
        if not all(item["valid"] for item in status.values()):
            raise ModelFileError(
                "Required Krea 2 model files are missing or incomplete",
                details={
                    "files": status,
                    "storage_guide": "docs/STORAGE_SETUP_RU.md",
                },
            )
        return status

    def health(self) -> dict:
        try:
            files = self._model_status()
            models_ok = all(item["valid"] for item in files.values())
        except ModelFileError as exc:
            files = {"manifest": exc.as_dict()}
            models_ok = False

        try:
            self.client.wait_ready(timeout=3)
            response = self.client.session.get(
                f"{self.settings.comfy_base_url}/system_stats", timeout=5
            )
            response.raise_for_status()
            comfy = {"ready": True, "system_stats": response.json()}
        except Exception as exc:
            comfy = {"ready": False, "error": str(exc)}
        return {
            "ok": comfy.get("ready", False) and models_ok,
            "comfyui": comfy,
            "models": files,
            "model_root": str(self.settings.model_root),
            "loras": self.registry.list_available(),
        }

    @staticmethod
    def _input_options(info: dict, node_name: str, input_name: str) -> list[str]:
        try:
            spec = info[node_name]["input"]["required"][input_name]
        except (KeyError, TypeError):
            return []
        if isinstance(spec, (list, tuple)) and spec and isinstance(spec[0], list):
            return [str(item) for item in spec[0]]
        return []

    def validate_runtime(self) -> dict:
        files = self.validate_model_files()
        self.client.wait_ready(timeout=30)
        required_nodes = [
            "UNETLoader",
            "CLIPLoader",
            "VAELoader",
            "LoraLoaderModelOnly",
            "ModelSamplingAuraFlow",
            "EmptySD3LatentImage",
            "KSampler",
            "VAEDecode",
            "SaveImage",
        ]
        info = self.client.object_info()
        missing_nodes = [name for name in required_nodes if name not in info]
        if missing_nodes:
            raise ModelFileError(
                "ComfyUI is missing required nodes",
                details={"missing_nodes": missing_nodes},
            )

        expected_models = {
            "UNETLoader.unet_name": (
                self.settings.unet_name,
                self._input_options(info, "UNETLoader", "unet_name"),
            ),
            "CLIPLoader.clip_name": (
                self.settings.text_encoder_name,
                self._input_options(info, "CLIPLoader", "clip_name"),
            ),
            "VAELoader.vae_name": (
                self.settings.vae_name,
                self._input_options(info, "VAELoader", "vae_name"),
            ),
        }
        not_visible = {
            key: {"expected": expected, "available_count": len(options)}
            for key, (expected, options) in expected_models.items()
            if options and expected not in options
        }
        if not_visible:
            raise ModelFileError(
                "Model files exist but are not visible to ComfyUI",
                details={
                    "not_visible": not_visible,
                    "hint": "Check MODEL_ROOT and extra model paths",
                },
            )
        return {
            "ok": True,
            "required_nodes": required_nodes,
            "models": files,
        }

    def generate(self, payload: dict, job_id: str) -> dict:
        started = time.monotonic()
        request = GenerationRequest.parse(payload, self.settings)
        self.validate_model_files()
        self._checkpoint_file(request.checkpoint)
        loras = self.registry.resolve(request.loras)
        safe_job = "".join(ch for ch in job_id if ch.isalnum() or ch in "-_")[-24:]
        prefix = (
            f"{request.filename_prefix}_{safe_job}"
            if safe_job
            else request.filename_prefix
        )
        workflow_result = build_workflow(request, loras, self.settings, prefix)

        with _GENERATION_LOCK:
            self.client.wait_ready(timeout=30)
            prompt_id, paths, _history = self.client.run(
                workflow_result.workflow, workflow_result.output_node_id
            )
            output_mode, images = self.output.publish(
                paths, request.output_mode, job_id
            )

        elapsed = time.monotonic() - started
        logger.info(
            "Generated %d image(s) in %.2fs; prompt_id=%s loras=%s",
            len(images),
            elapsed,
            prompt_id,
            [lora.file for lora in loras],
        )
        head: dict[str, Any] = (
            {"images_base64": [item["base64"] for item in images]}
            if output_mode == "base64"
            else {"images": images}
        )
        return {
            **head,
            "time": round(elapsed, 2),
            "steps": request.steps,
            "seed": request.seed,
            "ok": True,
            "action": "generate",
            "prompt_id": prompt_id,
            "width": request.width,
            "height": request.height,
            "num_images": len(images),
            "cfg": request.cfg,
            "checkpoint": request.checkpoint,
            "sampler_name": request.sampler_name,
            "scheduler": request.scheduler,
            "loras": [lora.public_dict() for lora in loras],
            "final_prompt": workflow_result.final_prompt,
            "output_mode": output_mode,
        }

    def _checkpoint_file(self, checkpoint: str) -> None:
        """Raw ships as an optional manifest group, so it may simply be absent."""
        if checkpoint != "raw":
            return
        name = self.settings.raw_unet_name
        path = self.settings.model_root / "diffusion_models" / name
        if not path.is_file() or path.stat().st_size < _FALLBACK_MIN_MODEL_BYTES:
            raise ModelFileError(
                "The Krea 2 Raw checkpoint is missing; the 'raw' group of the "
                "model manifest is not installed",
                details={"expected_path": str(path), "checkpoint": name},
            )

    def _edit_lora_file(self) -> str:
        """Ensures the identity-edit LoRA is on disk before we build an edit graph."""
        name = self.settings.edit_lora_name
        path = self.settings.lora_root / name
        if not path.is_file() or path.stat().st_size < _FALLBACK_MIN_MODEL_BYTES:
            raise ModelFileError(
                "Krea 2 Identity Edit LoRA is missing or incomplete; "
                "the 'edit' group of the model manifest is not installed",
                details={"expected_path": str(path), "lora": name},
            )
        return name

    def edit(self, payload: dict, job_id: str) -> dict:
        started = time.monotonic()
        request = GenerationRequest.parse_edit(payload, self.settings)
        self.validate_model_files()
        self._checkpoint_file(request.checkpoint)
        edit_lora = self._edit_lora_file()
        loras = self.registry.resolve(request.loras)
        safe_job = "".join(ch for ch in job_id if ch.isalnum() or ch in "-_")[-24:]
        prefix = (
            f"{request.filename_prefix}_{safe_job}"
            if safe_job
            else request.filename_prefix
        )

        with _GENERATION_LOCK:
            self.client.wait_ready(timeout=30)
            names = [
                self.client.upload_image(data, f"{prefix}_ref{index}.png")
                for index, data in enumerate(request.images)
            ]
            mask_name = None
            if request.ref_boost_mask is not None:
                mask_name = self.client.upload_image(
                    request.ref_boost_mask, f"{prefix}_mask.png"
                )
            workflow_result = build_edit_workflow(
                request, loras, self.settings, prefix, names, edit_lora, mask_name
            )
            prompt_id, paths, _history = self.client.run(
                workflow_result.workflow, workflow_result.output_node_id
            )
            output_mode, images = self.output.publish(
                paths, request.output_mode, job_id
            )

        elapsed = time.monotonic() - started
        logger.info(
            "Edited %d image(s) in %.2fs; prompt_id=%s refs=%d loras=%s",
            len(images),
            elapsed,
            prompt_id,
            len(request.images),
            [lora.file for lora in loras],
        )
        head: dict[str, Any] = (
            {"images_base64": [item["base64"] for item in images]}
            if output_mode == "base64"
            else {"images": images}
        )
        return {
            **head,
            "time": round(elapsed, 2),
            "steps": request.steps,
            "seed": request.seed,
            "ok": True,
            "action": "edit",
            "prompt_id": prompt_id,
            "width": request.width,
            "height": request.height,
            "num_images": len(images),
            "cfg": request.cfg,
            "checkpoint": request.checkpoint,
            "sampler_name": request.sampler_name,
            "scheduler": request.scheduler,
            "grounding_px": request.grounding_px,
            "ref_boost": request.ref_boost,
            "system_prompt": request.system_prompt,
            "reference_images": len(request.images),
            "ref_boost_mask": request.ref_boost_mask is not None,
            "edit_lora": edit_lora,
            "loras": [lora.public_dict() for lora in loras],
            "final_prompt": workflow_result.final_prompt,
            "output_mode": output_mode,
        }

    def process(self, payload: dict, job_id: str) -> dict:
        if not isinstance(payload, dict):
            raise InputError("input must be a JSON object")
        action = str(payload.get("action", "generate")).strip().lower()
        if action == "generate":
            return self.generate(payload, job_id)
        if action == "edit":
            return self.edit(payload, job_id)
        if action in {"list_loras", "loras"}:
            return {
                "ok": True,
                "action": "list_loras",
                "loras": self.registry.list_available(),
            }
        if action == "health":
            return {"action": "health", **self.health()}
        if action in {"validate", "validate_runtime"}:
            return {"action": "validate_runtime", **self.validate_runtime()}
        raise InputError(
            f"Unknown action '{action}'",
            details={
                "allowed": [
                    "generate",
                    "edit",
                    "list_loras",
                    "health",
                    "validate_runtime",
                ]
            },
        )
