from __future__ import annotations

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
