from __future__ import annotations

import pytest

from krea_worker.errors import InputError
from krea_worker.request import FACE_SYSTEM_PROMPT, GenerationRequest
from krea_worker.settings import Settings
from krea_worker.workflow import build_edit_workflow
from test_edit_request import b64, png_bytes

EDIT_LORA = "krea2_identity_edit_v1_2.safetensors"


def _req(settings: Settings, **extra) -> GenerationRequest:
    payload = {"prompt": "put her on a night market", "image": b64(png_bytes())}
    payload.update(extra)
    return GenerationRequest.parse_edit(payload, settings)


def _wf(settings: Settings, **extra):
    return build_edit_workflow(
        _req(settings, **extra), [], settings, "krea2_edit", ["scene.png"], EDIT_LORA
    ).workflow


def test_system_prompt_is_empty_by_default(settings: Settings) -> None:
    assert _req(settings).system_prompt == ""
    assert _wf(settings)["positive"]["inputs"]["system_prompt"] == ""


def test_face_preset_expands_to_the_identity_system_prompt(settings: Settings) -> None:
    req = _req(settings, system_prompt="face")
    assert req.system_prompt == FACE_SYSTEM_PROMPT
    assert "facial identity" in FACE_SYSTEM_PROMPT.lower()


def test_custom_system_prompt_passes_through_verbatim(settings: Settings) -> None:
    wf = _wf(settings, system_prompt="Look only at the eyes:")
    assert wf["positive"]["inputs"]["system_prompt"] == "Look only at the eyes:"


def test_system_prompt_does_not_touch_the_trained_unconditional(settings: Settings) -> None:
    """The negative encode is the trained unconditional; overriding its system
    prompt would move it out of distribution."""
    wf = _wf(settings, system_prompt="face")
    assert wf["negative"]["inputs"]["system_prompt"] == ""


def test_overlong_system_prompt_is_rejected(settings: Settings) -> None:
    with pytest.raises(InputError):
        _req(settings, system_prompt="x" * 4001)


def test_face_preset_also_raises_grounding_for_people(settings: Settings) -> None:
    """1024 is what the node pack recommends for people; 768 stays the default."""
    assert _req(settings).grounding_px == 768
    assert _req(settings, preset="face").grounding_px == 1024
    assert _req(settings, preset="face").ref_boost == 4.0
    assert _req(settings, preset="face").steps == 12
    assert _req(settings, preset="face").system_prompt == FACE_SYSTEM_PROMPT


def test_explicit_values_win_over_the_preset(settings: Settings) -> None:
    req = _req(settings, preset="face", grounding_px=512, ref_boost=3.0, steps=8)
    assert (req.grounding_px, req.ref_boost, req.steps) == (512, 3.0, 8)
