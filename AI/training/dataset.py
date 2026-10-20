"""Validate and preview YOLO object-detection datasets."""

from __future__ import annotations

import argparse
import json
import random
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import cv2
import yaml

IMAGE_SUFFIXES = {".bmp", ".jpeg", ".jpg", ".png", ".tif", ".tiff", ".webp"}
PREVIEW_COLORS = {0: (255, 128, 0), 1: (255, 0, 255)}


@dataclass(slots=True)
class SplitSummary:
    """Validation counters for one dataset split."""

    images: int = 0
    labels: int = 0
    empty_labels: int = 0
    boxes: int = 0
    class_counts: Counter[int] = field(default_factory=Counter)


@dataclass(slots=True)
class DatasetReport:
    """Complete validation result suitable for CLI JSON output."""

    config: str
    root: str
    classes: dict[int, str]
    splits: dict[str, SplitSummary]
    errors: list[str]
    warnings: list[str]

    @property
    def valid(self) -> bool:
        return not self.errors

    def to_dict(self) -> dict[str, Any]:
        return {
            "config": self.config,
            "root": self.root,
            "classes": self.classes,
            "splits": {
                name: {
                    "images": summary.images,
                    "labels": summary.labels,
                    "empty_labels": summary.empty_labels,
                    "boxes": summary.boxes,
                    "class_counts": dict(summary.class_counts),
                }
                for name, summary in self.splits.items()
            },
            "errors": self.errors,
            "warnings": self.warnings,
            "valid": self.valid,
        }


def _load_config(config_path: Path) -> tuple[Path, dict[int, str], dict[str, Any]]:
    if not config_path.is_file():
        raise FileNotFoundError(f"dataset config not found: {config_path}")

    raw = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise TypeError("dataset config must contain a YAML mapping")

    raw_names = raw.get("names")
    if isinstance(raw_names, list):
        names = {index: str(name) for index, name in enumerate(raw_names)}
    elif isinstance(raw_names, dict):
        try:
            names = {int(index): str(name) for index, name in raw_names.items()}
        except (TypeError, ValueError) as error:
            raise ValueError("dataset class IDs must be integers") from error
    else:
        raise TypeError("dataset config must define names as a list or mapping")
    if not names:
        raise ValueError("dataset config must define at least one class")

    configured_root = Path(str(raw.get("path", config_path.parent)))
    root = (
        configured_root
        if configured_root.is_absolute()
        else config_path.parent / configured_root
    ).resolve()
    return root, names, raw


def _image_files(path: Path) -> list[Path]:
    if not path.is_dir():
        return []
    return sorted(
        item for item in path.rglob("*") if item.suffix.lower() in IMAGE_SUFFIXES
    )


def _label_path(image: Path, image_dir: Path, label_dir: Path) -> Path:
    return label_dir / image.relative_to(image_dir).with_suffix(".txt")


def _parse_label(
    label_path: Path,
    classes: dict[int, str],
) -> tuple[list[tuple[int, float, float, float, float]], list[str]]:
    boxes: list[tuple[int, float, float, float, float]] = []
    errors: list[str] = []
    for line_number, line in enumerate(
        label_path.read_text(encoding="utf-8").splitlines(), start=1
    ):
        if not line.strip():
            continue
        fields = line.split()
        if len(fields) != 5:
            errors.append(f"{label_path}:{line_number}: expected 5 values")
            continue
        try:
            class_id = int(fields[0])
            x_center, y_center, width, height = map(float, fields[1:])
        except ValueError:
            errors.append(f"{label_path}:{line_number}: values are not numeric")
            continue
        if class_id not in classes:
            errors.append(f"{label_path}:{line_number}: unknown class {class_id}")
            continue
        if not all(
            0.0 <= value <= 1.0 for value in (x_center, y_center, width, height)
        ):
            errors.append(
                f"{label_path}:{line_number}: coordinates must be within 0..1"
            )
            continue
        if width <= 0.0 or height <= 0.0:
            errors.append(f"{label_path}:{line_number}: box size must be positive")
            continue
        if (
            x_center - width / 2 < -1e-6
            or x_center + width / 2 > 1.0 + 1e-6
            or y_center - height / 2 < -1e-6
            or y_center + height / 2 > 1.0 + 1e-6
        ):
            errors.append(f"{label_path}:{line_number}: box extends outside image")
            continue
        boxes.append((class_id, x_center, y_center, width, height))
    return boxes, errors


def validate_dataset(config: str | Path) -> DatasetReport:
    """Validate image/label pairs and YOLO rows from a dataset YAML file."""

    config_path = Path(config).expanduser().resolve()
    root, classes, raw = _load_config(config_path)
    report = DatasetReport(
        config=str(config_path),
        root=str(root),
        classes=classes,
        splits={},
        errors=[],
        warnings=[],
    )
    if not root.is_dir():
        report.errors.append(f"dataset root not found: {root}")
        return report

    for split in ("train", "val", "test"):
        configured_images = raw.get(split)
        if configured_images in (None, ""):
            continue
        image_dir = root / str(configured_images)
        label_dir = root / "labels" / split
        summary = SplitSummary()
        report.splits[split] = summary

        if not image_dir.is_dir():
            report.errors.append(f"{split} image directory not found: {image_dir}")
            continue
        if not label_dir.is_dir():
            report.errors.append(f"{split} label directory not found: {label_dir}")
            continue

        images = _image_files(image_dir)
        summary.images = len(images)
        label_files = sorted(label_dir.rglob("*.txt"))
        summary.labels = len(label_files)
        expected_labels = {_label_path(image, image_dir, label_dir) for image in images}

        for missing in sorted(expected_labels - set(label_files)):
            report.errors.append(f"missing label: {missing}")
        for orphan in sorted(set(label_files) - expected_labels):
            report.errors.append(f"label has no matching image: {orphan}")

        for image in images:
            if cv2.imread(str(image), cv2.IMREAD_COLOR) is None:
                report.errors.append(f"unreadable image: {image}")
            label = _label_path(image, image_dir, label_dir)
            if not label.is_file():
                continue
            boxes, label_errors = _parse_label(label, classes)
            report.errors.extend(label_errors)
            if not label.read_text(encoding="utf-8").strip():
                summary.empty_labels += 1
            summary.boxes += len(boxes)
            summary.class_counts.update(box[0] for box in boxes)

        if not images:
            report.warnings.append(f"{split} split contains no images")

    for required_split in ("train", "val"):
        if required_split not in report.splits:
            report.errors.append(f"dataset config does not define {required_split}")
    for class_id, class_name in classes.items():
        total = sum(
            summary.class_counts[class_id] for summary in report.splits.values()
        )
        if total == 0:
            report.warnings.append(f"class {class_id} ({class_name}) has no boxes")
    return report


def create_previews(
    config: str | Path,
    output_dir: str | Path,
    *,
    count: int = 24,
    seed: int = 42,
) -> list[Path]:
    """Draw YOLO labels on a deterministic random sample of dataset images."""

    if count < 1:
        raise ValueError("preview count must be positive")
    config_path = Path(config).expanduser().resolve()
    root, classes, raw = _load_config(config_path)
    candidates: list[tuple[str, Path, Path]] = []
    for split in ("train", "val", "test"):
        configured_images = raw.get(split)
        if configured_images in (None, ""):
            continue
        image_dir = root / str(configured_images)
        label_dir = root / "labels" / split
        candidates.extend(
            (split, image, _label_path(image, image_dir, label_dir))
            for image in _image_files(image_dir)
        )
    if not candidates:
        raise ValueError("dataset contains no images to preview")

    selected = random.Random(seed).sample(candidates, min(count, len(candidates)))
    destination = Path(output_dir).expanduser().resolve()
    destination.mkdir(parents=True, exist_ok=True)
    written: list[Path] = []
    for split, image_path, label_path in selected:
        image = cv2.imread(str(image_path), cv2.IMREAD_COLOR)
        if image is None or not label_path.is_file():
            continue
        boxes, errors = _parse_label(label_path, classes)
        if errors:
            continue
        image_height, image_width = image.shape[:2]
        for class_id, x_center, y_center, width, height in boxes:
            x1 = round((x_center - width / 2) * image_width)
            y1 = round((y_center - height / 2) * image_height)
            x2 = round((x_center + width / 2) * image_width)
            y2 = round((y_center + height / 2) * image_height)
            color = PREVIEW_COLORS.get(class_id, (0, 255, 0))
            cv2.rectangle(image, (x1, y1), (x2, y2), color, 3)
            cv2.putText(
                image,
                classes[class_id],
                (x1, max(24, y1 - 8)),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.8,
                color,
                2,
            )
        output_path = destination / f"{split}_{image_path.name}"
        if not cv2.imwrite(str(output_path), image):
            raise OSError(f"could not write preview: {output_path}")
        written.append(output_path)
    return written


def main() -> None:
    parser = argparse.ArgumentParser(description="Validate a YOLO dataset")
    parser.add_argument("--config", required=True, help="Path to dataset.yaml")
    parser.add_argument("--preview-dir", help="Optional labeled preview directory")
    parser.add_argument("--preview-count", type=int, default=24)
    parser.add_argument("--seed", type=int, default=42)
    args = parser.parse_args()

    report = validate_dataset(args.config)
    print(json.dumps(report.to_dict(), indent=2, ensure_ascii=False))
    if args.preview_dir and report.valid:
        previews = create_previews(
            args.config,
            args.preview_dir,
            count=args.preview_count,
            seed=args.seed,
        )
        print(f"preview images: {len(previews)} ({Path(args.preview_dir).resolve()})")
    if not report.valid:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
