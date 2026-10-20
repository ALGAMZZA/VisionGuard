"""Convert synchronized Unity JPEG/YOLO captures into a sampled YOLO dataset."""

from __future__ import annotations

import argparse
import json
import math
import re
import shutil
from collections import Counter
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

import cv2

CLASS_NAMES = {0: "person", 1: "forklift"}
FRAME_PATTERN = re.compile(r"^frame_(\d+)$")


@dataclass(frozen=True)
class UnitySplitSummary:
    split: str
    first_source_frame: int | None
    last_source_frame: int | None
    sampled_frames: int
    empty_labels: int
    person_boxes: int
    forklift_boxes: int


def _validate_ratios(train_ratio: float, val_ratio: float, test_ratio: float) -> None:
    ratios = (train_ratio, val_ratio, test_ratio)
    if any(value < 0 for value in ratios):
        raise ValueError("split ratios cannot be negative")
    if not math.isclose(sum(ratios), 1.0, abs_tol=1e-6):
        raise ValueError("train, val, and test ratios must sum to 1")
    if train_ratio <= 0 or val_ratio <= 0:
        raise ValueError("train and val ratios must be positive")


def _read_classes(source: Path) -> None:
    classes_path = source / "classes.txt"
    if not classes_path.is_file():
        raise FileNotFoundError(f"Unity classes file not found: {classes_path}")
    classes = [line.strip() for line in classes_path.read_text(encoding="utf-8").splitlines()]
    if classes != [CLASS_NAMES[0], CLASS_NAMES[1]]:
        raise ValueError(
            "Unity classes.txt must contain exactly 'person' then 'forklift'; "
            f"found: {classes}"
        )


def _collect_pairs(source: Path) -> list[tuple[int, Path, Path]]:
    image_dir = source / "images"
    label_dir = source / "labels"
    if not image_dir.is_dir() or not label_dir.is_dir():
        raise FileNotFoundError("Unity source must contain images/ and labels/ directories")

    images = {path.stem: path for path in image_dir.glob("*.jpg")}
    labels = {path.stem: path for path in label_dir.glob("*.txt")}
    missing_labels = sorted(images.keys() - labels.keys())
    orphan_labels = sorted(labels.keys() - images.keys())
    if missing_labels or orphan_labels:
        details = []
        if missing_labels:
            details.append(f"missing labels: {len(missing_labels)} (first: {missing_labels[0]})")
        if orphan_labels:
            details.append(f"orphan labels: {len(orphan_labels)} (first: {orphan_labels[0]})")
        raise ValueError("Unity image/label stems do not match; " + "; ".join(details))
    if not images:
        raise ValueError(f"Unity capture contains no JPEG images: {image_dir}")

    pairs: list[tuple[int, Path, Path]] = []
    for stem, image_path in images.items():
        match = FRAME_PATTERN.fullmatch(stem)
        if match is None:
            raise ValueError(f"unexpected Unity frame filename: {image_path.name}")
        pairs.append((int(match.group(1)), image_path, labels[stem]))
    pairs.sort(key=lambda item: item[0])
    return pairs


def _sample_pairs(
    pairs: list[tuple[int, Path, Path]], source_fps: float, sample_fps: float
) -> list[tuple[int, Path, Path]]:
    if source_fps <= 0 or sample_fps <= 0:
        raise ValueError("source_fps and sample_fps must be positive")
    if sample_fps > source_fps:
        raise ValueError("sample_fps cannot exceed source_fps")

    step = source_fps / sample_fps
    selected: list[tuple[int, Path, Path]] = []
    position = 0.0
    while round(position) < len(pairs):
        selected.append(pairs[round(position)])
        position += step
    return selected


def _split_counts(total: int, ratios: dict[str, float]) -> dict[str, int]:
    raw = {name: total * ratio for name, ratio in ratios.items()}
    counts = {name: math.floor(value) for name, value in raw.items()}
    remaining = total - sum(counts.values())
    priority = sorted(
        ratios,
        key=lambda name: (raw[name] - counts[name], ratios[name]),
        reverse=True,
    )
    for name in priority[:remaining]:
        counts[name] += 1
    for name, ratio in ratios.items():
        if ratio > 0 and counts[name] == 0:
            raise ValueError(f"not enough sampled frames to create the {name} split")
    return counts


def _validate_label(label_path: Path) -> Counter[int]:
    counts: Counter[int] = Counter()
    for line_number, line in enumerate(
        label_path.read_text(encoding="utf-8").splitlines(), start=1
    ):
        if not line.strip():
            continue
        fields = line.split()
        if len(fields) != 5:
            raise ValueError(f"{label_path}:{line_number}: expected 5 values")
        try:
            class_id = int(fields[0])
            x_center, y_center, width, height = map(float, fields[1:])
        except ValueError as error:
            raise ValueError(f"{label_path}:{line_number}: non-numeric YOLO row") from error
        if class_id not in CLASS_NAMES:
            raise ValueError(f"{label_path}:{line_number}: unknown class {class_id}")
        values = (x_center, y_center, width, height)
        if not all(math.isfinite(value) for value in values):
            raise ValueError(f"{label_path}:{line_number}: non-finite coordinate")
        if not all(0 <= value <= 1 for value in values) or width <= 0 or height <= 0:
            raise ValueError(f"{label_path}:{line_number}: invalid normalized box")
        if (
            x_center - width / 2 < -1e-6
            or x_center + width / 2 > 1 + 1e-6
            or y_center - height / 2 < -1e-6
            or y_center + height / 2 > 1 + 1e-6
        ):
            raise ValueError(f"{label_path}:{line_number}: box extends outside image")
        counts[class_id] += 1
    return counts


def prepare_unity_dataset(
    source_dir: str | Path,
    output_dir: str | Path,
    *,
    source_fps: float = 10.0,
    sample_fps: float = 3.0,
    train_ratio: float = 0.8,
    val_ratio: float = 0.2,
    test_ratio: float = 0.0,
    start_frame: int | None = None,
    end_frame: int | None = None,
) -> dict[str, Any]:
    """Validate, sample, and chronologically split one Unity capture take."""

    _validate_ratios(train_ratio, val_ratio, test_ratio)
    source = Path(source_dir).expanduser().resolve()
    output = Path(output_dir).expanduser().resolve()
    if not source.is_dir():
        raise NotADirectoryError(f"Unity source directory not found: {source}")
    _read_classes(source)
    pairs = _collect_pairs(source)
    if start_frame is not None and start_frame < 0:
        raise ValueError("start_frame cannot be negative")
    if end_frame is not None and end_frame < 0:
        raise ValueError("end_frame cannot be negative")
    if start_frame is not None and end_frame is not None and start_frame > end_frame:
        raise ValueError("start_frame cannot be greater than end_frame")
    pairs = [
        pair
        for pair in pairs
        if (start_frame is None or pair[0] >= start_frame)
        and (end_frame is None or pair[0] <= end_frame)
    ]
    if not pairs:
        raise ValueError("selected Unity frame range contains no image/label pairs")
    selected = _sample_pairs(pairs, source_fps, sample_fps)

    output.mkdir(parents=True, exist_ok=True)
    for pattern in ("images/**/*.jpg", "labels/**/*.txt"):
        if next((path for path in output.glob(pattern) if path.is_file()), None):
            raise FileExistsError(f"output already contains generated data: {output}")

    ratios = {"train": train_ratio, "val": val_ratio, "test": test_ratio}
    counts = _split_counts(len(selected), ratios)
    summaries: list[UnitySplitSummary] = []
    offset = 0
    take_name = source.name
    for split in ("train", "val", "test"):
        split_pairs = selected[offset : offset + counts[split]]
        offset += counts[split]
        image_output = output / "images" / split
        label_output = output / "labels" / split
        image_output.mkdir(parents=True, exist_ok=True)
        label_output.mkdir(parents=True, exist_ok=True)
        class_counts: Counter[int] = Counter()
        empty_labels = 0
        for frame_number, image_path, label_path in split_pairs:
            boxes = _validate_label(label_path)
            class_counts.update(boxes)
            if not boxes:
                empty_labels += 1
            if cv2.imread(str(image_path), cv2.IMREAD_COLOR) is None:
                raise ValueError(f"unreadable Unity JPEG: {image_path}")
            output_stem = f"{take_name}_{image_path.stem}"
            shutil.copy2(image_path, image_output / f"{output_stem}.jpg")
            shutil.copy2(label_path, label_output / f"{output_stem}.txt")
        summaries.append(
            UnitySplitSummary(
                split=split,
                first_source_frame=split_pairs[0][0] if split_pairs else None,
                last_source_frame=split_pairs[-1][0] if split_pairs else None,
                sampled_frames=len(split_pairs),
                empty_labels=empty_labels,
                person_boxes=class_counts[0],
                forklift_boxes=class_counts[1],
            )
        )

    manifest: dict[str, Any] = {
        "source_dir": str(source),
        "output_dir": str(output),
        "source_fps": source_fps,
        "sample_fps": sample_fps,
        "start_frame": start_frame,
        "end_frame": end_frame,
        "split_strategy": "chronological_contiguous_blocks",
        "classes": CLASS_NAMES,
        "totals": {
            "source_frames": len(pairs),
            "sampled_frames": len(selected),
            "person_boxes": sum(item.person_boxes for item in summaries),
            "forklift_boxes": sum(item.forklift_boxes for item in summaries),
            "empty_labels": sum(item.empty_labels for item in summaries),
        },
        "splits": [asdict(item) for item in summaries],
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


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Validate and sample a synchronized Unity YOLO capture."
    )
    parser.add_argument("--source", required=True, help="Unity capture take directory")
    parser.add_argument("--output", required=True, help="New YOLO dataset directory")
    parser.add_argument("--source-fps", type=float, default=10.0)
    parser.add_argument("--sample-fps", type=float, default=3.0)
    parser.add_argument("--train-ratio", type=float, default=0.8)
    parser.add_argument("--val-ratio", type=float, default=0.2)
    parser.add_argument("--test-ratio", type=float, default=0.0)
    parser.add_argument("--start-frame", type=int)
    parser.add_argument("--end-frame", type=int)
    return parser


def main() -> None:
    args = _build_parser().parse_args()
    manifest = prepare_unity_dataset(
        args.source,
        args.output,
        source_fps=args.source_fps,
        sample_fps=args.sample_fps,
        train_ratio=args.train_ratio,
        val_ratio=args.val_ratio,
        test_ratio=args.test_ratio,
        start_frame=args.start_frame,
        end_frame=args.end_frame,
    )
    print(json.dumps(manifest["totals"], indent=2, ensure_ascii=False))
    print(f"dataset config: {Path(manifest['output_dir']) / 'dataset.yaml'}")


if __name__ == "__main__":
    main()
