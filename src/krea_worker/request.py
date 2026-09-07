from __future__ import annotations

import base64
import binascii
import math
import re
import secrets
from dataclasses import dataclass, replace
from typing import Any

from .errors import InputError
from .settings import Settings

ALLOWED_SAMPLERS = {
    "euler",
    "euler_ancestral",
    "dpmpp_2m",
    "dpmpp_2m_sde",
    "heun",
}
ALLOWED_SCHEDULERS = {"beta", "simple", "normal", "sgm_uniform"}

# Defaults taken from the workflow shipped with comfyui-krea2edit; they are the
# configuration the Krea 2 Identity Edit weights are actually run with.
EDIT_DEFAULT_STEPS = 10
EDIT_DEFAULT_CFG = 1.0
EDIT_DEFAULT_SCHEDULER = "simple"
EDIT_DEFAULT_GROUNDING_PX = 768
EDIT_DEFAULT_REF_BOOST = 4.0
MAX_EDIT_IMAGES = 2
MAX_SYSTEM_PROMPT_CHARS = 4000

# Krea2EditGroundedEncode feeds Qwen3-VL a system line before the instruction.
# Its default asks about objects and background and never mentions people, so
# identity work benefits from steering the vision encoder at the face instead.
FACE_SYSTEM_PROMPT = (
    "Describe the person in the image by detailing their facial identity: face "
    "shape, eye shape and colour, eyebrows, nose, mouth, jawline, skin tone and "
    "texture, moles and marks, hairline and hair texture, together with the "
    "colour, shape, size, texture and spatial relationships of the objects and "
    "background:"
)

# Values for likeness work: grounding at 1024 (the README's suggestion for
# people) and ref_boost at 4.0, which the model card calls the setting that
# "gives strong face/body likeness" and which the shipped workflow uses. Lower
# values loosen toward creative freedom - 1.75 is a close-up portrait tip for
# keeping the face from looking frozen, not a way to maximise likeness.
FACE_PRESET = {"grounding_px": 1024, "ref_boost": 4.0, "steps": 12}
MAX_EDIT_IMAGE_BYTES = 20 * 1024 * 1024
_DATA_URI = re.compile(r"^data:image/[a-zA-Z0-9.+-]+;base64,")
_IMAGE_MAGIC = (
    bytes([137, 80, 78, 71, 13, 10, 26, 10]),  # PNG
    bytes([255, 216, 255]),                    # JPEG
    b"RIFF",                                   # WebP container
)


def _as_int(value: Any, name: str) -> int:
    if isinstance(value, bool):
        raise InputError(f"{name} must be an integer")
    if isinstance(value, float):
        if not math.isfinite(value) or not value.is_integer():
            raise InputError(f"{name} must be an integer")
    try:
        return int(value)
    except (TypeError, ValueError, OverflowError) as exc:
        raise InputError(f"{name} must be an integer") from exc


def _as_float(value: Any, name: str) -> float:
    if isinstance(value, bool):
        raise InputError(f"{name} must be a number")
    try:
        result = float(value)
    except (TypeError, ValueError, OverflowError) as exc:
        raise InputError(f"{name} must be a number") from exc
    if not math.isfinite(result):
        raise InputError(f"{name} must be a finite number")
    return result


def _dimension(value: Any, name: str) -> int:
    result = _as_int(value, name)
    if result < 256 or result > 2048:
        raise InputError(f"{name} must be between 256 and 2048")
    if result % 16 != 0:
        raise InputError(f"{name} must be divisible by 16", details={name: result})
    return result


@dataclass(frozen=True)
class GenerationRequest:
    prompt: str
    negative_prompt: str
    width: int
    height: int
    batch_size: int
    seed: int
    steps: int
    cfg: float
    sampler_name: str
    scheduler: str
    loras: Any
    output_mode: str | None
    filename_prefix: str
    images: tuple = ()
    grounding_px: int = EDIT_DEFAULT_GROUNDING_PX
    ref_boost: float = EDIT_DEFAULT_REF_BOOST
    ref_boost_a: float = 1.0
    system_prompt: str = ""
    ref_boost_mask: bytes | None = None

    @classmethod
    def parse(cls, payload: dict, settings: Settings) -> "GenerationRequest":
        if not isinstance(payload, dict):
            raise InputError("input must be a JSON object")

        prompt = payload.get("prompt")
        if not isinstance(prompt, str) or not prompt.strip():
            raise InputError("prompt is required and must be a non-empty string")
        prompt = prompt.strip()
        if len(prompt) > settings.max_prompt_chars:
            raise InputError(
                f"prompt exceeds {settings.max_prompt_chars} characters",
                details={"length": len(prompt)},
            )

        negative = payload.get("negative_prompt", "")
        if not isinstance(negative, str):
            raise InputError("negative_prompt must be a string")
        if len(negative) > 3000:
            raise InputError("negative_prompt exceeds 3000 characters")

        width = _dimension(payload.get("width", 1024), "width")
        height = _dimension(payload.get("height", 1024), "height")
        megapixels = width * height / 1_000_000
        if megapixels > settings.max_megapixels:
            raise InputError(
                f"requested image is {megapixels:.2f} MP; "
                f"per-image limit is {settings.max_megapixels:.2f} MP",
                details={"width": width, "height": height},
            )

        batch_size = _as_int(
            payload.get("num_images", payload.get("batch_size", 1)), "num_images"
        )
        if batch_size < 1 or batch_size > settings.max_batch_size:
            raise InputError(
                f"num_images must be between 1 and {settings.max_batch_size}"
            )
        total_megapixels = megapixels * batch_size
        if total_megapixels > settings.max_total_megapixels:
            raise InputError(
                f"batch is {total_megapixels:.2f} MP; total batch limit is "
                f"{settings.max_total_megapixels:.2f} MP",
                details={
                    "width": width,
                    "height": height,
                    "num_images": batch_size,
                },
            )

        seed = _as_int(payload.get("seed", -1), "seed")
        if seed < 0:
            seed = secrets.randbits(63)
        if seed > 2**63 - 1:
            raise InputError("seed must be <= 9223372036854775807")

        steps = _as_int(payload.get("steps", 8), "steps")
        if steps < 1 or steps > 30:
            raise InputError("steps must be between 1 and 30")

        cfg = _as_float(payload.get("cfg", 1.0), "cfg")
        if cfg < 0 or cfg > 10:
            raise InputError("cfg must be between 0 and 10")

        sampler = str(payload.get("sampler_name", "euler")).strip().lower()
        if sampler not in ALLOWED_SAMPLERS:
            raise InputError(
                f"unsupported sampler_name '{sampler}'",
                details={"allowed": sorted(ALLOWED_SAMPLERS)},
            )
        scheduler = str(payload.get("scheduler", "beta")).strip().lower()
        if scheduler not in ALLOWED_SCHEDULERS:
            raise InputError(
                f"unsupported scheduler '{scheduler}'",
                details={"allowed": sorted(ALLOWED_SCHEDULERS)},
            )

        output_mode = payload.get("output_mode")
        if output_mode is not None:
            output_mode = str(output_mode).strip().lower()
            if output_mode not in {"auto", "base64", "s3", "path"}:
                raise InputError("output_mode must be auto, base64, s3, or path")

        prefix = str(payload.get("filename_prefix", "krea2")).strip() or "krea2"
        prefix = "".join(ch for ch in prefix if ch.isalnum() or ch in "-_")[:40]
        prefix = prefix or "krea2"

        loras = payload.get(
            "loras", payload.get("lora", payload.get("lora_name"))
        )
        if isinstance(loras, str) and any(
            key in payload for key in ("lora_strength", "lora_trigger", "append_trigger")
        ):
            loras = {
                "name": loras,
                "strength": payload.get("lora_strength", 1.0),
                "trigger": payload.get("lora_trigger", ""),
                "append_trigger": payload.get("append_trigger", True),
            }
        return cls(
            prompt=prompt,
            negative_prompt=negative.strip(),
            width=width,
            height=height,
            batch_size=batch_size,
            seed=seed,
            steps=steps,
            cfg=cfg,
            sampler_name=sampler,
            scheduler=scheduler,
            loras=loras,
            output_mode=output_mode,
            filename_prefix=prefix,
        )

    @staticmethod
    def _decode_image(value: Any, name: str) -> bytes:
        if not isinstance(value, str) or not value.strip():
            raise InputError(f"{name} must be a base64-encoded image")
        payload = _DATA_URI.sub("", value.strip())
        try:
            data = base64.b64decode(payload, validate=True)
        except (binascii.Error, ValueError) as exc:
            raise InputError(f"{name} is not valid base64") from exc
        if not data:
            raise InputError(f"{name} decoded to an empty image")
        if len(data) > MAX_EDIT_IMAGE_BYTES:
            raise InputError(
                f"{name} is larger than {MAX_EDIT_IMAGE_BYTES // (1024 * 1024)} MB"
            )
        if not data.startswith(_IMAGE_MAGIC):
            raise InputError(f"{name} is not a PNG, JPEG, or WebP image")
        return data

    @classmethod
    def parse_edit(cls, payload: dict, settings: Settings) -> "GenerationRequest":
        """Parses an instruction-edit request for the Krea 2 Identity Edit workflow."""
        if not isinstance(payload, dict):
            raise InputError("input must be a JSON object")

        raw = payload.get("images")
        if raw is None:
            raw = [payload.get(key) for key in ("image", "image_b")]
            raw = [item for item in raw if item is not None]
        if not isinstance(raw, list):
            raise InputError("images must be an array of base64-encoded images")
        if not raw:
            raise InputError(
                "edit requires a reference image in 'image' (or 'images')"
            )
        if len(raw) > MAX_EDIT_IMAGES:
            raise InputError(
                f"edit accepts at most {MAX_EDIT_IMAGES} reference images; "
                "training order is scene first, subject second"
            )
        names = ("image", "image_b")
        images = tuple(
            cls._decode_image(item, names[index]) for index, item in enumerate(raw)
        )

        # `preset: "face"` moves the defaults to the settings recommended for
        # likeness work; anything named explicitly in the payload still wins.
        preset = str(payload.get("preset", "")).strip().lower()
        if preset and preset != "face":
            raise InputError(
                f"unknown preset '{preset}'", details={"allowed": ["face"]}
            )
        defaults_for = FACE_PRESET if preset == "face" else {}

        raw_system = payload.get("system_prompt")
        if raw_system is None and preset == "face":
            raw_system = "face"
        system_prompt = "" if raw_system is None else str(raw_system).strip()
        if system_prompt.lower() == "face":
            system_prompt = FACE_SYSTEM_PROMPT
        if len(system_prompt) > MAX_SYSTEM_PROMPT_CHARS:
            raise InputError(
                f"system_prompt must be at most {MAX_SYSTEM_PROMPT_CHARS} characters"
            )

        grounding_px = _as_int(
            payload.get(
                "grounding_px",
                defaults_for.get("grounding_px", EDIT_DEFAULT_GROUNDING_PX),
            ),
            "grounding_px",
        )
        if grounding_px < 0 or grounding_px > 4096:
            raise InputError("grounding_px must be between 0 and 4096")

        # A mask restricts ref_boost to part of the reference - typically the
        # face, so likeness stays pinned while the body and pose stay free.
        raw_mask = payload.get("ref_boost_mask")
        ref_boost_mask = (
            None if raw_mask is None else cls._decode_image(raw_mask, "ref_boost_mask")
        )

        ref_boost = _as_float(
            payload.get(
                "ref_boost", defaults_for.get("ref_boost", EDIT_DEFAULT_REF_BOOST)
            ),
            "ref_boost",
        )
        ref_boost_a = _as_float(payload.get("ref_boost_a", 1.0), "ref_boost_a")
        for name, value in (("ref_boost", ref_boost), ("ref_boost_a", ref_boost_a)):
            if value < 0 or value > 1000:
                raise InputError(f"{name} must be between 0 and 1000")

        defaults = {
            "steps": defaults_for.get("steps", EDIT_DEFAULT_STEPS),
            "cfg": EDIT_DEFAULT_CFG,
            "scheduler": EDIT_DEFAULT_SCHEDULER,
        }
        base = cls.parse({**defaults, **payload}, settings)
        return replace(
            base,
            images=images,
            grounding_px=grounding_px,
            ref_boost=ref_boost,
            ref_boost_a=ref_boost_a,
            system_prompt=system_prompt,
            ref_boost_mask=ref_boost_mask,
        )
