from __future__ import annotations

import base64
import mimetypes
import os
from pathlib import Path

from .errors import WorkerError


class OutputError(WorkerError):
    code = "output_error"


class OutputManager:
    def __init__(self, default_mode: str, clean_outputs: bool) -> None:
        self.default_mode = default_mode
        self.clean_outputs = clean_outputs

    @staticmethod
    def _s3_configured() -> bool:
        return bool(
            os.getenv("BUCKET_ENDPOINT_URL")
            and os.getenv("BUCKET_ACCESS_KEY_ID")
            and os.getenv("BUCKET_SECRET_ACCESS_KEY")
        )

    def _select_mode(self, requested: str | None) -> str:
        mode = requested or self.default_mode
        if mode == "auto":
            return "s3" if self._s3_configured() else "base64"
        return mode

    @staticmethod
    def _base64(path: Path) -> dict:
        mime = mimetypes.guess_type(path.name)[0] or "image/png"
        return {
            "filename": path.name,
            "mime_type": mime,
            "base64": base64.b64encode(path.read_bytes()).decode("ascii"),
        }

    @staticmethod
    def _s3(path: Path, job_id: str) -> dict:
        try:
            from runpod.serverless.utils import rp_upload

            url = rp_upload.upload_image(job_id, str(path))
        except Exception as exc:  # SDK/network exceptions vary by version
            raise OutputError(f"Could not upload output to S3: {exc}") from exc
        if not url:
            raise OutputError("S3 upload returned an empty URL")
        return {"filename": path.name, "url": str(url)}

    def publish(self, paths: list[Path], requested_mode: str | None, job_id: str) -> tuple[str, list[dict]]:
        configured_mode = requested_mode or self.default_mode
        mode = self._select_mode(requested_mode)

        def render(selected_mode: str) -> list[dict]:
            rendered: list[dict] = []
            for path in paths:
                if selected_mode == "base64":
                    rendered.append(self._base64(path))
                elif selected_mode == "s3":
                    rendered.append(self._s3(path, job_id))
                elif selected_mode == "path":
                    rendered.append({"filename": path.name, "path": str(path)})
                else:
                    raise OutputError(f"Unsupported output mode: {selected_mode}")
            return rendered

        try:
            results = render(mode)
        except OutputError:
            if configured_mode != "auto" or mode != "s3":
                raise
            mode = "base64"
            results = render(mode)

        if self.clean_outputs and mode != "path":
            for path in paths:
                try:
                    path.unlink(missing_ok=True)
                except OSError:
                    pass
        return mode, results
