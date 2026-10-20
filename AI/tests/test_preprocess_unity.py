from __future__ import annotations

from pathlib import Path

import cv2
import numpy as np
import pytest

from AI.training.preprocess_unity import prepare_unity_dataset


def _write_capture(source: Path, count: int = 20) -> None:
    (source / "images").mkdir(parents=True)
    (source / "labels").mkdir()
    (source / "classes.txt").write_text("person\nforklift\n", encoding="utf-8")
    for index in range(count):
        stem = f"frame_{index:08d}"
        image = np.full((24, 32, 3), index, dtype=np.uint8)
        assert cv2.imwrite(str(source / "images" / f"{stem}.jpg"), image)
        class_id = index % 2
        (source / "labels" / f"{stem}.txt").write_text(
            f"{class_id} 0.500000 0.500000 0.250000 0.250000\n",
            encoding="utf-8",
        )


def test_prepare_unity_dataset_samples_and_splits_chronologically(tmp_path: Path) -> None:
    source = tmp_path / "train_take_01"
    _write_capture(source)

    output = tmp_path / "unity_dataset"
    manifest = prepare_unity_dataset(
        source,
        output,
        source_fps=10,
        sample_fps=2,
        train_ratio=0.5,
        val_ratio=0.5,
    )

    assert manifest["totals"]["source_frames"] == 20
    assert manifest["totals"]["sampled_frames"] == 4
    assert manifest["totals"]["person_boxes"] == 2
    assert manifest["totals"]["forklift_boxes"] == 2
    assert manifest["splits"][0]["last_source_frame"] == 5
    assert manifest["splits"][1]["first_source_frame"] == 10
    assert len(list((output / "images" / "train").glob("*.jpg"))) == 2
    assert len(list((output / "images" / "val").glob("*.jpg"))) == 2
    assert (output / "dataset.yaml").is_file()


def test_prepare_unity_dataset_rejects_unpaired_files(tmp_path: Path) -> None:
    source = tmp_path / "broken_take"
    _write_capture(source, count=2)
    (source / "labels" / "frame_00000001.txt").unlink()

    with pytest.raises(ValueError, match="stems do not match"):
        prepare_unity_dataset(source, tmp_path / "output")


def test_prepare_unity_dataset_rejects_invalid_boxes(tmp_path: Path) -> None:
    source = tmp_path / "broken_box"
    _write_capture(source, count=2)
    (source / "labels" / "frame_00000000.txt").write_text(
        "0 0.9 0.5 0.4 0.2\n", encoding="utf-8"
    )

    with pytest.raises(ValueError, match="outside image"):
        prepare_unity_dataset(
            source,
            tmp_path / "output",
            source_fps=10,
            sample_fps=10,
            train_ratio=0.5,
            val_ratio=0.5,
        )


def test_prepare_unity_dataset_limits_source_frame_range(tmp_path: Path) -> None:
    source = tmp_path / "bounded_take"
    _write_capture(source, count=20)

    manifest = prepare_unity_dataset(
        source,
        tmp_path / "output",
        source_fps=10,
        sample_fps=10,
        train_ratio=0.5,
        val_ratio=0.5,
        start_frame=4,
        end_frame=11,
    )

    assert manifest["totals"]["source_frames"] == 8
    assert manifest["totals"]["sampled_frames"] == 8
    assert manifest["splits"][0]["first_source_frame"] == 4
    assert manifest["splits"][1]["last_source_frame"] == 11
