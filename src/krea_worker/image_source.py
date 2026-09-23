"""Accept reference images as URLs as well as base64.

Base64 inflates a payload by a third and forces the caller to buffer the whole
file, which is awkward for a service. A URL avoids both, but the worker runs
inside RunPod's network, so a caller must not be able to point it at addresses
that only the worker can reach.
"""

from __future__ import annotations

import ipaddress
import socket
from urllib.parse import urlparse

import requests

from .errors import InputError

ALLOWED_SCHEMES = ("http://", "https://")
DEFAULT_TIMEOUT = 20
CHUNK = 64 * 1024
# PNG, JPEG, WebP container - the same set the base64 path accepts.
_IMAGE_MAGIC = (
    bytes([137, 80, 78, 71, 13, 10, 26, 10]),
    bytes([255, 216, 255]),
    b"RIFF",
)


def looks_like_url(value: str) -> bool:
    return value.strip().lower().startswith(ALLOWED_SCHEMES)


def _resolve_public_host(host: str) -> None:
    """Reject hosts that resolve into the infrastructure's own network.

    Checked after resolution, not on the literal string: a name under the
    caller's control can point anywhere, including link-local metadata.
    """
    try:
        infos = socket.getaddrinfo(host, None)
    except socket.gaierror as exc:
        raise InputError(f"could not resolve host {host!r}") from exc

    for info in infos:
        address = ipaddress.ip_address(info[4][0])
        if (address.is_private or address.is_loopback or address.is_link_local
                or address.is_reserved or address.is_multicast
                or address.is_unspecified):
            raise InputError(f"address {address} is not allowed")


def fetch_image(
    url: str,
    name: str,
    session: object | None = None,
    max_bytes: int = 20 * 1024 * 1024,
    timeout: int = DEFAULT_TIMEOUT,
) -> bytes:
    """Download an image, refusing anything that is not one."""
    parsed = urlparse(url.strip())
    if not parsed.hostname:
        raise InputError(f"{name} is not a usable URL")
    _resolve_public_host(parsed.hostname)

    client = session if session is not None else requests
    try:
        response = client.get(url, stream=True, timeout=timeout, allow_redirects=False)
    except requests.RequestException as exc:
        raise InputError(f"could not fetch {name}: {exc}") from exc

    try:
        if 300 <= response.status_code < 400:
            # Following one would skip the address check above.
            raise InputError(f"{name} responded with a redirect; give a direct link")
        if response.status_code != 200:
            raise InputError(f"{name} responded with HTTP {response.status_code}")

        data = bytearray()
        for chunk in response.iter_content(CHUNK):
            data.extend(chunk)
            if len(data) > max_bytes:
                raise InputError(
                    f"{name} is larger than {max_bytes // (1024 * 1024)} MB"
                )
    finally:
        close = getattr(response, "close", None)
        if close:
            close()

    if not data:
        raise InputError(f"{name} downloaded as an empty file")
    if not bytes(data).startswith(_IMAGE_MAGIC):
        raise InputError(f"{name} is not a PNG, JPEG, or WebP image")
    return bytes(data)

def image_size(data: bytes) -> tuple[int, int]:
    """Pixel size of an encoded image. cv2 is imported lazily, as elsewhere."""
    import cv2
    import numpy as np

    frame = cv2.imdecode(np.frombuffer(data, dtype=np.uint8), cv2.IMREAD_COLOR)
    if frame is None:
        raise InputError("reference image could not be decoded")
    height, width = frame.shape[:2]
    return width, height
