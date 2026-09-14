"""Evaluate the complete inference pipeline against Unity ground truth files."""

from __future__ import annotations

import argparse
import json
import math
import time
from collections import defaultdict
from pathlib import Path
from typing import Any

import cv2

from AI.inference.collision_detector import CollisionDetector
from AI.inference.detector import Detector, DetectorConfig
from AI.inference.schemas import ObjectClass, RiskLevel


def _iou(first: list[float], second: list[float]) -> float:
    left, top = max(first[0], second[0]), max(first[1], second[1])
    right, bottom = min(first[2], second[2]), min(first[3], second[3])
    intersection = max(right - left, 0.0) * max(bottom - top, 0.0)
    first_area = (first[2] - first[0]) * (first[3] - first[1])
    second_area = (second[2] - second[0]) * (second[3] - second[1])
    union = first_area + second_area - intersection
    return intersection / union if union > 0 else 0.0


def _ground_truth_boxes(data: dict[str, Any], width: int, height: int) -> list[tuple[str, list[float]]]:
    boxes = []
    for obj in data.get("objects", []):
        if not obj.get("visible", False):
            continue
        box = obj["bbox"]
        center_x, center_y = box["x_center"] * width, box["y_center"] * height
        box_width, box_height = box["width"] * width, box["height"] * height
        boxes.append(
            (
                str(obj["class_name"]),
                [
                    center_x - box_width / 2,
                    center_y - box_height / 2,
                    center_x + box_width / 2,
                    center_y + box_height / 2,
                ],
            )
        )
    return boxes


def _match(
    truth: list[tuple[str, list[float]]],
    predictions: list[tuple[str, list[float]]],
    threshold: float,
) -> tuple[dict[str, list[int]], list[float]]:
    counts: dict[str, list[int]] = defaultdict(lambda: [0, 0, 0])  # TP, FP, FN
    matched_truth: set[int] = set()
    matched_predictions: set[int] = set()
    overlaps = []
    candidates = []
    for truth_index, (truth_class, truth_box) in enumerate(truth):
        for prediction_index, (prediction_class, prediction_box) in enumerate(predictions):
            if truth_class == prediction_class:
                candidates.append((_iou(truth_box, prediction_box), truth_index, prediction_index))
    for overlap, truth_index, prediction_index in sorted(candidates, reverse=True):
        if overlap < threshold:
            break
        if truth_index in matched_truth or prediction_index in matched_predictions:
            continue
        matched_truth.add(truth_index)
        matched_predictions.add(prediction_index)
        counts[truth[truth_index][0]][0] += 1
        overlaps.append(overlap)
    for index, (class_name, _) in enumerate(truth):
        if index not in matched_truth:
            counts[class_name][2] += 1
    for index, (class_name, _) in enumerate(predictions):
        if index not in matched_predictions:
            counts[class_name][1] += 1
    return counts, overlaps


def _world_cpa(data: dict[str, Any], horizon: float = 4.0) -> tuple[float, float | None] | None:
    objects = {obj.get("class_name"): obj for obj in data.get("objects", [])}
    if "person" not in objects or "forklift" not in objects:
        return None
    person, forklift = objects["person"], objects["forklift"]
    relative_position = [
        person["world_position"][axis] - forklift["world_position"][axis]
        for axis in ("x", "z")
    ]
    relative_velocity = [
        person["world_velocity"][axis] - forklift["world_velocity"][axis]
        for axis in ("x", "z")
    ]
    speed_squared = sum(value * value for value in relative_velocity)
    dot = sum(a * b for a, b in zip(relative_position, relative_velocity))
    if dot < 0 and speed_squared > 1e-9:
        tcpa = min(max(-dot / speed_squared, 0.0), horizon)
    else:
        tcpa = None
    time_value = tcpa or 0.0
    distance = math.sqrt(
        sum(
            (position + velocity * time_value) ** 2
            for position, velocity in zip(relative_position, relative_velocity)
        )
    )
    return distance, tcpa


def evaluate(args: argparse.Namespace) -> dict[str, Any]:
    source = Path(args.source).resolve()
    json_files = sorted(source.glob("frame_*.json"))
    if not json_files:
        raise ValueError(f"no frame JSON files found in {source}")
    if args.max_frames is not None:
        json_files = json_files[: args.max_frames]

    detector = Detector(
        DetectorConfig(
            model_path=args.model,
            confidence=args.conf,
            forklift_confidence=args.forklift_conf,
            image_size=args.imgsz,
            device=args.device,
            embedder_gpu=args.embedder_gpu,
        )
    )
    collision_detector = CollisionDetector()
    totals: dict[str, list[int]] = defaultdict(lambda: [0, 0, 0])
    overlaps: list[float] = []
    track_stats: dict[str, dict[str, Any]] = defaultdict(
        lambda: {"visible_frames": 0, "detected_frames": 0, "id_switches": 0, "longest_gap_frames": 0, "last_id": None, "gap": 0}
    )
    risk_counts = defaultdict(int)
    collision_frames = collision_danger_frames = 0
    safe_frames = safe_false_danger_frames = 0
    tcpa_errors: list[float] = []
    started = time.perf_counter()

    for frame_index, json_path in enumerate(json_files, start=1):
        data = json.loads(json_path.read_text(encoding="utf-8"))
        image_path = json_path.with_suffix(".jpg")
        frame = cv2.imread(str(image_path))
        if frame is None:
            raise ValueError(f"could not read {image_path}")
        detections = detector.detect(frame)
        risks = collision_detector.assess(detections, frame_index=frame_index, fps=args.fps)
        height, width = frame.shape[:2]
        truth = _ground_truth_boxes(data, width, height)
        predictions = [
            (d.class_name.value, [d.bbox.x1, d.bbox.y1, d.bbox.x2, d.bbox.y2])
            for d in detections
            if not d.is_predicted
        ]
        frame_counts, frame_overlaps = _match(truth, predictions, args.iou)
        for class_name, values in frame_counts.items():
            for index, value in enumerate(values):
                totals[class_name][index] += value
        overlaps.extend(frame_overlaps)

        for class_name in (ObjectClass.PERSON.value, ObjectClass.FORKLIFT.value):
            stat = track_stats[class_name]
            truth_box = next((box for name, box in truth if name == class_name), None)
            if truth_box is None:
                stat["gap"] = 0
                continue
            stat["visible_frames"] += 1
            candidates = [
                (_iou(truth_box, [d.bbox.x1, d.bbox.y1, d.bbox.x2, d.bbox.y2]), d)
                for d in detections
                if d.class_name.value == class_name
            ]
            current = max(candidates, default=(0.0, None), key=lambda item: item[0])
            current = current[1] if current[0] >= args.iou else None
            if current is None:
                stat["gap"] += 1
                stat["longest_gap_frames"] = max(stat["longest_gap_frames"], stat["gap"])
            else:
                stat["detected_frames"] += 1
                if stat["last_id"] is not None and stat["last_id"] != current.track_id:
                    stat["id_switches"] += 1
                stat["last_id"] = current.track_id
                stat["gap"] = 0

        top_risk = max(risks, key=lambda item: item.score, default=None)
        level = top_risk.level.value if top_risk else RiskLevel.SAFE.value
        risk_counts[level] += 1
        collision = bool(data.get("collision")) or any(
            bool(obj.get("collision")) for obj in data.get("objects", [])
        )
        if collision:
            collision_frames += 1
            collision_danger_frames += level == RiskLevel.DANGER.value
        if "Safe" in str(data.get("scenario_id", "")) and data.get("scenario_state") == "Running":
            safe_frames += 1
            safe_false_danger_frames += level == RiskLevel.DANGER.value
        world_cpa = _world_cpa(data)
        if world_cpa and world_cpa[1] is not None and top_risk and top_risk.time_to_closest_approach_s is not None:
            tcpa_errors.append(abs(world_cpa[1] - top_risk.time_to_closest_approach_s))

        if frame_index % args.progress_every == 0:
            elapsed = time.perf_counter() - started
            print(f"{frame_index}/{len(json_files)} frames ({frame_index / elapsed:.2f} FPS)", flush=True)

    class_metrics = {}
    for class_name in sorted(set(totals) | {"person", "forklift"}):
        tp, fp, fn = totals[class_name]
        class_metrics[class_name] = {
            "tp": tp,
            "fp": fp,
            "fn": fn,
            "precision": tp / (tp + fp) if tp + fp else 0.0,
            "recall": tp / (tp + fn) if tp + fn else 0.0,
        }
    for stat in track_stats.values():
        stat.pop("last_id", None)
        stat.pop("gap", None)
        stat["coverage"] = (
            stat["detected_frames"] / stat["visible_frames"]
            if stat["visible_frames"]
            else 0.0
        )

    report = {
        "source": str(source),
        "model": str(Path(args.model).resolve()),
        "frames": len(json_files),
        "iou_threshold": args.iou,
        "detection": class_metrics,
        "mean_matched_iou": sum(overlaps) / len(overlaps) if overlaps else 0.0,
        "tracking": track_stats,
        "risk_levels": dict(risk_counts),
        "collision_frames": collision_frames,
        "collision_danger_recall": collision_danger_frames / collision_frames if collision_frames else None,
        "safe_running_frames": safe_frames,
        "safe_false_danger_rate": safe_false_danger_frames / safe_frames if safe_frames else None,
        "tcpa_mae_seconds": sum(tcpa_errors) / len(tcpa_errors) if tcpa_errors else None,
        "tcpa_comparison_frames": len(tcpa_errors),
        "elapsed_seconds": time.perf_counter() - started,
        "limitations": [
            "Unity JSON has collision truth but no explicit SAFE/WARNING/DANGER ground-truth field.",
            "AI CPA uses image pixels while Unity CPA uses world coordinates; only time-to-CPA is directly compared.",
        ],
    }
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return report


def main() -> None:
    parser = argparse.ArgumentParser(description="Evaluate VisionGuard on Unity capture ground truth")
    parser.add_argument("--source", required=True)
    parser.add_argument("--model", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--conf", type=float, default=0.35)
    parser.add_argument("--forklift-conf", type=float, default=0.60)
    parser.add_argument("--imgsz", type=int, default=640)
    parser.add_argument("--device", default="cpu")
    parser.add_argument("--fps", type=float, default=10.0)
    parser.add_argument("--iou", type=float, default=0.5)
    parser.add_argument("--progress-every", type=int, default=250)
    parser.add_argument("--max-frames", type=int, default=None)
    parser.add_argument("--embedder-gpu", action="store_true")
    evaluate(parser.parse_args())


if __name__ == "__main__":
    main()
