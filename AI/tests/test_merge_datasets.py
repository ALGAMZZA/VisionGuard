from __future__ import annotations

from pathlib import Path

import cv2
import numpy as np
import pytest

from AI.training.dataset import validate_dataset
from AI.training.merge_datasets import merge_yolo_datasets


def _dataset(root: Path, marker: int) -> Path:
    for split in ("train", "val", "test"):
        (root / "images" / split).mkdir(parents=True)
        (root / "labels" / split).mkdir(parents=True)
    for split in ("train", "val"):
        assert cv2.imwrite(
            str(root / "images" / split / "frame.jpg"),
            np.full((16, 16, 3), marker, dtype=np.uint8),
        )
        (root / "labels" / split / "frame.txt").write_text(
            "0 0.5 0.5 0.25 0.25\n1 0.5 0.5 0.5 0.5\n",
            encoding="utf-8",
        )
    config = root / "dataset.yaml"
    config.write_text(
        f'path: "{root}"\ntrain: images/train\nval: images/val\ntest: images/test\n'
        "names:\n  0: person\n  1: forklift\n",
        encoding="utf-8",
    )
    return config


def test_merge_preserves_splits_and_prefixes_colliding_stems(tmp_path: Path) -> None:
    first = _dataset(tmp_path / "first", 10)
    second = _dataset(tmp_path / "second", 20)
    output = tmp_path / "merged"

    manifest = merge_yolo_datasets(
        [("nvidia", first), ("unity", second)], output
    )

    assert manifest["totals"] == {
        "images": 4,
        "boxes": 8,
        "person_boxes": 4,
        "forklift_boxes": 4,
    }
    assert {path.name for path in (output / "images" / "train").glob("*.jpg")} == {
        "nvidia_frame.jpg",
        "unity_frame.jpg",
    }
    assert validate_dataset(output / "dataset.yaml").valid


def test_merge_rejects_duplicate_source_names(tmp_path: Path) -> None:
    config = _dataset(tmp_path / "source", 10)
    with pytest.raises(ValueError, match="names must be unique"):
        merge_yolo_datasets(
            [("same", config), ("same", config)], tmp_path / "merged"
        )
