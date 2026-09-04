#!/usr/bin/env python3
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from krea_worker.errors import WorkerError  # noqa: E402
from krea_worker.service import KreaService  # noqa: E402


def main() -> int:
    try:
        result = KreaService().validate_runtime()
    except WorkerError as exc:
        print(json.dumps({"ok": False, "error": exc.as_dict()}, indent=2), file=sys.stderr)
        return 1
    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
