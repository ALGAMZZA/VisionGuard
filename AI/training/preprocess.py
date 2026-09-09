"""Convert NVIDIA artifacts videos and JSONL boxes into a YOLO dataset."""

from __future__ import annotations

import argparse
import json
import math
import random
from collections import Counter
from collections.abc import Mapping, Sequence
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

import cv2

CLASS_NAMES = {0: "person", 1: "forklift"}
VIDEO_SUFFIX = ".rgb.mp4"
ANNOTATION_SUFFIX = ".object_detection.jsonl"


@dataclass(frozen=True)
class YoloLabel:
    class_id: int
    x_center: float
    y_center: float
    width: float
    height: float

    def serialize(self) -> str:
        return (
            f"{self.class_id} {self.x_center:.6f} {self.y_center:.6f} "
            f"{self.width:.6f} {self.height:.6f}"
        )


@dataclass(frozen=True)
class VideoSummary:
    video: str
    annotation: str
    scenario: str
    split: str
    source_frames: int
    sampled_frames: int
    person_boxes: int
    forklift_boxes: int
    ignored_entities: int
    rejected_boxes: int


def _mapping(value: object) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def classify_entity(entity_path: str, entity: Mapping[str, Any]) -> int | None:
    """Map NVIDIA entity metadata to the two VisionGuard class IDs."""

    label = _mapping(entity.get("label"))
    annotators = _mapping(entity.get("annotators"))
    metro = _mapping(entity.get("metro_agent_data"))
    fields = (
        entity_path,
        label.get("class", ""),
        annotators.get("asset_url", ""),
        metro.get("agent_type", ""),
        metro.get("agent_name", ""),
        metro.get("agent_group", ""),
        metro.get("asset_url", ""),
        metro.get("prim_path", ""),
    )
    description = " ".join(str(field).lower() for field in fields)

    if "forklift" in description or "fork lift" in description:
        return 1
    if any(token in description for token in ("worker", "character", "person", "human")):
        return 0
    return None


def normalize_bbox(
    bbox: Mapping[str, Any],
    image_width: int,
    image_height: int,
    *,
    min_box_area: float = 16.0,
) -> tuple[float, float, float, float] | None:
    """Clip an xyxy box to the frame and return normalized YOLO coordinates."""

    try:
        x_min = float(bbox["x_min"])
        y_min = float(bbox["y_min"])
        x_max = float(bbox["x_max"])
        y_max = float(bbox["y_max"])
    except (KeyError, TypeError, ValueError):
        return None

    values = (x_min, y_min, x_max, y_max)
    if image_width <= 0 or image_height <= 0 or not all(map(math.isfinite, values)):
        return None

    x_min = min(max(x_min, 0.0), float(image_width))
    x_max = min(max(x_max, 0.0), float(image_width))
    y_min = min(max(y_min, 0.0), float(image_height))
    y_max = min(max(y_max, 0.0), float(image_height))
    width = x_max - x_min
    height = y_max - y_min
    if width <= 0 or height <= 0 or width * height < min_box_area:
        return None

    return (
        (x_min + x_max) / (2.0 * image_width),
        (y_min + y_max) / (2.0 * image_height),
        width / image_width,
        height / image_height,
    )


def parse_frame_labels(
    record: Mapping[str, Any],
    image_width: int,
    image_height: int,
    *,
    min_box_area: float = 16.0,
) -> tuple[list[YoloLabel], int, int]:
    """Return labels plus ignored-entity and rejected-box counts for one frame."""

    labels: list[YoloLabel] = []
    ignored_entities = 0
    rejected_boxes = 0

    for section_name in ("agents", "objects"):
        section = _mapping(record.get(section_name))
        for entity_path, raw_entity in section.items():
            entity = _mapping(raw_entity)
            class_id = classify_entity(str(entity_path), entity)
            if class_id is None:
                ignored_entities += 1
                continue

            annotators = _mapping(entity.get("annotators"))
            bbox = _mapping(annotators.get("bounding_box_2d_tight_fast"))
            normalized = normalize_bbox(
                bbox,
                image_width,
                image_height,
                min_box_area=min_box_area,
            )
            if normalized is None:
                rejected_boxes += 1
                continue
            labels.append(YoloLabel(class_id, *normalized))

    return labels, ignored_entities, rejected_boxes


def assign_scenario_splits(
    scenarios: Sequence[str],
    *,
    train_ratio: float,
    val_ratio: float,
    test_ratio: float,
    seed: int,
) -> dict[str, str]:
    """Assign whole scenarios to splits so camera views never leak across splits."""

    ratios = {"train": train_ratio, "val": val_ratio, "test": test_ratio}
    if any(value < 0 for value in ratios.values()):
        raise ValueError("split ratios cannot be negative")
    if not math.isclose(sum(ratios.values()), 1.0, abs_tol=1e-6):
        raise ValueError("train, val, and test ratios must sum to 1")

    unique_scenarios = sorted(set(scenarios))
    active_splits = [name for name, ratio in ratios.items() if ratio > 0]
    if len(unique_scenarios) < len(active_splits):
        raise ValueError(
            "there are fewer scenarios than non-empty splits; reduce the split count"
        )

    random.Random(seed).shuffle(unique_scenarios)
    raw_counts = {
        name: len(unique_scenarios) * ratio for name, ratio in ratios.items()
    }
    counts = {name: math.floor(value) for name, value in raw_counts.items()}
    remaining = len(unique_scenarios) - sum(counts.values())
    priority = sorted(
        ratios,
        key=lambda name: (raw_counts[name] - counts[name], ratios[name]),
        reverse=True,
    )
    for name in priority[:remaining]:
        counts[name] += 1

    for name in active_splits:
        if counts[name] > 0:
            continue
        donor = max(active_splits, key=lambda candidate: counts[candidate])
        if counts[donor] <= 1:
            raise ValueError("could not allocate at least one scenario to each split")
        counts[donor] -= 1
        counts[name] += 1

    assignments: dict[str, str] = {}
    offset = 0
    for split in ("train", "val", "test"):
        for scenario in unique_scenarios[offset : offset + counts[split]]:
            assignments[scenario] = split
        offset += counts[split]
    return assignments


def _scenario_name(video_path: Path) -> str:
    return video_path.name.removesuffix(VIDEO_SUFFIX).split(".", maxsplit=1)[0]


def _annotation_path(video_path: Path) -> Path:
    base_name = video_path.name.removesuffix(VIDEO_SUFFIX)
    return video_path.with_name(f"{base_name}{ANNOTATION_SUFFIX}")


def _ensure_clean_output(output_dir: Path) -> None:
    generated_patterns = ("images/**/*.jpg", "labels/**/*.txt")
    existing = next(
        (
            path
            for pattern in generated_patterns
            for path in output_dir.glob(pattern)
            if path.is_file()
        ),
        None,
    )
    if existing is not None:
        raise FileExistsError(
            f"output already contains generated data: {existing}; use a new directory"
        )


def _convert_video(
    video_path: Path,
    annotation_path: Path,
    output_dir: Path,
    split: str,
    *,
    sample_fps: float,
    jpeg_quality: int,
    min_box_area: float,
) -> VideoSummary:
    capture = cv2.VideoCapture(str(video_path))
    if not capture.isOpened():
        raise OSError(f"could not open video: {video_path}")

    source_fps = capture.get(cv2.CAP_PROP_FPS)
    if not math.isfinite(source_fps) or source_fps <= 0:
        capture.release()
        raise ValueError(f"video has invalid FPS: {video_path}")
    frame_interval = max(1, round(source_fps / min(sample_fps, source_fps)))

    image_dir = output_dir / "images" / split
    label_dir = output_dir / "labels" / split
    image_dir.mkdir(parents=True, exist_ok=True)
    label_dir.mkdir(parents=True, exist_ok=True)

    source_frames = 0
    sampled_frames = 0
    class_counts: Counter[int] = Counter()
    ignored_entities = 0
    rejected_boxes = 0
    base_name = video_path.name.removesuffix(VIDEO_SUFFIX)

    try:
        with annotation_path.open("r", encoding="utf-8") as annotations:
            while True:
                ok, frame = capture.read()
                annotation_line = annotations.readline()
                if not ok:
                    break

                frame_index = source_frames
                source_frames += 1
                if frame_index % frame_interval != 0:
                    continue
                if not annotation_line:
                    raise ValueError(
                        f"annotations ended before video frame {frame_index}: "
                        f"{annotation_path}"
                    )

                try:
                    record = json.loads(annotation_line)
                except json.JSONDecodeError as error:
                    raise ValueError(
                        f"invalid JSON at frame {frame_index} in {annotation_path}"
                    ) from error

                height, width = frame.shape[:2]
                labels, ignored, rejected = parse_frame_labels(
                    _mapping(record),
                    width,
                    height,
                    min_box_area=min_box_area,
                )
                ignored_entities += ignored
                rejected_boxes += rejected
                class_counts.update(label.class_id for label in labels)

                output_stem = f"{base_name}_frame_{frame_index:06d}"
                image_path = image_dir / f"{output_stem}.jpg"
                label_path = label_dir / f"{output_stem}.txt"
                if not cv2.imwrite(
                    str(image_path),
                    frame,
                    [cv2.IMWRITE_JPEG_QUALITY, jpeg_quality],
                ):
                    raise OSError(f"could not write image: {image_path}")
                label_text = "\n".join(label.serialize() for label in labels)
                label_path.write_text(
                    f"{label_text}\n" if label_text else "",
                    encoding="utf-8",
                )
                sampled_frames += 1
    finally:
        capture.release()

    return VideoSummary(
        video=str(video_path),
        annotation=str(annotation_path),
        scenario=_scenario_name(video_path),
        split=split,
        source_frames=source_frames,
        sampled_frames=sampled_frames,
        person_boxes=class_counts[0],
        forklift_boxes=class_counts[1],
        ignored_entities=ignored_entities,
        rejected_boxes=rejected_boxes,
    )


def prepare_yolo_dataset(
    source_dir: str | Path,
    output_dir: str | Path,
    *,
    sample_fps: float = 5.0,
    train_ratio: float = 0.8,
    val_ratio: float = 0.2,
    test_ratio: float = 0.0,
    seed: int = 42,
    jpeg_quality: int = 90,
    min_box_area: float = 16.0,
) -> dict[str, Any]:
    """Build a scene-grouped YOLO dataset and return its manifest."""

    if sample_fps <= 0:
        raise ValueError("sample_fps must be positive")
    if not 1 <= jpeg_quality <= 100:
        raise ValueError("jpeg_quality must be between 1 and 100")
    if min_box_area < 0:
        raise ValueError("min_box_area cannot be negative")

    source = Path(source_dir).expanduser().resolve()
    output = Path(output_dir).expanduser().resolve()
    if not source.is_dir():
        raise NotADirectoryError(f"source directory not found: {source}")
    output.mkdir(parents=True, exist_ok=True)
    _ensure_clean_output(output)

    videos = sorted(source.glob(f"*{VIDEO_SUFFIX}"))
    if not videos:
        raise FileNotFoundError(f"no *{VIDEO_SUFFIX} files found in {source}")

    pairs: list[tuple[Path, Path]] = []
    for video in videos:
        annotation = _annotation_path(video)
        if not annotation.is_file():
            raise FileNotFoundError(f"annotation not found for {video.name}: {annotation}")
        pairs.append((video, annotation))

    scenarios = [_scenario_name(video) for video, _ in pairs]
    assignments = assign_scenario_splits(
        scenarios,
        train_ratio=train_ratio,
        val_ratio=val_ratio,
        test_ratio=test_ratio,
        seed=seed,
    )

    for split in ("train", "val", "test"):
        (output / "images" / split).mkdir(parents=True, exist_ok=True)
        (output / "labels" / split).mkdir(parents=True, exist_ok=True)

    summaries = [
        _convert_video(
            video,
            annotation,
            output,
            assignments[_scenario_name(video)],
            sample_fps=sample_fps,
            jpeg_quality=jpeg_quality,
            min_box_area=min_box_area,
        )
        for video, annotation in pairs
    ]

    manifest: dict[str, Any] = {
        "source_dir": str(source),
        "output_dir": str(output),
        "sample_fps": sample_fps,
        "seed": seed,
        "classes": CLASS_NAMES,
        "scenario_splits": assignments,
        "totals": {
            "videos": len(summaries),
            "source_frames": sum(item.source_frames for item in summaries),
            "sampled_frames": sum(item.sampled_frames for item in summaries),
            "person_boxes": sum(item.person_boxes for item in summaries),
            "forklift_boxes": sum(item.forklift_boxes for item in summaries),
            "ignored_entities": sum(item.ignored_entities for item in summaries),
            "rejected_boxes": sum(item.rejected_boxes for item in summaries),
        },
        "videos": [asdict(item) for item in summaries],
    }
    (output / "manifest.json").write_text(
        json.dumps(manifest, indent=2, ensure_ascii=False),
        encoding="utf-8",
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
        description="Convert selected NVIDIA artifacts into YOLO images and labels."
    )
    parser.add_argument("--source", required=True, help="Selected artifacts directory")
    parser.add_argument("--output", required=True, help="New YOLO dataset directory")
    parser.add_argument("--sample-fps", type=float, default=5.0)
    parser.add_argument("--train-ratio", type=float, default=0.8)
    parser.add_argument("--val-ratio", type=float, default=0.2)
    parser.add_argument("--test-ratio", type=float, default=0.0)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--jpeg-quality", type=int, default=90)
    parser.add_argument("--min-box-area", type=float, default=16.0)
    return parser


def main() -> None:
    args = _build_parser().parse_args()
    manifest = prepare_yolo_dataset(
        args.source,
        args.output,
        sample_fps=args.sample_fps,
        train_ratio=args.train_ratio,
        val_ratio=args.val_ratio,
        test_ratio=args.test_ratio,
        seed=args.seed,
        jpeg_quality=args.jpeg_quality,
        min_box_area=args.min_box_area,
    )
    print(json.dumps(manifest["totals"], indent=2, ensure_ascii=False))
    print(f"dataset config: {Path(manifest['output_dir']) / 'dataset.yaml'}")


if __name__ == "__main__":
    main()
