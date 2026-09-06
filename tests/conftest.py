from __future__ import annotations

import json
from pathlib import Path

import pytest

from krea_worker.settings import Settings


def write_large(path: Path, size: int = 1024 * 1024 + 1) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("wb") as handle:
        handle.truncate(size)
    return path


@pytest.fixture
def settings(tmp_path: Path) -> Settings:
    model_root = tmp_path / "models"
    catalog_path = tmp_path / "lora_catalog.json"
    catalog_path.write_text(
        json.dumps({"schema_version": 1, "loras": {}}), encoding="utf-8"
    )
    manifest_path = tmp_path / "models.json"
    manifest_path.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "artifacts": [
                    {
                        "id": "unet",
                        "target": "diffusion_models/krea2_turbo_fp8_scaled.safetensors",
                        "min_bytes": 1024 * 1024,
                        "required": True,
                    },
                    {
                        "id": "text-encoder",
                        "target": "text_encoders/qwen3vl_4b_fp8_scaled.safetensors",
                        "min_bytes": 1024 * 1024,
                        "required": True,
                    },
                    {
                        "id": "vae",
                        "target": "vae/qwen_image_vae.safetensors",
                        "min_bytes": 1024 * 1024,
                        "required": True,
                    },
                ],
            }
        ),
        encoding="utf-8",
    )
    return Settings(
        comfy_host="127.0.0.1",
        comfy_port=8188,
        model_root=model_root,
        output_root=tmp_path / "output",
        catalog_path=catalog_path,
        manifest_path=manifest_path,
        unet_name="krea2_turbo_fp8_scaled.safetensors",
        text_encoder_name="qwen3vl_4b_fp8_scaled.safetensors",
        vae_name="qwen_image_vae.safetensors",
        model_shift=3.0,
        max_megapixels=2.1,
        max_total_megapixels=2.1,
        max_batch_size=2,
        max_loras=4,
        max_prompt_chars=6000,
        request_timeout_seconds=60,
        poll_interval_seconds=0.01,
        output_mode="base64",
        clean_outputs=True,
        debug_errors=False,
    )
