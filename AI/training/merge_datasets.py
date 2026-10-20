"""Merge compatible YOLO datasets while preserving their existing splits."""

from __future__ import annotations

import argparse
import json
import re
import shutil
from collections import Counter
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

import yaml

from AI.training.dataset import IMAGE_SUFFIXES, validate_dataset

EXPECTED_CLASSES = {0: "person", 1: "forklift"}


@dataclass(frozen=True)
class MergedSourceSummary:
    name: str
    config: str
    split_images: dict[str, int]
    split_boxes: dict[str, int]
    class_counts: dict[int, int]


def _safe_name(value: str) -> str:
    cleaned = re.sub(r"[^a-zA-Z0-9_-]+", "_", value).strip("_")
    if not cleaned:
        raise ValueError("dataset name must contain a letter, number, '_' or '-'")
    return cleaned


def _load_dataset(config_path: Path) -> tuple[Path, dict[str, str], dict[int, str]]:
    raw = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise TypeError(f"dataset YAML must contain a mapping: {config_path}")
    configured_root = Path(str(raw.get("path", config_path.parent)))
    root = configured_root if configured_root.is_absolute() else config_path.parent / configured_root
    raw_names = raw.get("names")
    if isinstance(raw_names, list):
        names = {index: str(name) for index, name in enumerate(raw_names)}
    elif isinstance(raw_names, dict):
        names = {int(index): str(name) for index, name in raw_names.items()}
    else:
        raise TypeError(f"dataset YAML has invalid names: {config_path}")
    splits = {
        split: str(raw[split])
        for split in ("train", "val", "test")
        if raw.get(split) not in (None, "")
    }
    return root.resolve(), splits, names


def _parse_spec(spec: str) -> tuple[str, Path]:
    name, separator, raw_path = spec.partition("=")
    if not separator or not raw_path:
        raise ValueError("dataset must use NAME=/path/to/dataset.yaml")
    return _safe_name(name), Path(raw_path).expanduser().resolve()


def merge_yolo_datasets(
    datasets: list[tuple[str, str | Path]],
    output_dir: str | Path,
    *,
    validate_sources: bool = True,
) -> dict[str, Any]:
    """Copy datasets into one output, prefixing stems and retaining each split."""

    if len(datasets) < 2:
        raise ValueError("at least two datasets are required")
    normalized = [(_safe_name(name), Path(config).expanduser().resolve()) for name, config in datasets]
    names = [name for name, _ in normalized]
    if len(set(names)) != len(names):
        raise ValueError("dataset names must be unique")

    output = Path(output_dir).expanduser().resolve()
    output.mkdir(parents=True, exist_ok=True)
    for pattern in ("images/**/*", "labels/**/*.txt"):
        if next((path for path in output.glob(pattern) if path.is_file()), None):
            raise FileExistsError(f"output already contains generated data: {output}")
    for split in ("train", "val", "test"):
        (output / "images" / split).mkdir(parents=True, exist_ok=True)
        (output / "labels" / split).mkdir(parents=True, exist_ok=True)

    summaries: list[MergedSourceSummary] = []
    for source_name, config_path in normalized:
        if not config_path.is_file():
            raise FileNotFoundError(f"dataset config not found: {config_path}")
        if validate_sources:
            report = validate_dataset(config_path)
            if not report.valid:
                raise ValueError(
                    f"source dataset is invalid ({source_name}):\n"
                    + "\n".join(report.errors[:10])
                )
        root, splits, classes = _load_dataset(config_path)
        if classes != EXPECTED_CLASSES:
            raise ValueError(
                f"dataset classes differ ({source_name}): expected {EXPECTED_CLASSES}, found {classes}"
            )

        split_images: Counter[str] = Counter()
        split_boxes: Counter[str] = Counter()
        class_counts: Counter[int] = Counter()
        for split, relative_images in splits.items():
            image_dir = root / relative_images
            label_dir = root / "labels" / split
            images = sorted(
                path for path in image_dir.rglob("*") if path.suffix.lower() in IMAGE_SUFFIXES
            )
            for image_path in images:
                relative = image_path.relative_to(image_dir)
                label_path = label_dir / relative.with_suffix(".txt")
                if not label_path.is_file():
                    raise FileNotFoundError(f"matching label not found: {label_path}")
                destination_stem = f"{source_name}_{image_path.stem}"
                image_destination = output / "images" / split / f"{destination_stem}{image_path.suffix.lower()}"
                label_destination = output / "labels" / split / f"{destination_stem}.txt"
                if image_destination.exists() or label_destination.exists():
                    raise FileExistsError(f"merged filename collision: {destination_stem}")
                shutil.copy2(image_path, image_destination)
                shutil.copy2(label_path, label_destination)
                split_images[split] += 1
                for line in label_path.read_text(encoding="utf-8").splitlines():
                    if not line.strip():
                        continue
                    class_id = int(line.split(maxsplit=1)[0])
                    class_counts[class_id] += 1
                    split_boxes[split] += 1
        summaries.append(
            MergedSourceSummary(
                name=source_name,
                config=str(config_path),
                split_images=dict(split_images),
                split_boxes=dict(split_boxes),
                class_counts=dict(class_counts),
            )
        )

    manifest: dict[str, Any] = {
        "output_dir": str(output),
        "classes": EXPECTED_CLASSES,
        "totals": {
            "images": sum(sum(item.split_images.values()) for item in summaries),
            "boxes": sum(sum(item.split_boxes.values()) for item in summaries),
            "person_boxes": sum(item.class_counts.get(0, 0) for item in summaries),
            "forklift_boxes": sum(item.class_counts.get(1, 0) for item in summaries),
        },
        "sources": [asdict(item) for item in summaries],
    }
    (output / "manifest.json").write_text(
        json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    dataset_yaml = (
        f"path: {json.dumps(str(output), ensure_ascii=False)}\n"
        "train: images/train\n"
        "val: images/val\n"
        "test: images/test\n\n"
        "names:\n"
        "  0: person\n"
        "  1: forklift\n"
    )
    (output / "dataset.yaml").write_text(dataset_yaml, encoding="utf-8")
    return manifest


def main() -> None:
    parser = argparse.ArgumentParser(description="Merge compatible YOLO datasets")
    parser.add_argument(
        "--dataset",
        action="append",
        required=True,
        help="Repeat NAME=/path/to/dataset.yaml for each source",
    )
    parser.add_argument("--output", required=True, help="New merged dataset directory")
    parser.add_argument("--skip-source-validation", action="store_true")
    args = parser.parse_args()
    manifest = merge_yolo_datasets(
        [_parse_spec(spec) for spec in args.dataset],
        args.output,
        validate_sources=not args.skip_source_validation,
    )
    print(json.dumps(manifest["totals"], indent=2, ensure_ascii=False))
    print(f"dataset config: {Path(manifest['output_dir']) / 'dataset.yaml'}")


if __name__ == "__main__":
    main()
