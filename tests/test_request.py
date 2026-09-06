from __future__ import annotations

import pytest

from krea_worker.errors import InputError
from krea_worker.request import GenerationRequest
from krea_worker.settings import Settings


def test_valid_request(settings: Settings) -> None:
    request = GenerationRequest.parse(
        {
            "prompt": "A portrait in soft daylight",
            "width": 1024,
            "height": 1280,
            "seed": -1,
            "lora": "realism",
        },
        settings,
    )
    assert request.width == 1024
    assert request.height == 1280
    assert request.seed >= 0
    assert request.loras == "realism"


def test_dimensions_must_be_multiple_of_16(settings: Settings) -> None:
    with pytest.raises(InputError, match="divisible by 16"):
        GenerationRequest.parse({"prompt": "test", "width": 1001}, settings)


def test_megapixel_limit(settings: Settings) -> None:
    with pytest.raises(InputError, match="limit"):
        GenerationRequest.parse(
            {"prompt": "test", "width": 1536, "height": 1536}, settings
        )


def test_rejects_unknown_scheduler(settings: Settings) -> None:
    with pytest.raises(InputError, match="unsupported scheduler"):
        GenerationRequest.parse(
            {"prompt": "test", "scheduler": "made_up"}, settings
        )


def test_total_batch_megapixel_limit(settings: Settings) -> None:
    with pytest.raises(InputError, match="total batch limit"):
        GenerationRequest.parse(
            {
                "prompt": "test",
                "width": 1280,
                "height": 1024,
                "num_images": 2,
            },
            settings,
        )


def test_rejects_fractional_integer_and_non_finite_cfg(settings: Settings) -> None:
    with pytest.raises(InputError, match="steps must be an integer"):
        GenerationRequest.parse({"prompt": "test", "steps": 7.5}, settings)
    with pytest.raises(InputError, match="finite"):
        GenerationRequest.parse({"prompt": "test", "cfg": "nan"}, settings)


def test_supports_lora_name_compatibility_fields(settings: Settings) -> None:
    request = GenerationRequest.parse(
        {
            "prompt": "test",
            "lora_name": "realism",
            "lora_strength": 0.8,
            "lora_trigger": "natural photo",
            "append_trigger": False,
        },
        settings,
    )
    assert request.loras == {
        "name": "realism",
        "strength": 0.8,
        "trigger": "natural photo",
        "append_trigger": False,
    }
