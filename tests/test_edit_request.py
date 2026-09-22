from __future__ import annotations

import base64
import struct
import zlib

import pytest

from krea_worker.errors import InputError
from krea_worker.request import GenerationRequest
from krea_worker.settings import Settings


def png_bytes(rgb=(10, 20, 30)) -> bytes:
    def chunk(typ: bytes, data: bytes) -> bytes:
        return (struct.pack(">I", len(data)) + typ + data
                + struct.pack(">I", zlib.crc32(typ + data) & 0xFFFFFFFF))
    ihdr = struct.pack(">IIBBBBB", 1, 1, 8, 2, 0, 0, 0)
    return (bytes([137, 80, 78, 71, 13, 10, 26, 10]) + chunk(b"IHDR", ihdr)
            + chunk(b"IDAT", zlib.compress(b"\x00" + bytes(rgb))) + chunk(b"IEND", b""))


def b64(data: bytes) -> str:
    return base64.b64encode(data).decode("ascii")


def test_edit_requires_at_least_one_image(settings: Settings) -> None:
    with pytest.raises(InputError):
        GenerationRequest.parse_edit({"prompt": "make the coat red"}, settings)


def test_edit_decodes_single_reference_image(settings: Settings) -> None:
    src = png_bytes()
    req = GenerationRequest.parse_edit(
        {"prompt": "make the coat red", "image": b64(src)}, settings
    )
    assert req.images == (src,)


def test_edit_accepts_second_reference_in_training_order(settings: Settings) -> None:
    scene, person = png_bytes((1, 2, 3)), png_bytes((9, 8, 7))
    req = GenerationRequest.parse_edit(
        {"prompt": "put this man next to the tractor",
         "image": b64(scene), "image_b": b64(person)},
        settings,
    )
    assert req.images == (scene, person)


def test_edit_rejects_a_third_reference_image(settings: Settings) -> None:
    with pytest.raises(InputError):
        GenerationRequest.parse_edit(
            {"prompt": "x", "images": [b64(png_bytes())] * 3}, settings
        )


def test_edit_rejects_payload_that_is_not_an_image(settings: Settings) -> None:
    with pytest.raises(InputError):
        GenerationRequest.parse_edit(
            {"prompt": "x", "image": b64(b"this is not an image")}, settings
        )


def test_edit_rejects_invalid_base64(settings: Settings) -> None:
    with pytest.raises(InputError):
        GenerationRequest.parse_edit({"prompt": "x", "image": "!!!not base64!!!"}, settings)


def test_edit_strips_data_uri_prefix(settings: Settings) -> None:
    src = png_bytes()
    req = GenerationRequest.parse_edit(
        {"prompt": "x", "image": "data:image/png;base64," + b64(src)}, settings
    )
    assert req.images == (src,)


def test_edit_defaults_match_the_shipped_workflow(settings: Settings) -> None:
    req = GenerationRequest.parse_edit(
        {"prompt": "x", "image": b64(png_bytes())}, settings
    )
    assert req.steps == 10
    assert req.cfg == 1.0
    assert req.scheduler == "simple"
    assert req.grounding_px == 768
    assert req.ref_boost == 4.0


def test_edit_rejects_grounding_px_out_of_range(settings: Settings) -> None:
    with pytest.raises(InputError):
        GenerationRequest.parse_edit(
            {"prompt": "x", "image": b64(png_bytes()), "grounding_px": 9000}, settings
        )


def test_edit_accepts_a_url_instead_of_base64(settings: Settings, monkeypatch) -> None:
    """A service should not have to inflate every photo by a third."""
    src = png_bytes((4, 5, 6))
    asked: list = []

    def fake_fetch(url, name, **kwargs):
        asked.append((url, name))
        return src

    monkeypatch.setattr("krea_worker.request.fetch_image", fake_fetch)
    req = GenerationRequest.parse_edit(
        {"prompt": "change her coat", "image": "https://cdn.example/a.png"}, settings
    )
    assert req.images == (src,)
    assert asked == [("https://cdn.example/a.png", "image")]


def test_edit_still_accepts_base64_after_urls_were_added(settings: Settings) -> None:
    src = png_bytes((7, 8, 9))
    req = GenerationRequest.parse_edit(
        {"prompt": "change her coat", "image": b64(src)}, settings
    )
    assert req.images == (src,)


def test_a_mask_may_also_come_as_a_url(settings: Settings, monkeypatch) -> None:
    mask = png_bytes((1, 1, 1))
    monkeypatch.setattr("krea_worker.request.fetch_image", lambda url, name, **kw: mask)
    req = GenerationRequest.parse_edit(
        {"prompt": "change her pose", "image": b64(png_bytes()),
         "ref_boost_mask": "https://cdn.example/mask.png"},
        settings,
    )
    assert req.ref_boost_mask == mask
