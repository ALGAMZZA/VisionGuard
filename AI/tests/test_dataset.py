import json
from pathlib import Path

import cv2
import numpy as np

from AI.training.dataset import create_previews, validate_dataset


def _make_dataset(root: Path, label: str = "0 0.5 0.5 0.4 0.6\n") -> Path:
    for split in ("train", "val"):
        image_dir = root / "images" / split
        label_dir = root / "labels" / split
        image_dir.mkdir(parents=True)
        label_dir.mkdir(parents=True)
        cv2.imwrite(str(image_dir / f"{split}.jpg"), np.zeros((100, 200, 3)))
        (label_dir / f"{split}.txt").write_text(label, encoding="utf-8")
    config = root / "dataset.yaml"
    config.write_text(
        "path: .\ntrain: images/train\nval: images/val\n"
        "names:\n  0: person\n  1: forklift\n",
        encoding="utf-8",
    )
    return config


def test_validate_dataset_counts_pairs_and_classes(tmp_path: Path) -> None:
    config = _make_dataset(tmp_path)

    report = validate_dataset(config)

    assert report.valid
    assert report.splits["train"].images == 1
    assert report.splits["val"].labels == 1
    assert report.splits["train"].class_counts[0] == 1
    assert "class 1 (forklift) has no boxes" in report.warnings
    json.dumps(report.to_dict())


def test_validate_dataset_rejects_invalid_box(tmp_path: Path) -> None:
    config = _make_dataset(tmp_path, "1 0.9 0.5 0.4 0.2\n")

    report = validate_dataset(config)

    assert not report.valid
    assert any("box extends outside image" in error for error in report.errors)


def test_create_previews_draws_selected_labels(tmp_path: Path) -> None:
    config = _make_dataset(tmp_path)
    preview_dir = tmp_path / "previews"

    previews = create_previews(config, preview_dir, count=2)

    assert len(previews) == 2
    assert all(path.is_file() for path in previews)
