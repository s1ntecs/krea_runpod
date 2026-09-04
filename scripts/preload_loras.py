#!/usr/bin/env python3
from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from krea_worker.lora_registry import LoraRegistry  # noqa: E402


def parse_bool(value: str) -> bool:
    return value.strip().lower() in {"1", "true", "yes", "on"}


def main() -> int:
    parser = argparse.ArgumentParser(description="Read selected LoRAs into the Linux page cache")
    parser.add_argument("--names", default=os.getenv("PRELOAD_LORAS", "realism,darkbrush"))
    parser.add_argument("--model-root", default=os.getenv("MODEL_ROOT", "/runpod-volume/models"))
    parser.add_argument("--catalog", default=os.getenv("LORA_CATALOG", str(ROOT / "config/lora_catalog.json")))
    parser.add_argument("--chunk-mb", type=int, default=32)
    args = parser.parse_args()

    names = [item.strip() for item in args.names.split(",") if item.strip()]
    if not names:
        print("No LoRAs selected for preload")
        return 0
    strict = parse_bool(os.getenv("PRELOAD_STRICT", "false"))
    registry = LoraRegistry(Path(args.model_root) / "loras", Path(args.catalog), max_loras=64)
    chunk_size = max(1, args.chunk_mb) * 1024 * 1024
    failures = 0
    for name in names:
        try:
            lora = registry.resolve(name)[0]
            path = Path(args.model_root) / "loras" / lora.file
            read_bytes = 0
            print(f"Preloading {lora.requested_name}: {path} ({path.stat().st_size:,} bytes)")
            with path.open("rb", buffering=0) as handle:
                while chunk := handle.read(chunk_size):
                    read_bytes += len(chunk)
            print(f"Preloaded {lora.requested_name}: {read_bytes:,} bytes")
        except Exception as exc:
            failures += 1
            print(f"LoRA preload skipped for {name}: {exc}", file=sys.stderr)
            if strict:
                return 1
    return 1 if failures and strict else 0


if __name__ == "__main__":
    raise SystemExit(main())
