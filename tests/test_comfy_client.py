from __future__ import annotations

from pathlib import Path

import pytest

from krea_worker.comfy_client import ComfyClient
from krea_worker.errors import ComfyError

PNG = bytes([137, 80, 78, 71, 13, 10, 26, 10]) + b"body"


class _Response:
    def __init__(self, payload: dict, ok: bool = True) -> None:
        self._payload = payload
        self.ok = ok
        self.status_code = 200 if ok else 500

    def raise_for_status(self) -> None:
        if not self.ok:
            raise RuntimeError("boom")

    def json(self) -> dict:
        return self._payload


def _client(tmp_path: Path) -> ComfyClient:
    return ComfyClient("http://comfy:8188", tmp_path, 60, 0.01)


def test_upload_image_returns_name_assigned_by_comfyui(tmp_path: Path) -> None:
    client = _client(tmp_path)
    seen: dict = {}

    def fake_post(url, files=None, data=None, timeout=None):
        seen["url"] = url
        seen["files"] = files
        seen["data"] = data
        return _Response({"name": "krea_src_00.png", "subfolder": "", "type": "input"})

    client.session.post = fake_post
    name = client.upload_image(PNG, "source.png")

    assert name == "krea_src_00.png"
    assert seen["url"] == "http://comfy:8188/upload/image"
    assert seen["files"]["image"][1] == PNG


def test_upload_image_includes_subfolder_in_returned_name(tmp_path: Path) -> None:
    client = _client(tmp_path)
    client.session.post = lambda *a, **k: _Response(
        {"name": "src.png", "subfolder": "krea", "type": "input"}
    )
    assert client.upload_image(PNG, "source.png") == "krea/src.png"


def test_upload_image_raises_when_comfyui_returns_no_name(tmp_path: Path) -> None:
    client = _client(tmp_path)
    client.session.post = lambda *a, **k: _Response({"subfolder": ""})
    with pytest.raises(ComfyError):
        client.upload_image(PNG, "source.png")
