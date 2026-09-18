from __future__ import annotations

import struct
import zlib

import pytest

from krea_worker.face_mask import FaceBox, build_mask_png, largest_face


def png_size(data: bytes) -> tuple[int, int]:
    assert data.startswith(bytes([137, 80, 78, 71, 13, 10, 26, 10]))
    width, height = struct.unpack(">II", data[16:24])
    return width, height


def decode_gray(data: bytes) -> tuple[int, int, list[list[int]]]:
    """Minimal greyscale PNG reader, enough to inspect what we drew."""
    width, height = png_size(data)
    idat = b""
    pos = 8
    while pos < len(data):
        length = struct.unpack(">I", data[pos:pos + 4])[0]
        typ = data[pos + 4:pos + 8]
        if typ == b"IDAT":
            idat += data[pos + 8:pos + 8 + length]
        pos += 12 + length
    raw = zlib.decompress(idat)
    rows, stride = [], width
    for y in range(height):
        start = y * (stride + 1)
        assert raw[start] == 0, "only unfiltered rows are produced"
        rows.append(list(raw[start + 1:start + 1 + stride]))
    return width, height, rows


def test_largest_face_wins_over_bystanders() -> None:
    faces = [FaceBox(10, 10, 20, 20), FaceBox(100, 100, 90, 120), FaceBox(5, 5, 30, 30)]
    assert largest_face(faces) == FaceBox(100, 100, 90, 120)


def test_largest_face_on_empty_list_is_none() -> None:
    assert largest_face([]) is None


def test_mask_matches_the_source_size() -> None:
    mask = build_mask_png(200, 300, FaceBox(80, 100, 40, 50))
    assert png_size(mask) == (200, 300)


def test_mask_is_white_on_the_face_and_black_far_away() -> None:
    _w, _h, rows = decode_gray(build_mask_png(200, 300, FaceBox(80, 100, 40, 50)))
    assert rows[125][100] == 255, "centre of the face must be fully masked"
    assert rows[5][5] == 0, "a far corner must stay unmasked"


def test_mask_extends_past_the_box_to_catch_chin_and_hairline() -> None:
    """The detector's box stops at the jaw; ref_boost needs the whole head."""
    box = FaceBox(80, 100, 40, 50)
    _w, _h, rows = decode_gray(build_mask_png(200, 300, box, margin=0.25))
    just_above = box.y - 5
    assert rows[just_above][box.x + box.width // 2] > 0


def test_mask_rejects_a_box_outside_the_image() -> None:
    with pytest.raises(ValueError):
        build_mask_png(100, 100, FaceBox(300, 300, 50, 50))
