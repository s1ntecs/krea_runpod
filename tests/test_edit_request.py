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
