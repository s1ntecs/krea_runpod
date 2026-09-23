from __future__ import annotations

import pytest

from krea_worker.request import GenerationRequest, fit_to_model
from krea_worker.settings import Settings
from test_edit_request import b64, png_bytes


def test_keeps_a_size_the_model_already_accepts() -> None:
    assert fit_to_model(976, 1600, 2.1) == (976, 1600)


def test_rounds_down_to_a_multiple_of_sixteen() -> None:
    """979x1606 is what a phone produces; the model needs both sides /16."""
    assert fit_to_model(979, 1606, 2.1) == (976, 1600)


def test_scales_an_oversized_image_under_the_megapixel_cap() -> None:
    w, h = fit_to_model(4000, 3000, 2.1)
    assert w % 16 == 0 and h % 16 == 0
    assert w * h / 1_000_000 <= 2.1
    # aspect ratio preserved within the rounding error of one 16px step
    assert abs((w / h) - (4000 / 3000)) < 0.02


def test_keeps_portrait_orientation_when_scaling_down() -> None:
    w, h = fit_to_model(2000, 3000, 2.1)
    assert h > w
    assert w * h / 1_000_000 <= 2.1


def test_never_goes_below_the_minimum_side() -> None:
    assert fit_to_model(50, 40, 2.1) == (256, 256)


def test_never_exceeds_the_maximum_side() -> None:
    w, h = fit_to_model(8000, 1000, 2.1)
    assert w <= 2048 and h >= 256


def test_edit_takes_the_size_from_the_image_when_none_given(
    settings: Settings, monkeypatch
) -> None:
    monkeypatch.setattr("krea_worker.request.image_size", lambda data: (979, 1606))
    req = GenerationRequest.parse_edit(
        {"prompt": "change her coat", "image": b64(png_bytes())}, settings
    )
    assert (req.width, req.height) == (976, 1600)


def test_an_explicit_size_still_wins(settings: Settings, monkeypatch) -> None:
    monkeypatch.setattr("krea_worker.request.image_size", lambda data: (979, 1606))
    req = GenerationRequest.parse_edit(
        {"prompt": "change her coat", "image": b64(png_bytes()),
         "width": 768, "height": 768},
        settings,
    )
    assert (req.width, req.height) == (768, 768)


def test_generate_without_a_size_stays_square(settings: Settings) -> None:
    """generate has no source image to copy, so the old default applies."""
    req = GenerationRequest.parse({"prompt": "a cat"}, settings)
    assert (req.width, req.height) == (1024, 1024)


def test_only_one_side_given_is_rejected(settings: Settings, monkeypatch) -> None:
    monkeypatch.setattr("krea_worker.request.image_size", lambda data: (979, 1606))
    with pytest.raises(Exception):
        GenerationRequest.parse_edit(
            {"prompt": "change her coat", "image": b64(png_bytes()), "width": 768},
            settings,
        )
