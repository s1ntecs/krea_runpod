from __future__ import annotations

import importlib
from pathlib import Path

import pytest

from krea_worker.errors import LoraError


@pytest.fixture
def handler_module(tmp_path: Path, monkeypatch):
    """Imports handler.py against throwaway paths so KreaService can be built."""
    catalog = tmp_path / "lora_catalog.json"
    catalog.write_text('{"schema_version": 1, "loras": {}}', encoding="utf-8")
    manifest = tmp_path / "models.json"
    manifest.write_text('{"schema_version": 1, "artifacts": []}', encoding="utf-8")
    monkeypatch.setenv("MODEL_ROOT", str(tmp_path / "models"))
    monkeypatch.setenv("LORA_CATALOG", str(catalog))
    monkeypatch.setenv("MODEL_MANIFEST", str(manifest))
    monkeypatch.setenv("OUTPUT_ROOT", str(tmp_path / "out"))
    import handler as module
    return importlib.reload(module)


def test_failure_details_survive_the_runpod_sdk(handler_module, monkeypatch) -> None:
    """runpod's rp_job.py pops a top-level "error" key out of the handler result,
    so a failure reported under that name reaches the caller as a bare {"ok": false}.
    """
    def boom(payload, job_id):
        raise LoraError("LoRA 'snofs' was not found", details={"available_files": []})

    monkeypatch.setattr(handler_module.SERVICE, "process", boom)
    result = handler_module.handler({"id": "j1", "input": {"prompt": "x"}})

    assert result["ok"] is False
    assert "error" not in result, "runpod strips a top-level 'error' key"
    assert result["failure"]["code"] == "lora_error"
    assert "snofs" in result["failure"]["message"]
    assert result["failure"]["details"] == {"available_files": []}


def test_unexpected_exceptions_also_report_under_failure(handler_module, monkeypatch) -> None:
    def boom(payload, job_id):
        raise RuntimeError("kaboom")

    monkeypatch.setattr(handler_module.SERVICE, "process", boom)
    result = handler_module.handler({"id": "j2", "input": {}})

    assert result["ok"] is False
    assert "error" not in result
    assert result["failure"]["code"] == "internal_error"
    assert "kaboom" in result["failure"]["message"]
