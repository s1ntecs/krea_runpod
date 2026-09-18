from __future__ import annotations

from pathlib import Path

from krea_worker.request import GenerationRequest
from krea_worker.service import KreaService
from krea_worker.settings import Settings
from conftest import write_large
from test_edit_request import b64, png_bytes

EDIT_LORA = "krea2_identity_edit_v1_2.safetensors"
MASK = b"fake-mask-png"


def _prepare(settings: Settings) -> None:
    write_large(settings.model_root / "diffusion_models" / settings.unet_name)
    write_large(settings.model_root / "text_encoders" / settings.text_encoder_name)
    write_large(settings.model_root / "vae" / settings.vae_name)
    write_large(settings.lora_root / EDIT_LORA)


def _service(settings: Settings, monkeypatch, image: Path, uploads: list) -> KreaService:
    service = KreaService(settings)
    monkeypatch.setattr(service.client, "wait_ready", lambda timeout=120.0: None)
    monkeypatch.setattr(service.client, "run", lambda workflow, node: ("edit-1", [image], {}))

    def fake_upload(data: bytes, filename: str) -> str:
        uploads.append((data, filename))
        return "uploaded_%d.png" % len(uploads)

    monkeypatch.setattr(service.client, "upload_image", fake_upload)
    return service


def _out(tmp_path: Path) -> Path:
    out = tmp_path / "krea2_edit_00001_.png"
    out.write_bytes(b"edited")
    return out


def test_request_parses_the_auto_face_mask_flag(settings: Settings) -> None:
    req = GenerationRequest.parse_edit(
        {"prompt": "change her pose", "image": b64(png_bytes()), "auto_face_mask": True},
        settings,
    )
    assert req.auto_face_mask is True


def test_auto_mask_is_detected_and_uploaded(
    settings: Settings, tmp_path: Path, monkeypatch
) -> None:
    _prepare(settings)
    uploads: list = []
    service = _service(settings, monkeypatch, _out(tmp_path), uploads)
    monkeypatch.setattr("krea_worker.service.auto_face_mask", lambda image: (MASK, 1))

    result = service.process(
        {"action": "edit", "prompt": "change her pose",
         "image": b64(png_bytes()), "auto_face_mask": True},
        "job-auto",
    )

    assert result["auto_face_mask"] == "detected"
    assert result["faces_found"] == 1
    assert result["ref_boost_mask"] is True
    assert any(data == MASK for data, _name in uploads), "the drawn mask must be uploaded"


def test_without_a_face_it_falls_back_and_lowers_ref_boost(
    settings: Settings, tmp_path: Path, monkeypatch
) -> None:
    """No face means ref_boost 4 would freeze the frame, so it is relaxed."""
    _prepare(settings)
    uploads: list = []
    service = _service(settings, monkeypatch, _out(tmp_path), uploads)
    monkeypatch.setattr("krea_worker.service.auto_face_mask", lambda image: (None, 0))

    result = service.process(
        {"action": "edit", "prompt": "change her pose",
         "image": b64(png_bytes()), "auto_face_mask": True},
        "job-auto",
    )

    assert result["auto_face_mask"] == "fallback"
    assert result["faces_found"] == 0
    assert result["ref_boost_mask"] is False
    assert result["ref_boost"] == 1.75
    assert all(data != MASK for data, _name in uploads)


def test_an_explicit_mask_wins_over_auto_detection(
    settings: Settings, tmp_path: Path, monkeypatch
) -> None:
    _prepare(settings)
    uploads: list = []
    service = _service(settings, monkeypatch, _out(tmp_path), uploads)
    called = []
    monkeypatch.setattr(
        "krea_worker.service.auto_face_mask",
        lambda image: (called.append(image), (MASK, 1))[1],
    )
    manual = png_bytes((7, 7, 7))

    result = service.process(
        {"action": "edit", "prompt": "change her pose", "image": b64(png_bytes()),
         "auto_face_mask": True, "ref_boost_mask": b64(manual)},
        "job-auto",
    )

    assert result["auto_face_mask"] == "manual"
    assert not called, "detection must not run when a mask was supplied"
    assert any(data == manual for data, _name in uploads)


def test_auto_face_mask_is_absent_from_the_response_when_not_requested(
    settings: Settings, tmp_path: Path, monkeypatch
) -> None:
    _prepare(settings)
    service = _service(settings, monkeypatch, _out(tmp_path), [])

    result = service.process(
        {"action": "edit", "prompt": "make the coat red", "image": b64(png_bytes())},
        "job-plain",
    )

    assert "auto_face_mask" not in result
    assert "faces_found" not in result
