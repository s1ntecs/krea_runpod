from __future__ import annotations

import json
import math
from dataclasses import asdict, dataclass
from pathlib import Path, PurePosixPath
from typing import Any

from .errors import LoraError

# Some Krea 2 utility LoRAs intentionally contain only a handful of tensors and
# are measured in bytes or kilobytes rather than megabytes. Size alone is not a
# useful integrity check, but keeping a tiny floor still rejects empty/truncated
# files. Git LFS pointers are detected explicitly below.
_MIN_LORA_BYTES = 128
_GIT_LFS_SIGNATURE = b"version https://git-lfs.github.com/spec/v1"


@dataclass(frozen=True)
class ResolvedLora:
    requested_name: str
    file: str
    strength: float
    trigger: str
    append_trigger: bool
    registered: bool

    def public_dict(self) -> dict:
        return asdict(self)


class LoraRegistry:
    """Resolves catalog aliases and arbitrary LoRA files stored on the network volume."""

    def __init__(self, lora_root: Path, catalog_path: Path, max_loras: int = 4) -> None:
        self.lora_root = lora_root
        self.catalog_path = catalog_path
        self.max_loras = max_loras

    def _catalog(self) -> dict[str, dict]:
        if not self.catalog_path.exists():
            return {}
        try:
            data = json.loads(self.catalog_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise LoraError(f"Cannot read LoRA catalog: {self.catalog_path}") from exc
        loras = data.get("loras", {})
        if not isinstance(loras, dict):
            raise LoraError("LoRA catalog field 'loras' must be an object")
        return {str(k).lower(): v for k, v in loras.items() if isinstance(v, dict)}

    @staticmethod
    def _safe_relative(value: str) -> str:
        normalized = value.replace("\\", "/").strip()
        path = PurePosixPath(normalized)
        if not normalized or path.is_absolute() or ".." in path.parts:
            raise LoraError(f"Unsafe LoRA name/path: {value!r}")
        return path.as_posix()

    @staticmethod
    def _usable_lora_file(path: Path) -> bool:
        try:
            if not path.is_file() or path.stat().st_size < _MIN_LORA_BYTES:
                return False
            with path.open("rb") as handle:
                prefix = handle.read(len(_GIT_LFS_SIGNATURE))
            return not prefix.startswith(_GIT_LFS_SIGNATURE)
        except OSError:
            return False

    def _installed(self) -> dict[str, Path]:
        if not self.lora_root.exists():
            return {}
        installed: dict[str, Path] = {}
        root = self.lora_root.resolve()
        for path in sorted(self.lora_root.rglob("*.safetensors")):
            if not path.is_file():
                continue
            resolved = path.resolve()
            if root not in resolved.parents:
                continue
            relative = path.relative_to(self.lora_root).as_posix()
            installed[relative] = path
        return installed

    @staticmethod
    def _build_lookup(installed: dict[str, Path]) -> dict[str, str | None]:
        lookup: dict[str, str | None] = {}
        for relative in installed:
            candidates = {
                relative.lower(),
                Path(relative).name.lower(),
                Path(relative).stem.lower(),
            }
            for candidate in candidates:
                if candidate in lookup and lookup[candidate] != relative:
                    lookup[candidate] = None
                else:
                    lookup[candidate] = relative
        return lookup

    def _resolve_file(self, requested: str, installed: dict[str, Path]) -> str:
        safe = self._safe_relative(requested)
        lookup = self._build_lookup(installed)
        key = safe.lower()
        relative = lookup.get(key)
        if relative is None and key in lookup:
            raise LoraError(
                f"LoRA name '{requested}' is ambiguous; use its relative path under models/loras"
            )
        if relative is None and not safe.lower().endswith(".safetensors"):
            relative = lookup.get(f"{safe}.safetensors".lower())
        if relative is None:
            available = sorted(installed)[:50]
            raise LoraError(
                f"LoRA '{requested}' was not found in {self.lora_root}",
                details={"available_files": available},
            )
        path = installed[relative]
        if not self._usable_lora_file(path):
            raise LoraError(
                f"LoRA file looks incomplete or is a Git LFS pointer: {relative}",
                details={"size_bytes": path.stat().st_size},
            )
        return relative

    @staticmethod
    def _as_bool(value: Any, name: str) -> bool:
        if isinstance(value, bool):
            return value
        if isinstance(value, int) and value in {0, 1}:
            return bool(value)
        if isinstance(value, str):
            normalized = value.strip().lower()
            if normalized in {"1", "true", "yes", "on"}:
                return True
            if normalized in {"0", "false", "no", "off"}:
                return False
        raise LoraError(f"{name} must be a boolean")

    @staticmethod
    def _normalize_specs(raw: Any) -> list[dict]:
        if raw is None or raw == "" or raw == []:
            return []
        values = raw if isinstance(raw, list) else [raw]
        specs: list[dict] = []
        for value in values:
            if isinstance(value, str):
                specs.append({"name": value})
            elif isinstance(value, dict):
                specs.append(dict(value))
            else:
                raise LoraError("Each LoRA must be a string or an object")
        return specs

    @staticmethod
    def _strength_bounds(entry: dict | None, name: str) -> tuple[float, float]:
        raw_min = entry.get("min_strength", -2.0) if entry else -2.0
        raw_max = entry.get("max_strength", 2.0) if entry else 2.0
        try:
            minimum = float(raw_min)
            maximum = float(raw_max)
        except (TypeError, ValueError) as exc:
            raise LoraError(f"Invalid strength bounds in catalog for LoRA '{name}'") from exc
        if not math.isfinite(minimum) or not math.isfinite(maximum) or minimum > maximum:
            raise LoraError(f"Invalid strength bounds in catalog for LoRA '{name}'")
        return minimum, maximum

    def resolve(self, raw: Any) -> list[ResolvedLora]:
        specs = self._normalize_specs(raw)
        if len(specs) > self.max_loras:
            raise LoraError(f"At most {self.max_loras} LoRAs can be used in one request")

        catalog = self._catalog()
        installed = self._installed()
        resolved: list[ResolvedLora] = []
        seen: set[str] = set()

        for spec in specs:
            name = spec.get("name", spec.get("lora_name", spec.get("file")))
            if not isinstance(name, str) or not name.strip():
                raise LoraError("LoRA object requires a non-empty 'name'")
            name = name.strip()
            if name.lower() in {"none", "off", "false"}:
                continue

            catalog_entry = catalog.get(name.lower())
            registered = catalog_entry is not None
            if registered:
                file_value = catalog_entry.get("file")
                if not isinstance(file_value, str) or not file_value.strip():
                    raise LoraError(f"Catalog entry '{name}' has no valid file")
                file_hint = file_value
            else:
                file_hint = name
            relative = self._resolve_file(file_hint, installed)

            default_strength = catalog_entry.get("default_strength", 1.0) if registered else 1.0
            try:
                strength = float(spec.get("strength", spec.get("scale", default_strength)))
            except (TypeError, ValueError) as exc:
                raise LoraError(f"Invalid strength for LoRA '{name}'") from exc
            if not math.isfinite(strength):
                raise LoraError(f"LoRA strength for '{name}' must be finite")
            minimum, maximum = self._strength_bounds(catalog_entry, name)
            if strength < minimum or strength > maximum:
                raise LoraError(
                    f"LoRA strength for '{name}' must be between {minimum:g} and {maximum:g}"
                )

            trigger_default = str(catalog_entry.get("trigger", "")) if registered else ""
            trigger = str(spec.get("trigger", spec.get("trigger_word", trigger_default))).strip()
            if len(trigger) > 300:
                raise LoraError(f"Trigger word for '{name}' is too long")
            append_trigger = self._as_bool(
                spec.get("append_trigger", True), f"append_trigger for LoRA '{name}'"
            )

            if relative.lower() in seen:
                raise LoraError(f"LoRA '{relative}' is listed more than once")
            seen.add(relative.lower())
            resolved.append(
                ResolvedLora(
                    requested_name=name,
                    file=relative,
                    strength=strength,
                    trigger=trigger,
                    append_trigger=append_trigger,
                    registered=registered,
                )
            )
        return resolved

    def list_available(self) -> list[dict]:
        catalog = self._catalog()
        installed = self._installed()
        installed_lower = {name.lower(): path for name, path in installed.items()}
        by_file = {
            str(entry.get("file", "")).lower(): alias
            for alias, entry in catalog.items()
        }
        result: list[dict] = []

        for alias, entry in sorted(catalog.items()):
            file_name = str(entry.get("file", ""))
            path = installed_lower.get(file_name.lower())
            minimum, maximum = self._strength_bounds(entry, alias)
            result.append(
                {
                    "name": alias,
                    "file": file_name,
                    "installed": bool(path and self._usable_lora_file(path)),
                    "size_bytes": path.stat().st_size if path else None,
                    "default_strength": entry.get("default_strength", 1.0),
                    "min_strength": minimum,
                    "max_strength": maximum,
                    "trigger": entry.get("trigger", ""),
                    "description": entry.get("description", ""),
                    "source": entry.get("source", ""),
                    "license": entry.get("license", ""),
                    "registered": True,
                }
            )

        for relative, path in sorted(installed.items()):
            if relative.lower() in by_file:
                continue
            result.append(
                {
                    "name": relative,
                    "file": relative,
                    "installed": self._usable_lora_file(path),
                    "size_bytes": path.stat().st_size,
                    "default_strength": 1.0,
                    "min_strength": -2.0,
                    "max_strength": 2.0,
                    "trigger": "",
                    "description": "LoRA discovered on the network volume",
                    "source": "",
                    "license": "unknown; verify before use",
                    "registered": False,
                }
            )
        return result
