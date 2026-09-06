from __future__ import annotations

import math
import secrets
from dataclasses import dataclass
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
