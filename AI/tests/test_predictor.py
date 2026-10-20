import numpy as np

from AI.inference.predictor import Predictor
from AI.inference.schemas import BoundingBox, Detection, ObjectClass, RiskLevel


class FakeDetector:
    def __init__(self) -> None:
        self.reset_called = False

    def detect(self, frame: np.ndarray) -> list[Detection]:
        assert frame.shape == (120, 160, 3)
        return [
            Detection(
                class_id=0,
                class_name=ObjectClass.PERSON,
                confidence=0.95,
                bbox=BoundingBox(x1=10, y1=10, x2=30, y2=60),
                track_id=1,
            )
        ]

    def reset_tracking(self) -> None:
        self.reset_called = True


def test_predictor_builds_frame_result() -> None:
    detector = FakeDetector()
    predictor = Predictor(detector)

    result = predictor.predict(
        np.zeros((120, 160, 3), dtype=np.uint8),
        frame_id="frame-1",
    )

    assert result.frame_id == "frame-1"
    assert result.image_width == 160
    assert result.image_height == 120
    assert result.overall_risk == RiskLevel.SAFE
    assert len(result.detections) == 1
    assert result.processing_time_ms >= 0

    predictor.reset()
    assert detector.reset_called
