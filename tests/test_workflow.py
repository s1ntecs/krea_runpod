from __future__ import annotations

from krea_worker.lora_registry import ResolvedLora
from krea_worker.request import GenerationRequest
from krea_worker.settings import Settings
from krea_worker.workflow import build_workflow


def test_builds_dynamic_lora_chain_and_appends_trigger(settings: Settings) -> None:
    request = GenerationRequest.parse(
        {
            "prompt": "A fox in a forest",
            "width": 1024,
            "height": 1024,
            "seed": 123,
            "loras": ["first", "second"],
        },
        settings,
    )
    loras = [
        ResolvedLora("first", "a.safetensors", 1.0, "ink wash style", True, True),
        ResolvedLora("second", "b.safetensors", 0.5, "", True, False),
    ]
    result = build_workflow(request, loras, settings, "job")

    assert result.final_prompt == "A fox in a forest, ink wash style"
    assert result.workflow["lora_01"]["inputs"]["model"] == ["unet", 0]
    assert result.workflow["lora_02"]["inputs"]["model"] == ["lora_01", 0]
    assert result.workflow["model_sampling"]["inputs"]["model"] == ["lora_02", 0]
    assert result.workflow["sampler"]["inputs"]["scheduler"] == "beta"
    assert result.workflow["latent"]["class_type"] == "EmptySD3LatentImage"


def test_zeroes_negative_when_empty(settings: Settings) -> None:
    request = GenerationRequest.parse({"prompt": "A room"}, settings)
    result = build_workflow(request, [], settings, "job")
    assert result.workflow["negative"]["class_type"] == "ConditioningZeroOut"


def test_encodes_explicit_negative_prompt(settings: Settings) -> None:
    request = GenerationRequest.parse(
        {"prompt": "A room", "negative_prompt": "text, watermark"}, settings
    )
    result = build_workflow(request, [], settings, "job")
    assert result.workflow["negative"]["class_type"] == "CLIPTextEncode"
    assert result.workflow["negative"]["inputs"]["text"] == "text, watermark"
