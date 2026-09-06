from __future__ import annotations


class WorkerError(Exception):
    """Base error returned to API callers with a stable code."""

    code = "worker_error"

    def __init__(self, message: str, *, details: dict | None = None) -> None:
        super().__init__(message)
        self.message = message
        self.details = details or {}

    def as_dict(self) -> dict:
        payload = {"code": self.code, "message": self.message}
        if self.details:
            payload["details"] = self.details
        return payload


class InputError(WorkerError):
    code = "invalid_input"


class ModelFileError(WorkerError):
    code = "model_file_error"


class LoraError(WorkerError):
    code = "lora_error"


class ComfyError(WorkerError):
    code = "comfyui_error"


class TimeoutError(WorkerError):
    code = "generation_timeout"
