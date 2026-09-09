from __future__ import annotations

from dataclasses import dataclass
from typing import ClassVar

import numpy as np
import pytest

from AI.inference.detector import Detector, DetectorConfig
from AI.inference.schemas import ObjectClass


class FakeTensor:
    def __init__(self, value: object) -> None:
        self.value = value

    def __getitem__(self, _: int) -> FakeTensor:
        return self

    def __int__(self) -> int:
        return int(self.value)

    def __float__(self) -> float:
        return float(self.value)

    def detach(self) -> FakeTensor:
        return self

    def cpu(self) -> FakeTensor:
        return self

    def numpy(self) -> np.ndarray:
        return np.asarray(self.value)


@dataclass
class FakeBox:
    class_id: int
    confidence: float
    coordinates: list[float]

    @property
    def cls(self) -> FakeTensor:
        return FakeTensor(self.class_id)

    @property
    def conf(self) -> FakeTensor:
        return FakeTensor(self.confidence)

    @property
    def xyxy(self) -> FakeTensor:
        return FakeTensor(self.coordinates)


class FakeModel:
    names: ClassVar[dict[int, str]] = {0: "person", 1: "forklift", 2: "chair"}

    def predict(self, **_: object) -> list[object]:
        boxes = [
            FakeBox(0, 0.9, [10, 10, 30, 50]),
            FakeBox(1, 0.8, [50, 10, 90, 60]),
            FakeBox(2, 0.7, [100, 10, 120, 50]),
        ]
        return [type("Result", (), {"boxes": boxes})()]


class FakeTrack:
    def __init__(
        self, track_id: int, raw_detection: tuple[list[float], float, int]
    ) -> None:
        self.track_id = track_id
        self.ltwh, self.confidence, self.class_id = raw_detection
        self.time_since_update = 0

    def is_confirmed(self) -> bool:
        return True

    def get_det_class(self) -> int:
        return self.class_id

    def get_det_conf(self) -> float:
        return self.confidence

    def to_ltrb(
        self, *, orig: bool = False, orig_strict: bool = False
    ) -> list[float]:
        left, top, width, height = self.ltwh
        return [left, top, left + width, top + height]


class FakeTracker:
    def update_tracks(
        self,
        detections: list[tuple[list[float], float, int]],
        *,
        frame: np.ndarray,
    ) -> list[FakeTrack]:
        assert frame.shape == (100, 200, 3)
        return [FakeTrack(index + 1, item) for index, item in enumerate(detections)]

    def reset(self) -> None:
        pass


def test_detector_filters_classes_and_normalizes_tracks() -> None:
    detector = Detector(
        DetectorConfig(model_path="unused"),
        model=FakeModel(),
        tracker=FakeTracker(),
    )

    detections = detector.detect(np.zeros((100, 200, 3), dtype=np.uint8))

    assert len(detections) == 2
    assert detections[0].class_name == ObjectClass.PERSON
    assert detections[0].track_id == 1
    assert detections[1].class_name == ObjectClass.FORKLIFT
    assert detections[1].bbox.x2 == 90


def test_invalid_detector_config_is_rejected() -> None:
    with pytest.raises(ValueError, match="confidence"):
        DetectorConfig(confidence=1.1)
    with pytest.raises(ValueError, match="max_box_area_ratio"):
        DetectorConfig(max_box_area_ratio=0.0)


def test_detector_does_not_emit_stale_tracks() -> None:
    class StaleTracker(FakeTracker):
        def update_tracks(
            self,
            detections: list[tuple[list[float], float, int]],
            *,
            frame: np.ndarray,
        ) -> list[FakeTrack]:
            tracks = super().update_tracks(detections, frame=frame)
            for track in tracks:
                track.time_since_update = 1
            return tracks

    detector = Detector(
        DetectorConfig(model_path="unused"),
        model=FakeModel(),
        tracker=StaleTracker(),
    )

    assert detector.detect(np.zeros((100, 200, 3), dtype=np.uint8)) == []


def test_detector_rejects_box_covering_most_of_frame() -> None:
    class HugeBoxModel(FakeModel):
        def predict(self, **_: object) -> list[object]:
            boxes = [FakeBox(1, 0.9, [0, 0, 190, 100])]
            return [type("Result", (), {"boxes": boxes})()]

    detector = Detector(
        DetectorConfig(model_path="unused", max_box_area_ratio=0.5),
        model=HugeBoxModel(),
        tracker=FakeTracker(),
    )

    assert detector.detect(np.zeros((100, 200, 3), dtype=np.uint8)) == []

