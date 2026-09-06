from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


def _bool(name: str, default: bool) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    normalized = value.strip().lower()
    if normalized in {"1", "true", "yes", "on"}:
        return True
    if normalized in {"0", "false", "no", "off"}:
        return False
    raise ValueError(f"{name} must be a boolean value")


def _int(name: str, default: int) -> int:
    value = os.getenv(name)
    return int(value) if value is not None else default


def _float(name: str, default: float) -> float:
    value = os.getenv(name)
    return float(value) if value is not None else default


@dataclass(frozen=True)
class Settings:
    comfy_host: str
    comfy_port: int
    model_root: Path
    output_root: Path
    catalog_path: Path
    manifest_path: Path
    unet_name: str
    text_encoder_name: str
    vae_name: str
    model_shift: float
    max_megapixels: float
    max_total_megapixels: float
    max_batch_size: int
    max_loras: int
    max_prompt_chars: int
    request_timeout_seconds: int
    poll_interval_seconds: float
    output_mode: str
    clean_outputs: bool
    debug_errors: bool

    @property
    def comfy_base_url(self) -> str:
        return f"http://{self.comfy_host}:{self.comfy_port}"

    @property
    def lora_root(self) -> Path:
        return self.model_root / "loras"

    @classmethod
    def from_env(cls) -> "Settings":
        output_mode = os.getenv("OUTPUT_MODE", "auto").strip().lower()
        if output_mode not in {"auto", "base64", "s3", "path"}:
            raise ValueError("OUTPUT_MODE must be one of: auto, base64, s3, path")
        return cls(
            comfy_host=os.getenv("COMFY_HOST", "127.0.0.1"),
            comfy_port=_int("COMFY_PORT", 8188),
            model_root=Path(os.getenv("MODEL_ROOT", "/runpod-volume/models")),
            output_root=Path(os.getenv("OUTPUT_ROOT", "/tmp/krea-comfy-output")),
            catalog_path=Path(
                os.getenv("LORA_CATALOG", "/opt/krea/config/lora_catalog.json")
            ),
            manifest_path=Path(
                os.getenv("MODEL_MANIFEST", "/opt/krea/config/models.json")
            ),
            unet_name=os.getenv("KREA_UNET", "krea2_turbo_fp8_scaled.safetensors"),
            text_encoder_name=os.getenv(
                "KREA_TEXT_ENCODER", "qwen3vl_4b_fp8_scaled.safetensors"
            ),
            vae_name=os.getenv("KREA_VAE", "qwen_image_vae.safetensors"),
            model_shift=_float("KREA_MODEL_SHIFT", 3.0),
            max_megapixels=_float("MAX_MEGAPIXELS", 2.10),
            max_total_megapixels=_float("MAX_TOTAL_MEGAPIXELS", 2.10),
            max_batch_size=_int("MAX_BATCH_SIZE", 2),
            max_loras=_int("MAX_LORAS", 4),
            max_prompt_chars=_int("MAX_PROMPT_CHARS", 6000),
            request_timeout_seconds=_int("JOB_TIMEOUT_SECONDS", 900),
            poll_interval_seconds=_float("COMFY_POLL_SECONDS", 0.35),
            output_mode=output_mode,
            clean_outputs=_bool("CLEAN_OUTPUTS", True),
            debug_errors=_bool("DEBUG_ERRORS", False),
        )
