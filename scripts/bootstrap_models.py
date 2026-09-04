#!/usr/bin/env python3
from __future__ import annotations

import argparse
import fcntl
import hashlib
import json
import os
import shutil
import sys
from contextlib import contextmanager
from pathlib import Path, PurePosixPath

from huggingface_hub import hf_hub_download


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Download Krea 2 artifacts into a RunPod Network Volume"
    )
    parser.add_argument(
        "--model-root", default=os.getenv("MODEL_ROOT", "/runpod-volume/models")
    )
    parser.add_argument(
        "--manifest", default=os.getenv("MODEL_MANIFEST", "config/models.json")
    )
    parser.add_argument(
        "--groups", default=os.getenv("DOWNLOAD_GROUPS", "core,starter-loras")
    )
    parser.add_argument("--only", default="", help="Comma-separated artifact IDs")
    parser.add_argument("--verify-only", action="store_true")
    parser.add_argument(
        "--verify-sha256",
        action="store_true",
        help="Hash existing files too (new downloads are always hash-verified)",
    )
    parser.add_argument("--dry-run", action="store_true")
    return parser.parse_args()


def safe_target(root: Path, relative: str) -> Path:
    normalized = relative.replace("\\", "/").strip()
    posix = PurePosixPath(normalized)
    if not normalized or posix.is_absolute() or ".." in posix.parts:
        raise ValueError(f"Unsafe target path in manifest: {relative}")
    target = (root / Path(*posix.parts)).resolve()
    root_resolved = root.resolve()
    if root_resolved not in target.parents:
        raise ValueError(f"Target escapes model root: {relative}")
    return target


@contextmanager
def volume_lock(model_root: Path):
    lock_dir = model_root.parent / ".locks"
    lock_dir.mkdir(parents=True, exist_ok=True)
    lock_path = lock_dir / "krea2-model-bootstrap.lock"
    with lock_path.open("w") as handle:
        print(f"Waiting for volume lock: {lock_path}", flush=True)
        fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
        print("Volume lock acquired", flush=True)
        try:
            yield
        finally:
            fcntl.flock(handle.fileno(), fcntl.LOCK_UN)


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while chunk := handle.read(16 * 1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def valid_file(
    path: Path,
    min_bytes: int,
    expected_sha256: str | None = None,
    verify_hash: bool = False,
) -> bool:
    if not path.is_file() or path.stat().st_size < min_bytes:
        return False
    if verify_hash and expected_sha256:
        print(f"HASH    {path}", flush=True)
        return sha256_file(path).lower() == expected_sha256.lower()
    return True


def selected_artifacts(manifest: dict, groups: set[str], only: set[str]) -> list[dict]:
    result = []
    artifacts = manifest.get("artifacts", [])
    if not isinstance(artifacts, list):
        raise ValueError("Manifest field 'artifacts' must be an array")
    for artifact in artifacts:
        if not isinstance(artifact, dict):
            continue
        artifact_id = str(artifact.get("id", ""))
        if only:
            selected = artifact_id in only
        else:
            selected = bool(artifact.get("required")) or artifact.get("group") in groups
        if selected:
            result.append(artifact)
    return result


def verify_download(artifact: dict, path: Path) -> None:
    expected = str(artifact.get("sha256", "")).strip().lower()
    if not expected:
        return
    print(f"HASH    {artifact['id']}: {path}", flush=True)
    actual = sha256_file(path)
    if actual != expected:
        raise RuntimeError(
            f"SHA256 mismatch for {artifact['id']}: expected {expected}, got {actual}"
        )


def download_artifact(
    artifact: dict,
    model_root: Path,
    token: str | None,
    verify_existing_hash: bool,
) -> Path:
    artifact_id = str(artifact["id"])
    target = safe_target(model_root, str(artifact["target"]))
    min_bytes = int(artifact.get("min_bytes", 1))
    expected_sha256 = str(artifact.get("sha256", "")).strip() or None
    if valid_file(
        target,
        min_bytes,
        expected_sha256=expected_sha256,
        verify_hash=verify_existing_hash,
    ):
        print(f"OK      {artifact_id}: {target} ({target.stat().st_size:,} bytes)")
        return target

    if target.exists():
        quarantine = target.with_name(target.name + ".incomplete")
        quarantine.unlink(missing_ok=True)
        target.replace(quarantine)
        print(f"Moved incomplete file to {quarantine}")

    download_root = model_root / ".downloads" / artifact_id
    download_root.mkdir(parents=True, exist_ok=True)
    print(
        f"DOWNLOAD {artifact_id}: {artifact['repo_id']}::{artifact['filename']} "
        f"-> {target}",
        flush=True,
    )
    downloaded = Path(
        hf_hub_download(
            repo_id=str(artifact["repo_id"]),
            filename=str(artifact["filename"]),
            revision=str(artifact.get("revision", "main")),
            token=token,
            local_dir=download_root,
        )
    )
    if not valid_file(downloaded, min_bytes):
        raise RuntimeError(
            f"Downloaded file for {artifact_id} is too small: "
            f"{downloaded.stat().st_size:,} bytes"
        )
    verify_download(artifact, downloaded)

    target.parent.mkdir(parents=True, exist_ok=True)
    staging = target.with_name(target.name + ".staging")
    staging.unlink(missing_ok=True)
    if downloaded.is_symlink():
        shutil.copy2(downloaded.resolve(), staging)
    else:
        try:
            os.replace(downloaded, staging)
        except OSError:
            shutil.copy2(downloaded, staging)
    os.replace(staging, target)
    shutil.rmtree(download_root, ignore_errors=True)
    print(f"READY   {artifact_id}: {target} ({target.stat().st_size:,} bytes)")
    return target


def main() -> int:
    args = parse_args()
    model_root = Path(args.model_root).expanduser().resolve()
    manifest_path = Path(args.manifest).expanduser().resolve()
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    groups = {item.strip() for item in args.groups.split(",") if item.strip()}
    only = {item.strip() for item in args.only.split(",") if item.strip()}
    artifacts = selected_artifacts(manifest, groups, only)
    if not artifacts:
        print("No artifacts selected", file=sys.stderr)
        return 2

    print(f"Model root: {model_root}")
    print("Selected: " + ", ".join(str(item["id"]) for item in artifacts))
    if args.dry_run:
        for item in artifacts:
            print(
                f"- {item['id']}: {item['repo_id']}::{item['filename']} "
                f"-> {item['target']}"
            )
        return 0

    if args.verify_only:
        missing = []
        for item in artifacts:
            target = safe_target(model_root, str(item["target"]))
            if not valid_file(
                target,
                int(item.get("min_bytes", 1)),
                expected_sha256=str(item.get("sha256", "")).strip() or None,
                verify_hash=args.verify_sha256,
            ):
                missing.append(str(item["id"]))
        if missing:
            print(
                "Missing, incomplete, or corrupt: " + ", ".join(missing),
                file=sys.stderr,
            )
            return 1
        print("All selected artifacts passed validation")
        return 0

    model_root.mkdir(parents=True, exist_ok=True)
    token = os.getenv("HF_TOKEN") or os.getenv("HUGGINGFACE_TOKEN")
    with volume_lock(model_root):
        for item in artifacts:
            download_artifact(
                item,
                model_root,
                token,
                verify_existing_hash=args.verify_sha256,
            )
    print("Model bootstrap complete")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
