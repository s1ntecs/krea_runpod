from __future__ import annotations

import base64
from pathlib import Path

from krea_worker.service import KreaService
from krea_worker.settings import Settings
from conftest import write_large


def test_model_file_validation(settings: Settings) -> None:
    write_large(settings.model_root / "diffusion_models" / settings.unet_name)
    write_large(settings.model_root / "text_encoders" / settings.text_encoder_name)
    write_large(settings.model_root / "vae" / settings.vae_name)
    service = KreaService(settings)
    status = service.validate_model_files()
    assert all(item["valid"] for item in status.values())


def test_model_file_validation_uses_manifest_minimum(settings: Settings) -> None:
    for path in (
        settings.model_root / "diffusion_models" / settings.unet_name,
        settings.model_root / "text_encoders" / settings.text_encoder_name,
        settings.model_root / "vae" / settings.vae_name,
    ):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b"too-small")

    service = KreaService(settings)
    from krea_worker.errors import ModelFileError

    try:
        service.validate_model_files()
    except ModelFileError as exc:
        assert all(
            item["minimum_bytes"] == 1024 * 1024
            for item in exc.details["files"].values()
        )
    else:
        raise AssertionError("small model files must be rejected")


def _prepare_models(settings: Settings) -> None:
    write_large(settings.model_root / "diffusion_models" / settings.unet_name)
    write_large(settings.model_root / "text_encoders" / settings.text_encoder_name)
    write_large(settings.model_root / "vae" / settings.vae_name)


def _stub_comfy(service: KreaService, monkeypatch, image: Path) -> None:
    monkeypatch.setattr(service.client, "wait_ready", lambda timeout=120.0: None)
    monkeypatch.setattr(
        service.client, "run", lambda workflow, node: ("prompt-1", [image], {})
    )


def test_generate_returns_raw_base64_images_and_time(
    settings: Settings, tmp_path: Path, monkeypatch
) -> None:
    _prepare_models(settings)
    image = tmp_path / "krea2_00001_.png"
    image.write_bytes(b"fake-png-bytes")

    service = KreaService(settings)
    _stub_comfy(service, monkeypatch, image)

    result = service.generate({"prompt": "a cat", "steps": 8, "seed": 42}, "job-1")

    assert base64.b64decode(result["images_base64"][0]) == b"fake-png-bytes"
    assert result["steps"] == 8
    assert result["seed"] == 42
    assert isinstance(result["time"], float)
    assert "elapsed_seconds" not in result
    assert "images" not in result


def test_generate_keeps_images_field_for_non_base64_modes(
    settings: Settings, tmp_path: Path, monkeypatch
) -> None:
    _prepare_models(settings)
    image = tmp_path / "krea2_00001_.png"
    image.write_bytes(b"fake-png-bytes")

    service = KreaService(settings)
    _stub_comfy(service, monkeypatch, image)

    result = service.generate(
        {"prompt": "a cat", "output_mode": "path"}, "job-2"
    )

    assert result["output_mode"] == "path"
    assert result["images"][0]["path"] == str(image)
    assert "images_base64" not in result
