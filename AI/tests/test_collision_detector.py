import pytest

from AI.inference.collision_detector import CollisionConfig, CollisionDetector
from AI.inference.schemas import BoundingBox, Detection, ObjectClass, RiskLevel


def make_detection(
    class_id: int,
    class_name: ObjectClass,
    track_id: int,
    center_x: float,
) -> Detection:
    return Detection(
        class_id=class_id,
        class_name=class_name,
        confidence=0.9,
        bbox=BoundingBox(
            x1=center_x - 10,
            y1=20,
            x2=center_x + 10,
            y2=100,
        ),
        track_id=track_id,
    )


def test_stationary_distant_pair_is_safe() -> None:
    collision_detector = CollisionDetector()
    risks = collision_detector.assess(
        [
            make_detection(0, ObjectClass.PERSON, 1, 100),
            make_detection(1, ObjectClass.FORKLIFT, 2, 400),
        ],
        frame_index=1,
        fps=30,
    )

    assert len(risks) == 1
    assert risks[0].level == RiskLevel.SAFE
    assert risks[0].distance_px == 300
    assert risks[0].time_to_closest_approach_s is None


def test_approaching_pair_becomes_danger() -> None:
    collision_detector = CollisionDetector(CollisionConfig(velocity_smoothing=1.0))
    first_frame = [
        make_detection(0, ObjectClass.PERSON, 1, 100),
        make_detection(1, ObjectClass.FORKLIFT, 2, 300),
    ]
    second_frame = [
        make_detection(0, ObjectClass.PERSON, 1, 100),
        make_detection(1, ObjectClass.FORKLIFT, 2, 200),
    ]

    collision_detector.assess(first_frame, frame_index=1, fps=1)
    risks = collision_detector.assess(second_frame, frame_index=2, fps=1)

    assert risks[0].level == RiskLevel.DANGER
    assert risks[0].future_distance_px == 0
    assert risks[0].time_to_closest_approach_s == 1
    assert risks[0].score > 90


def test_untracked_detections_do_not_create_motion_risk() -> None:
    collision_detector = CollisionDetector()
    detections = [
        Detection(
            class_id=0,
            class_name=ObjectClass.PERSON,
            confidence=0.9,
            bbox=BoundingBox(x1=0, y1=0, x2=10, y2=20),
        ),
        Detection(
            class_id=1,
            class_name=ObjectClass.FORKLIFT,
            confidence=0.9,
            bbox=BoundingBox(x1=20, y1=0, x2=30, y2=20),
        ),
    ]

    assert collision_detector.assess(detections, frame_index=1) == []


def test_invalid_collision_config_is_rejected() -> None:
    with pytest.raises(ValueError, match="thresholds"):
        CollisionConfig(warning_score=80, danger_score=60)
