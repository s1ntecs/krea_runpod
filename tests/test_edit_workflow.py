from __future__ import annotations

from krea_worker.lora_registry import ResolvedLora
from krea_worker.request import GenerationRequest
from krea_worker.settings import Settings
from krea_worker.workflow import build_edit_workflow
from test_edit_request import b64, png_bytes

EDIT_LORA = "krea2_identity_edit_v1_2.safetensors"


def _request(settings: Settings, two: bool = False) -> GenerationRequest:
    payload = {"prompt": "change her outfit to a red raincoat",
               "image": b64(png_bytes((1, 2, 3)))}
    if two:
        payload["image_b"] = b64(png_bytes((9, 8, 7)))
    return GenerationRequest.parse_edit(payload, settings)


def _build(settings: Settings, loras=None, two: bool = False):
    names = ["scene.png", "subject.png"][: 2 if two else 1]
    return build_edit_workflow(
        _request(settings, two), loras or [], settings, "krea2_edit", names, EDIT_LORA
    )


def test_sampler_takes_the_model_from_the_edit_patch(settings: Settings) -> None:
    wf = _build(settings).workflow
    assert wf["sampler"]["inputs"]["model"][0] == "edit_patch"
    assert wf["edit_patch"]["class_type"] == "Krea2EditModelPatch"


def test_edit_graph_has_no_model_sampling_node(settings: Settings) -> None:
    wf = _build(settings).workflow
    kinds = {node["class_type"] for node in wf.values()}
    assert "ModelSamplingAuraFlow" not in kinds


def test_both_conditionings_are_grounded_and_negative_is_empty(settings: Settings) -> None:
    wf = _build(settings).workflow
    assert wf["positive"]["class_type"] == "Krea2EditGroundedEncode"
    assert wf["negative"]["class_type"] == "Krea2EditGroundedEncode"
    assert wf["negative"]["inputs"]["prompt"] == ""
    assert wf["positive"]["inputs"]["grounding_px"] == 768


def test_identity_lora_loads_before_user_loras(settings: Settings) -> None:
    user = [ResolvedLora(requested_name="realism", file="krea2_realism_lora.safetensors",
                         strength=0.8, trigger="", append_trigger=True, registered=True)]
    wf = _build(settings, loras=user).workflow
    assert wf["lora_edit"]["inputs"]["lora_name"] == EDIT_LORA
    assert wf["lora_edit"]["inputs"]["model"][0] == "unet"
    assert wf["lora_01"]["inputs"]["model"][0] == "lora_edit"
    assert wf["edit_patch"]["inputs"]["model"][0] == "lora_01"


def test_single_reference_leaves_the_second_slot_unwired(settings: Settings) -> None:
    wf = _build(settings).workflow
    assert "source_latent_b" not in wf["edit_patch"]["inputs"]
    assert "image_b" not in wf["positive"]["inputs"]
    assert "src_01" not in wf


def test_two_references_keep_scene_first_and_subject_second(settings: Settings) -> None:
    wf = _build(settings, two=True).workflow
    assert wf["src_00"]["inputs"]["image"] == "scene.png"
    assert wf["src_01"]["inputs"]["image"] == "subject.png"
    assert wf["edit_patch"]["inputs"]["source_latent"][0] == "src_lat_00"
    assert wf["edit_patch"]["inputs"]["source_latent_b"][0] == "src_lat_01"
    assert wf["positive"]["inputs"]["image_b"][0] == "src_01"


def test_target_latent_is_the_same_latent_the_sampler_denoises(settings: Settings) -> None:
    wf = _build(settings).workflow
    assert wf["edit_patch"]["inputs"]["target_latent"] == wf["sampler"]["inputs"]["latent_image"]


def test_ref_boost_reaches_the_patch_node(settings: Settings) -> None:
    wf = _build(settings).workflow
    assert wf["edit_patch"]["inputs"]["ref_boost"] == 4.0
    assert wf["edit_patch"]["inputs"]["fit_mode"] == "fit"
