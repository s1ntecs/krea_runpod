from __future__ import annotations

import json
from pathlib import Path

import pytest

from krea_worker.errors import LoraError
from krea_worker.lora_registry import LoraRegistry
from conftest import write_large


def test_resolves_catalog_alias_and_custom_filename(tmp_path: Path) -> None:
    lora_root = tmp_path / "loras"
    write_large(lora_root / "krea2_realism_lora.safetensors")
    write_large(lora_root / "custom" / "my_style.safetensors")
    catalog = tmp_path / "catalog.json"
    catalog.write_text(
        json.dumps(
            {
                "loras": {
                    "realism": {
                        "file": "krea2_realism_lora.safetensors",
                        "default_strength": 0.9,
                        "trigger": "",
                    }
                }
            }
        ),
        encoding="utf-8",
    )
    registry = LoraRegistry(lora_root, catalog, max_loras=4)

    realism = registry.resolve("realism")[0]
    assert realism.file == "krea2_realism_lora.safetensors"
    assert realism.strength == 0.9
    assert realism.registered is True

    custom = registry.resolve({"name": "my_style", "strength": 0.7, "trigger": "mystyle"})[0]
    assert custom.file == "custom/my_style.safetensors"
    assert custom.strength == 0.7
    assert custom.trigger == "mystyle"
    assert custom.registered is False


def test_rejects_path_traversal(tmp_path: Path) -> None:
    registry = LoraRegistry(tmp_path / "loras", tmp_path / "missing.json")
    with pytest.raises(LoraError, match="Unsafe"):
        registry.resolve("../secret.safetensors")


def test_ambiguous_basename_requires_relative_path(tmp_path: Path) -> None:
    lora_root = tmp_path / "loras"
    write_large(lora_root / "a" / "same.safetensors")
    write_large(lora_root / "b" / "same.safetensors")
    registry = LoraRegistry(lora_root, tmp_path / "missing.json")

    with pytest.raises(LoraError, match="ambiguous"):
        registry.resolve("same")
    resolved = registry.resolve("a/same.safetensors")[0]
    assert resolved.file == "a/same.safetensors"


def test_rejects_lfs_pointer_sized_file(tmp_path: Path) -> None:
    lora_root = tmp_path / "loras"
    path = lora_root / "broken.safetensors"
    path.parent.mkdir(parents=True)
    path.write_text("version https://git-lfs.github.com/spec/v1", encoding="utf-8")
    registry = LoraRegistry(lora_root, tmp_path / "missing.json")

    with pytest.raises(LoraError, match="incomplete"):
        registry.resolve("broken")


def test_parses_append_trigger_boolean_and_rejects_nan(tmp_path: Path) -> None:
    lora_root = tmp_path / "loras"
    write_large(lora_root / "style.safetensors")
    registry = LoraRegistry(lora_root, tmp_path / "missing.json")

    resolved = registry.resolve(
        {"name": "style", "append_trigger": "false", "trigger": "example"}
    )[0]
    assert resolved.append_trigger is False

    with pytest.raises(LoraError, match="finite"):
        registry.resolve({"name": "style", "strength": "nan"})
