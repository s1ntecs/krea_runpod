from __future__ import annotations

import logging
import time
import uuid
from pathlib import Path
from typing import Any

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from .errors import ComfyError, TimeoutError

logger = logging.getLogger(__name__)


class ComfyClient:
    def __init__(
        self,
        base_url: str,
        output_root: Path,
        timeout_seconds: int,
        poll_interval_seconds: float,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.output_root = output_root
        self.timeout_seconds = timeout_seconds
        self.poll_interval_seconds = poll_interval_seconds
        self.session = requests.Session()
        retry = Retry(
            total=4,
            connect=4,
            read=2,
            backoff_factor=0.4,
            status_forcelist=(429, 500, 502, 503, 504),
            allowed_methods=frozenset({"GET"}),
        )
        self.session.mount("http://", HTTPAdapter(max_retries=retry))

    def wait_ready(self, timeout: float = 120.0) -> None:
        deadline = time.monotonic() + timeout
        last_error = "unknown"
        while time.monotonic() < deadline:
            try:
                response = self.session.get(f"{self.base_url}/system_stats", timeout=5)
                if response.ok:
                    return
                last_error = f"HTTP {response.status_code}"
            except requests.RequestException as exc:
                last_error = str(exc)
            time.sleep(0.5)
        raise ComfyError(f"ComfyUI did not become ready: {last_error}")

    def upload_image(self, data: bytes, filename: str) -> str:
        """Uploads an image into ComfyUI's input dir and returns the name LoadImage expects."""
        try:
            response = self.session.post(
                f"{self.base_url}/upload/image",
                files={"image": (filename, data, "image/png")},
                data={"type": "input", "overwrite": "false"},
                timeout=120,
            )
            response.raise_for_status()
            payload = response.json()
        except requests.RequestException as exc:
            raise ComfyError(f"Could not upload input image to ComfyUI: {exc}") from exc
        name = payload.get("name") if isinstance(payload, dict) else None
        if not isinstance(name, str) or not name:
            raise ComfyError("ComfyUI did not return a name for the uploaded image")
        subfolder = payload.get("subfolder") or ""
        return f"{subfolder}/{name}" if subfolder else name

    def object_info(self, node: str | None = None) -> dict:
        path = f"/object_info/{node}" if node else "/object_info"
        try:
            response = self.session.get(f"{self.base_url}{path}", timeout=30)
            response.raise_for_status()
            data = response.json()
        except (requests.RequestException, ValueError) as exc:
            raise ComfyError(f"Cannot query ComfyUI object_info: {exc}") from exc
        return data

    def queue(self, workflow: dict) -> tuple[str, str]:
        client_id = str(uuid.uuid4())
        try:
            response = self.session.post(
                f"{self.base_url}/prompt",
                json={"prompt": workflow, "client_id": client_id},
                timeout=60,
            )
        except requests.RequestException as exc:
            raise ComfyError(f"Cannot submit workflow to ComfyUI: {exc}") from exc

        try:
            payload = response.json()
        except ValueError as exc:
            raise ComfyError(
                f"ComfyUI returned non-JSON response: HTTP {response.status_code}"
            ) from exc
        if not response.ok or "prompt_id" not in payload:
            raise ComfyError(
                "ComfyUI rejected the workflow",
                details={
                    "http_status": response.status_code,
                    "response": payload,
                },
            )
        return str(payload["prompt_id"]), client_id

    @staticmethod
    def _history_error(item: dict) -> dict | None:
        status = item.get("status") or {}
        if status.get("status_str") == "error":
            return {"status": status}
        for message in status.get("messages", []):
            if isinstance(message, list) and message and message[0] in {
                "execution_error",
                "execution_interrupted",
            }:
                return {"message": message}
        return None

    def wait_for_result(self, prompt_id: str) -> dict:
        deadline = time.monotonic() + self.timeout_seconds
        while time.monotonic() < deadline:
            try:
                response = self.session.get(
                    f"{self.base_url}/history/{prompt_id}", timeout=20
                )
                response.raise_for_status()
                history = response.json()
            except (requests.RequestException, ValueError) as exc:
                logger.warning("History poll failed for %s: %s", prompt_id, exc)
                time.sleep(self.poll_interval_seconds)
                continue

            item = history.get(prompt_id)
            if item:
                error = self._history_error(item)
                if error:
                    raise ComfyError("ComfyUI execution failed", details=error)
                status = item.get("status") or {}
                if status.get("completed") or item.get("outputs"):
                    return item
            time.sleep(self.poll_interval_seconds)

        try:
            self.session.post(f"{self.base_url}/interrupt", timeout=10)
        except requests.RequestException:
            pass
        raise TimeoutError(
            f"Generation exceeded {self.timeout_seconds} seconds",
            details={"prompt_id": prompt_id},
        )

    @staticmethod
    def output_images(history_item: dict, output_node_id: str) -> list[dict]:
        outputs = history_item.get("outputs") or {}
        preferred = outputs.get(output_node_id) or {}
        images = list(preferred.get("images") or [])
        if not images:
            for node_output in outputs.values():
                if isinstance(node_output, dict):
                    images.extend(node_output.get("images") or [])
        if not images:
            raise ComfyError(
                "ComfyUI completed but did not return any images",
                details={"output_nodes": sorted(outputs)},
            )
        return images

    def materialize_output(self, descriptor: dict) -> Path:
        filename = descriptor.get("filename")
        subfolder = descriptor.get("subfolder", "")
        if not isinstance(filename, str) or not filename:
            raise ComfyError("Invalid image descriptor from ComfyUI")

        root = self.output_root.resolve()
        candidate = (self.output_root / str(subfolder) / filename).resolve()
        if root not in candidate.parents and candidate != root:
            raise ComfyError("Unsafe output path returned by ComfyUI")
        if candidate.exists() and candidate.is_file():
            return candidate

        params: dict[str, Any] = {
            "filename": filename,
            "subfolder": subfolder,
            "type": descriptor.get("type", "output"),
        }
        try:
            response = self.session.get(f"{self.base_url}/view", params=params, timeout=60)
            response.raise_for_status()
        except requests.RequestException as exc:
            raise ComfyError(f"Cannot fetch generated image '{filename}': {exc}") from exc
        candidate.parent.mkdir(parents=True, exist_ok=True)
        candidate.write_bytes(response.content)
        return candidate

    def run(self, workflow: dict, output_node_id: str) -> tuple[str, list[Path], dict]:
        prompt_id, _client_id = self.queue(workflow)
        history_item = self.wait_for_result(prompt_id)
        descriptors = self.output_images(history_item, output_node_id)
        paths = [self.materialize_output(item) for item in descriptors]
        return prompt_id, paths, history_item
