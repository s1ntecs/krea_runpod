from __future__ import annotations

from pathlib import Path

from krea_worker.output import OutputError, OutputManager


def test_base64_output_and_cleanup(tmp_path: Path) -> None:
    path = tmp_path / "image.png"
    path.write_bytes(b"png-bytes")
    manager = OutputManager("base64", clean_outputs=True)
    mode, images = manager.publish([path], None, "job")
    assert mode == "base64"
    assert images[0]["data"].startswith("data:image/png;base64,")
    assert not path.exists()


def test_auto_falls_back_to_base64_when_s3_upload_fails(tmp_path: Path, monkeypatch) -> None:
    path = tmp_path / "image.png"
    path.write_bytes(b"png-bytes")
    manager = OutputManager("auto", clean_outputs=False)
    monkeypatch.setattr(manager, "_s3_configured", lambda: True)

    def fail(_path: Path, _job_id: str) -> dict:
        raise OutputError("boom")

    monkeypatch.setattr(manager, "_s3", fail)
    mode, images = manager.publish([path], None, "job")
    assert mode == "base64"
    assert "data" in images[0]
