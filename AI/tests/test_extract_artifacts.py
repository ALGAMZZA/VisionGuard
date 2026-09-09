from __future__ import annotations

import io
import tarfile
from pathlib import Path

import pytest

from AI.training.extract_artifacts import extract_artifacts


def _add_file(tar: tarfile.TarFile, name: str, content: bytes) -> None:
    info = tarfile.TarInfo(name)
    info.size = len(content)
    tar.addfile(info, io.BytesIO(content))


def test_extract_artifacts_selects_only_training_inputs(tmp_path: Path) -> None:
    archive = tmp_path / "artifacts.tar"
    with tarfile.open(archive, "w") as tar:
        _add_file(tar, "scene.eye_00.rgb.mp4", b"video")
        _add_file(tar, "scene.eye_00.object_detection.jsonl", b"{}\n")
        _add_file(tar, "scene.meta.json", b"{}")
        _add_file(tar, "scene.eye_00.depth.mp4", b"depth")

    output = tmp_path / "selected"
    summary = extract_artifacts(archive, output)

    assert summary.selected_files == 3
    assert summary.extracted_files == 3
    assert (output / "scene.eye_00.rgb.mp4").read_bytes() == b"video"
    assert not (output / "scene.eye_00.depth.mp4").exists()

    second_summary = extract_artifacts(archive, output)
    assert second_summary.extracted_files == 0
    assert second_summary.skipped_files == 3


def test_extract_artifacts_rejects_path_traversal(tmp_path: Path) -> None:
    archive = tmp_path / "unsafe.tar"
    with tarfile.open(archive, "w") as tar:
        _add_file(tar, "../escape.rgb.mp4", b"bad")

    with pytest.raises(ValueError, match="unsafe TAR member"):
        extract_artifacts(archive, tmp_path / "selected")

    assert not (tmp_path / "escape.rgb.mp4").exists()
