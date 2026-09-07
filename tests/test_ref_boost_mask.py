from __future__ import annotations

import pytest

from krea_worker.errors import InputError
from krea_worker.request import GenerationRequest
from krea_worker.settings import Settings
from krea_worker.workflow import build_edit_workflow
from test_edit_request import b64, png_bytes

EDIT_LORA = "krea2_identity_edit_v1_2.safetensors"


def _req(settings: Settings, **extra) -> GenerationRequest:
    payload = {"prompt": "face the camera", "image": b64(png_bytes())}
    payload.update(extra)
    return GenerationRequest.parse_edit(payload, settings)


def test_mask_is_absent_by_default(settings: Settings) -> None:
    assert _req(settings).ref_boost_mask is None


def test_mask_is_decoded_like_the_reference_images(settings: Settings) -> None:
    mask = png_bytes((255, 255, 255))
    assert _req(settings, ref_boost_mask=b64(mask)).ref_boost_mask == mask


def test_non_image_mask_is_rejected(settings: Settings) -> None:
    with pytest.raises(InputError):
        _req(settings, ref_boost_mask=b64(b"not an image"))


def test_graph_omits_mask_nodes_when_no_mask_is_given(settings: Settings) -> None:
    wf = build_edit_workflow(
        _req(settings), [], settings, "krea2_edit", ["scene.png"], EDIT_LORA
    ).workflow
    assert "ref_mask" not in wf
    assert "ref_boost_mask" not in wf["edit_patch"]["inputs"]


def test_mask_is_converted_to_a_mask_and_wired_to_the_patch(settings: Settings) -> None:
    req = _req(settings, ref_boost_mask=b64(png_bytes((255, 255, 255))))
    wf = build_edit_workflow(
        req, [], settings, "krea2_edit", ["scene.png"], EDIT_LORA, mask_name="m.png"
    ).workflow
    assert wf["ref_mask_img"]["class_type"] == "LoadImage"
    assert wf["ref_mask_img"]["inputs"]["image"] == "m.png"
    assert wf["ref_mask"]["class_type"] == "ImageToMask"
    assert wf["ref_mask"]["inputs"]["image"] == ["ref_mask_img", 0]
    assert wf["ref_mask"]["inputs"]["channel"] == "red"
    assert wf["edit_patch"]["inputs"]["ref_boost_mask"] == ["ref_mask", 0]


def test_building_with_a_mask_but_no_uploaded_name_is_a_programming_error(
    settings: Settings,
) -> None:
    req = _req(settings, ref_boost_mask=b64(png_bytes((255, 255, 255))))
    with pytest.raises(ValueError):
        build_edit_workflow(req, [], settings, "krea2_edit", ["scene.png"], EDIT_LORA)
