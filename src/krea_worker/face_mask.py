"""Find the face in a reference image and draw the ref_boost mask for it.

Drawing a mask by hand is fine for one-off experiments but not for a service,
so the worker can produce it itself. The mask is a soft-edged ellipse over the
head: ref_boost then pins the face while body and pose stay free to change.

The PNG is assembled here rather than through an imaging library - the format
needed is a single greyscale channel, and writing it directly keeps the worker
free of another dependency.
"""

from __future__ import annotations

import math
import os
import struct
import zlib
from dataclasses import dataclass

# YuNet's ONNX file, baked into the image by the Dockerfile.
MODEL_PATH = os.getenv("FACE_DETECTOR_MODEL", "/opt/krea/assets/face_detection_yunet.onnx")
# Below this the detector starts reporting hands and shoulders as faces.
SCORE_THRESHOLD = 0.6

# The detector's box stops at the jaw and hairline; ref_boost works better with
# the whole head, so the ellipse is grown by this fraction of the box.
DEFAULT_MARGIN = 0.25
# Width of the soft edge, as a fraction of the ellipse radius. A hard edge
# shows up as a visible seam in the result.
FEATHER = 0.15


@dataclass(frozen=True)
class FaceBox:
    x: int
    y: int
    width: int
    height: int

    @property
    def area(self) -> int:
        return self.width * self.height


def largest_face(faces: list[FaceBox]) -> FaceBox | None:
    """The biggest face is the subject; smaller ones are bystanders."""
    return max(faces, key=lambda f: f.area, default=None)


def _png_grey(width: int, height: int, rows: list[bytearray]) -> bytes:
    def chunk(typ: bytes, data: bytes) -> bytes:
        return (struct.pack(">I", len(data)) + typ + data
                + struct.pack(">I", zlib.crc32(typ + data) & 0xFFFFFFFF))

    ihdr = struct.pack(">IIBBBBB", width, height, 8, 0, 0, 0, 0)
    raw = b"".join(b"\x00" + bytes(row) for row in rows)
    return (bytes([137, 80, 78, 71, 13, 10, 26, 10])
            + chunk(b"IHDR", ihdr)
            + chunk(b"IDAT", zlib.compress(raw, 6))
            + chunk(b"IEND", b""))


def build_mask_png(
    width: int,
    height: int,
    face: FaceBox,
    margin: float = DEFAULT_MARGIN,
    feather: float = FEATHER,
) -> bytes:
    """White ellipse over the face on black, sized to the source image."""
    if face.width <= 0 or face.height <= 0:
        raise ValueError("face box has no area")
    if face.x >= width or face.y >= height or face.x + face.width <= 0 or face.y + face.height <= 0:
        raise ValueError("face box lies outside the image")

    cx = face.x + face.width / 2
    cy = face.y + face.height / 2
    rx = face.width / 2 * (1 + margin)
    ry = face.height / 2 * (1 + margin)

    rows = [bytearray(width) for _ in range(height)]
    # Only the ellipse's bounding box can be non-zero, so the rest of the image
    # is left as the zeros it was allocated with.
    y0, y1 = max(0, int(cy - ry) - 1), min(height, int(cy + ry) + 2)
    x0, x1 = max(0, int(cx - rx) - 1), min(width, int(cx + rx) + 2)
    inner = max(0.0, 1.0 - feather)

    for y in range(y0, y1):
        dy = (y + 0.5 - cy) / ry
        dy2 = dy * dy
        row = rows[y]
        for x in range(x0, x1):
            dx = (x + 0.5 - cx) / rx
            dist = math.sqrt(dx * dx + dy2)
            if dist <= inner:
                row[x] = 255
            elif dist < 1.0:
                row[x] = int(255 * (1.0 - dist) / (1.0 - inner))
    return _png_grey(width, height, rows)


def _decode(image: bytes):
    """Decode to a BGR array. cv2 is imported lazily - only auto masks need it."""
    import cv2
    import numpy as np

    frame = cv2.imdecode(np.frombuffer(image, dtype=np.uint8), cv2.IMREAD_COLOR)
    if frame is None:
        raise ValueError("reference image could not be decoded")
    return frame


def detect_faces(image: bytes, model_path: str = MODEL_PATH) -> list[FaceBox]:
    """Locate faces with OpenCV's YuNet. Empty list when it finds none.

    YuNet rather than MediaPipe: the latter pulls in jaxlib, which has no wheel
    for the worker's platform. YuNet ships as a 230KB ONNX file and its detector
    is part of OpenCV itself.
    """
    import cv2

    frame = _decode(image)
    height, width = frame.shape[:2]
    detector = cv2.FaceDetectorYN.create(model_path, "", (width, height), SCORE_THRESHOLD, 0.3, 5000)
    _count, raw = detector.detect(frame)

    faces: list[FaceBox] = []
    for row in raw if raw is not None else []:
        x, y, w, h = (int(v) for v in row[:4])
        # Boxes can spill past the frame on faces at the edge; clamp them.
        x, y = max(0, x), max(0, y)
        w, h = min(w, width - x), min(h, height - y)
        if w > 0 and h > 0:
            faces.append(FaceBox(x, y, w, h))
    return faces


def auto_face_mask(image: bytes, model_path: str = MODEL_PATH) -> tuple[bytes | None, int]:
    """Mask for the biggest face in the image, plus how many faces were seen."""
    faces = detect_faces(image, model_path)
    face = largest_face(faces)
    if face is None:
        return None, 0
    frame = _decode(image)
    height, width = frame.shape[:2]
    return build_mask_png(width, height, face), len(faces)
