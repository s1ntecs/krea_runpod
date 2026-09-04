#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os

import requests


def main() -> int:
    parser = argparse.ArgumentParser(description="Run a synchronous test against RunPod Serverless")
    parser.add_argument("--endpoint-id", default=os.getenv("RUNPOD_ENDPOINT_ID"))
    parser.add_argument("--api-key", default=os.getenv("RUNPOD_API_KEY"))
    parser.add_argument("--lora", default="realism")
    parser.add_argument("--timeout", type=int, default=1200)
    args = parser.parse_args()
    if not args.endpoint_id or not args.api_key:
        parser.error("--endpoint-id and --api-key (or env vars) are required")

    response = requests.post(
        f"https://api.runpod.ai/v2/{args.endpoint_id}/runsync",
        headers={"Authorization": f"Bearer {args.api_key}"},
        json={"input": {
            "prompt": "A candid photograph of a barista making coffee in a small sunlit cafe",
            "width": 1024,
            "height": 1024,
            "steps": 8,
            "seed": 42,
            "lora": args.lora,
        }},
        timeout=args.timeout,
    )
    print(json.dumps(response.json(), indent=2, ensure_ascii=False))
    return 0 if response.ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
