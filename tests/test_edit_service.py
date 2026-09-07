from __future__ import annotations

import base64
from pathlib import Path

import pytest

from krea_worker.errors import ModelFileError
from krea_worker.service import KreaService
from krea_worker.settings import Settings
from conftest import write_large
from test_edit_request import b64, png_bytes

EDIT_LORA = "krea2_identity_edit_v1_2.safetensors"


def _prepare(settings: Settings, with_edit_lora: bool = True) -> None:
    write_large(settings.model_root / "diffusion_models" / settings.unet_name)
    write_large(settings.model_root / "text_encoders" / settings.text_encoder_name)
    write_large(settings.model_root / "vae" / settings.vae_name)
    if with_edit_lora:
        write_large(settings.lora_root / EDIT_LORA)


def _service(settings: Settings, monkeypatch, image: Path, uploads: list):
    service = KreaService(settings)
    monkeypatch.setattr(service.client, "wait_ready", lambda timeout=120.0: None)
    monkeypatch.setattr(
        service.client, "run", lambda workflow, node: ("edit-1", [image], {})
    )

    def fake_upload(data: bytes, filename: str) -> str:
        uploads.append((data, filename))
        return "uploaded_%d.png" % len(uploads)

    monkeypatch.setattr(service.client, "upload_image", fake_upload)
    return service


def test_edit_returns_the_same_response_shape_as_generate(
    settings: Settings, tmp_path: Path, monkeypatch
) -> None:
    _prepare(settings)
    out = tmp_path / "krea2_edit_00001_.png"
    out.write_bytes(b"edited-png-bytes")
    uploads: list = []
    service = _service(settings, monkeypatch, out, uploads)

    result = service.process(
        {"action": "edit", "prompt": "make the coat red", "image": b64(png_bytes())},
        "job-edit",
    )

    assert result["action"] == "edit"
    assert base64.b64decode(result["images_base64"][0]) == b"edited-png-bytes"
    assert result["steps"] == 10
    assert isinstance(result["time"], float)


def test_edit_uploads_every_reference_image_to_comfyui(
    settings: Settings, tmp_path: Path, monkeypatch
) -> None:
    _prepare(settings)
    out = tmp_path / "krea2_edit_00001_.png"
    out.write_bytes(b"edited")
    uploads: list = []
    service = _service(settings, monkeypatch, out, uploads)
    scene, subject = png_bytes((1, 2, 3)), png_bytes((9, 8, 7))

    service.process(
        {"action": "edit", "prompt": "put him by the tractor",
         "image": b64(scene), "image_b": b64(subject)},
        "job-edit-2",
    )

    assert [data for data, _name in uploads] == [scene, subject]


def test_edit_fails_clearly_when_the_identity_lora_is_missing(
    settings: Settings, tmp_path: Path, monkeypatch
) -> None:
    _prepare(settings, with_edit_lora=False)
    out = tmp_path / "x.png"
    out.write_bytes(b"edited")
    service = _service(settings, monkeypatch, out, [])

    with pytest.raises(ModelFileError):
        service.process(
            {"action": "edit", "prompt": "x", "image": b64(png_bytes())}, "job-edit-3"
        )
