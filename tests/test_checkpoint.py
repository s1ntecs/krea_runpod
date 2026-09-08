from __future__ import annotations

from pathlib import Path

import pytest

from krea_worker.errors import InputError, ModelFileError
from krea_worker.request import GenerationRequest
from krea_worker.service import KreaService
from krea_worker.settings import Settings
from krea_worker.workflow import build_edit_workflow, build_workflow
from conftest import write_large
from test_edit_request import b64, png_bytes

EDIT_LORA = "krea2_identity_edit_v1_2.safetensors"


def test_turbo_is_the_default_checkpoint(settings: Settings) -> None:
    assert GenerationRequest.parse({"prompt": "x"}, settings).checkpoint == "turbo"


def test_unknown_checkpoint_is_rejected(settings: Settings) -> None:
    with pytest.raises(InputError):
        GenerationRequest.parse({"prompt": "x", "checkpoint": "medium"}, settings)


def test_raw_brings_its_own_sampling_defaults(settings: Settings) -> None:
    """Raw is not distilled: the model card runs it at CFG 3 and ~20 steps."""
    req = GenerationRequest.parse({"prompt": "x", "checkpoint": "raw"}, settings)
    assert (req.steps, req.cfg) == (20, 3.0)


def test_explicit_sampling_wins_over_the_raw_defaults(settings: Settings) -> None:
    req = GenerationRequest.parse(
        {"prompt": "x", "checkpoint": "raw", "steps": 14, "cfg": 2.0}, settings
    )
    assert (req.steps, req.cfg) == (14, 2.0)


def test_settings_maps_each_checkpoint_to_its_file(settings: Settings) -> None:
    assert settings.unet_for("turbo") == settings.unet_name
    assert settings.unet_for("raw") == settings.raw_unet_name
    assert settings.unet_name != settings.raw_unet_name


def test_generate_graph_loads_the_requested_checkpoint(settings: Settings) -> None:
    req = GenerationRequest.parse({"prompt": "x", "checkpoint": "raw"}, settings)
    wf = build_workflow(req, [], settings, "krea2").workflow
    assert wf["unet"]["inputs"]["unet_name"] == settings.raw_unet_name


def test_edit_graph_loads_the_requested_checkpoint(settings: Settings) -> None:
    req = GenerationRequest.parse_edit(
        {"prompt": "x", "image": b64(png_bytes()), "checkpoint": "raw"}, settings
    )
    wf = build_edit_workflow(req, [], settings, "krea2", ["a.png"], EDIT_LORA).workflow
    assert wf["unet"]["inputs"]["unet_name"] == settings.raw_unet_name


def test_requesting_raw_without_the_file_fails_with_a_clear_error(
    settings: Settings, tmp_path: Path, monkeypatch
) -> None:
    write_large(settings.model_root / "diffusion_models" / settings.unet_name)
    write_large(settings.model_root / "text_encoders" / settings.text_encoder_name)
    write_large(settings.model_root / "vae" / settings.vae_name)
    service = KreaService(settings)
    monkeypatch.setattr(service.client, "wait_ready", lambda timeout=120.0: None)

    with pytest.raises(ModelFileError):
        service.process({"prompt": "x", "checkpoint": "raw"}, "job-raw")


def test_response_reports_which_checkpoint_ran(
    settings: Settings, tmp_path: Path, monkeypatch
) -> None:
    for sub, name in (("diffusion_models", settings.unet_name),
                      ("diffusion_models", settings.raw_unet_name),
                      ("text_encoders", settings.text_encoder_name),
                      ("vae", settings.vae_name)):
        write_large(settings.model_root / sub / name)
    image = tmp_path / "krea2_00001_.png"
    image.write_bytes(b"png")
    service = KreaService(settings)
    monkeypatch.setattr(service.client, "wait_ready", lambda timeout=120.0: None)
    monkeypatch.setattr(service.client, "run", lambda w, n: ("p1", [image], {}))

    result = service.process({"prompt": "x", "checkpoint": "raw"}, "job-raw-ok")
    assert result["checkpoint"] == "raw"
    assert result["steps"] == 20
