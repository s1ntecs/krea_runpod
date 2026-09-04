#!/usr/bin/env python3
from __future__ import annotations

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from krea_worker.service import KreaService  # noqa: E402


def as_bool(value: str) -> bool:
    return value.strip().lower() in {"1", "true", "yes", "on"}


def main() -> int:
    names_raw = os.getenv("WARMUP_LORAS", os.getenv("PRELOAD_LORAS", "realism"))
    names = [item.strip() for item in names_raw.split(",") if item.strip()] or ["none"]
    strict = as_bool(os.getenv("WARMUP_STRICT", "false"))
    service = KreaService()
    for index, name in enumerate(names, start=1):
        payload = {
            "prompt": "A simple studio photograph of a red ceramic mug on a gray table",
            "width": int(os.getenv("WARMUP_WIDTH", "512")),
            "height": int(os.getenv("WARMUP_HEIGHT", "512")),
            "steps": int(os.getenv("WARMUP_STEPS", "1")),
            "cfg": 1.0,
            "seed": 1,
            "output_mode": "path",
            "filename_prefix": "warmup",
        }
        if name.lower() != "none":
            payload["lora"] = name
        try:
            result = service.generate(payload, f"warmup-{index}-{name}")
            for image in result.get("images", []):
                if image.get("path"):
                    Path(image["path"]).unlink(missing_ok=True)
            print(f"Warmup completed for {name}")
        except Exception as exc:
            print(f"Warmup failed for {name}: {exc}", file=sys.stderr)
            if strict:
                return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
