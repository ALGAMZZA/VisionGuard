from __future__ import annotations

import json
from pathlib import Path

import cv2
import numpy as np

from AI.training.preprocess import (
    assign_scenario_splits,
    classify_entity,
    normalize_bbox,
    prepare_yolo_dataset,
)


def _record() -> dict[str, object]:
    return {
        "agents": {
            "/World/Characters/Worker/Worker_0": {
                "label": {"class": "character"},
                "annotators": {
                    "bounding_box_2d_tight_fast": {
                        "x_min": 10,
                        "y_min": 20,
                        "x_max": 30,
                        "y_max": 60,
                    }
                },
                "metro_agent_data": {"agent_group": "Worker"},
            },
            "/World/Robots/forklift/Forklift": {
                "label": {"class": "robot"},
                "annotators": {
                    "bounding_box_2d_tight_fast": {
                        "x_min": 50,
                        "y_min": 10,
                        "x_max": 90,
                        "y_max": 70,
                    }
                },
                "metro_agent_data": {"agent_group": "forklift"},
            },
        },
        "objects": {},
    }


def _write_video_pair(source: Path, scenario: str) -> None:
    base = f"{scenario}.eye_00"
    video_path = source / f"{base}.rgb.mp4"
    writer = cv2.VideoWriter(
        str(video_path),
        cv2.VideoWriter_fourcc(*"mp4v"),
        6.0,
        (100, 100),
    )
    assert writer.isOpened()
    for index in range(6):
        writer.write(np.full((100, 100, 3), index * 20, dtype=np.uint8))
    writer.release()

    lines = "\n".join(json.dumps(_record()) for _ in range(6))
    (source / f"{base}.object_detection.jsonl").write_text(
        f"{lines}\n", encoding="utf-8"
    )


def test_classification_and_bbox_normalization() -> None:
    worker = {"label": {"class": "character"}}
    forklift = {"metro_agent_data": {"agent_group": "forklift"}}

    assert classify_entity("worker", worker) == 0
    assert classify_entity("robot", forklift) == 1
    assert classify_entity("pallet", {"label": {"class": "object"}}) is None
    assert normalize_bbox(
        {"x_min": -10, "y_min": 20, "x_max": 50, "y_max": 80}, 100, 100
    ) == (0.25, 0.5, 0.5, 0.6)


def test_scenario_split_is_deterministic_and_grouped() -> None:
    scenarios = ["scene_a", "scene_a", "scene_b", "scene_c"]
    first = assign_scenario_splits(
        scenarios, train_ratio=2 / 3, val_ratio=1 / 3, test_ratio=0, seed=7
    )
    second = assign_scenario_splits(
        scenarios, train_ratio=2 / 3, val_ratio=1 / 3, test_ratio=0, seed=7
    )

    assert first == second
    assert set(first) == {"scene_a", "scene_b", "scene_c"}
    assert list(first.values()).count("train") == 2
    assert list(first.values()).count("val") == 1


def test_prepare_yolo_dataset_integration(tmp_path: Path) -> None:
    source = tmp_path / "selected"
    source.mkdir()
    _write_video_pair(source, "scene_a")
    _write_video_pair(source, "scene_b")

    output = tmp_path / "dataset"
    manifest = prepare_yolo_dataset(
        source,
        output,
        sample_fps=3,
        train_ratio=0.5,
        val_ratio=0.5,
        test_ratio=0,
        seed=1,
    )

    assert manifest["totals"]["videos"] == 2
    assert manifest["totals"]["sampled_frames"] == 6
    assert manifest["totals"]["person_boxes"] == 6
    assert manifest["totals"]["forklift_boxes"] == 6
    assert len(list((output / "images" / "train").glob("*.jpg"))) == 3
    assert len(list((output / "images" / "val").glob("*.jpg"))) == 3
    first_label = next((output / "labels").glob("**/*.txt")).read_text()
    assert first_label.splitlines()[0].startswith("0 ")
    assert first_label.splitlines()[1].startswith("1 ")
    assert (output / "dataset.yaml").is_file()
    assert (output / "manifest.json").is_file()
