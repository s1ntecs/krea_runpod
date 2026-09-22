from __future__ import annotations

import pytest

from krea_worker.errors import InputError
from krea_worker.image_source import fetch_image, looks_like_url
from test_edit_request import png_bytes


class FakeResponse:
    def __init__(self, status=200, headers=None, chunks=(), url="https://cdn.example/x.png"):
        self.status_code = status
        self.headers = headers or {}
        self._chunks = chunks
        self.url = url
        self.closed = False

    def iter_content(self, chunk_size):
        yield from self._chunks

    def close(self):
        self.closed = True


def _session(response: FakeResponse, seen: list | None = None):
    class Session:
        def get(self, url, **kwargs):
            if seen is not None:
                seen.append((url, kwargs))
            return response

    return Session()


@pytest.mark.parametrize("value,expected", [
    ("https://cdn.example/a.png", True),
    ("http://cdn.example/a.png", True),
    ("HTTPS://CDN.EXAMPLE/a.png", True),
    ("iVBORw0KGgoAAAANSUhEUg", False),
    ("data:image/png;base64,iVBORw0", False),
    ("ftp://cdn.example/a.png", False),
])
def test_recognises_which_strings_are_urls(value: str, expected: bool) -> None:
    assert looks_like_url(value) is expected


def test_downloads_an_image(monkeypatch) -> None:
    src = png_bytes()
    monkeypatch.setattr("krea_worker.image_source._resolve_public_host", lambda host: None)
    data = fetch_image("https://cdn.example/a.png", "image",
                       session=_session(FakeResponse(chunks=[src])))
    assert data == src


def test_rejects_a_non_image_payload(monkeypatch) -> None:
    monkeypatch.setattr("krea_worker.image_source._resolve_public_host", lambda host: None)
    with pytest.raises(InputError, match="PNG, JPEG"):
        fetch_image("https://cdn.example/a.html", "image",
                    session=_session(FakeResponse(chunks=[b"<!doctype html><html>"])))


def test_rejects_a_bad_status(monkeypatch) -> None:
    monkeypatch.setattr("krea_worker.image_source._resolve_public_host", lambda host: None)
    with pytest.raises(InputError, match="HTTP 404"):
        fetch_image("https://cdn.example/missing.png", "image",
                    session=_session(FakeResponse(status=404)))


def test_stops_downloading_past_the_size_limit(monkeypatch) -> None:
    monkeypatch.setattr("krea_worker.image_source._resolve_public_host", lambda host: None)
    huge = [png_bytes()] + [b"\x00" * 4096] * 64
    with pytest.raises(InputError, match="larger than"):
        fetch_image("https://cdn.example/big.png", "image",
                    session=_session(FakeResponse(chunks=huge)), max_bytes=8192)


def test_refuses_to_follow_redirects(monkeypatch) -> None:
    """A redirect could point back into the private network we just rejected."""
    seen: list = []
    monkeypatch.setattr("krea_worker.image_source._resolve_public_host", lambda host: None)
    with pytest.raises(InputError, match="redirect"):
        fetch_image("https://cdn.example/r.png", "image",
                    session=_session(FakeResponse(status=302), seen))
    assert seen and seen[0][1].get("allow_redirects") is False


@pytest.mark.parametrize("url", [
    "http://127.0.0.1/a.png",
    "http://localhost/a.png",
    "http://10.0.0.5/a.png",
    "http://192.168.1.10/a.png",
    "http://169.254.169.254/latest/meta-data",
    "http://[::1]/a.png",
])
def test_refuses_addresses_inside_the_infrastructure(url: str) -> None:
    """The worker runs inside RunPod; a caller must not use it to reach in."""
    with pytest.raises(InputError, match="not allowed"):
        fetch_image(url, "image", session=_session(FakeResponse()))
