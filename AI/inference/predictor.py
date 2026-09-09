"""Coordinator that combines object detection and collision assessment."""

from __future__ import annotations

import argparse
import time
from pathlib import Path
from typing import Protocol

import cv2
import numpy as np

from AI.inference.collision_detector import CollisionDetector
from AI.inference.detector import Detector, DetectorConfig
from AI.inference.schemas import Detection, ObjectClass, PredictionResult, RiskLevel


class DetectionProvider(Protocol):
    def detect(self, frame: np.ndarray) -> list[Detection]: ...

    def reset_tracking(self) -> None: ...


class Predictor:
    """Stateful, single-video-stream prediction pipeline."""

    def __init__(
        self,
        detector: DetectionProvider,
        collision_detector: CollisionDetector | None = None,
    ) -> None:
        self.detector = detector
        self.collision_detector = collision_detector or CollisionDetector()
        self._frame_index = 0

    def reset(self) -> None:
        self._frame_index = 0
        self.detector.reset_tracking()
        self.collision_detector.reset()

    def predict(
        self,
        frame: np.ndarray,
        *,
        frame_id: str | None = None,
        fps: float = 30.0,
    ) -> PredictionResult:
        if not isinstance(frame, np.ndarray) or frame.ndim != 3:
            raise ValueError("frame must be a HxWxC numpy array")

        started_at = time.perf_counter()
        self._frame_index += 1
        detections = self.detector.detect(frame)
        risks = self.collision_detector.assess(
            detections,
            frame_index=self._frame_index,
            fps=fps,
        )
        overall_risk = max(
            (risk.level for risk in risks),
            key=_risk_rank,
            default=RiskLevel.SAFE,
        )
        height, width = frame.shape[:2]

        return PredictionResult(
            frame_id=frame_id,
            image_width=width,
            image_height=height,
            detections=detections,
            risks=risks,
            overall_risk=overall_risk,
            processing_time_ms=(time.perf_counter() - started_at) * 1000.0,
        )


def _risk_rank(level: RiskLevel) -> int:
    return {
        RiskLevel.SAFE: 0,
        RiskLevel.WARNING: 1,
        RiskLevel.DANGER: 2,
    }[level]


def draw_prediction(frame: np.ndarray, result: PredictionResult) -> np.ndarray:
    """Draw tracked boxes and the highest risk on a copy of ``frame``."""

    output = frame.copy()
    colors = {
        ObjectClass.PERSON: (255, 128, 0),
        ObjectClass.FORKLIFT: (255, 0, 255),
    }
    for detection in result.detections:
        color = colors[detection.class_name]
        box = detection.bbox
        cv2.rectangle(
            output,
            (round(box.x1), round(box.y1)),
            (round(box.x2), round(box.y2)),
            color,
            2,
        )
        label = (
            f"{detection.class_name.value} #{detection.track_id} "
            f"{detection.confidence:.2f}"
        )
        cv2.putText(
            output,
            label,
            (round(box.x1), max(20, round(box.y1) - 8)),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.5,
            color,
            2,
        )

    if result.risks:
        top_risk = max(result.risks, key=lambda risk: risk.score)
        color = (0, 0, 255) if top_risk.level == RiskLevel.DANGER else (0, 180, 255)
        cv2.putText(
            output,
            f"{top_risk.level.value} {top_risk.score:.0f}",
            (20, 40),
            cv2.FONT_HERSHEY_SIMPLEX,
            1.0,
            color,
            3,
        )
    return output


def run_video(
    source: str,
    *,
    model_path: str,
    confidence: float,
    image_size: int,
    device: str | None,
    save_path: str | None,
    display: bool,
) -> None:
    """Run the modular pipeline against a video file or camera source."""

    detector = Detector(
        DetectorConfig(
            model_path=model_path,
            confidence=confidence,
            image_size=image_size,
            device=device,
        )
    )
    predictor = Predictor(detector)
    capture_source: str | int = int(source) if source.isdigit() else source
    capture = cv2.VideoCapture(capture_source)
    if not capture.isOpened():
        raise RuntimeError(f"could not open video source: {source}")

    fps = capture.get(cv2.CAP_PROP_FPS) or 30.0
    width = int(capture.get(cv2.CAP_PROP_FRAME_WIDTH))
    height = int(capture.get(cv2.CAP_PROP_FRAME_HEIGHT))
    writer = None
    if save_path:
        Path(save_path).parent.mkdir(parents=True, exist_ok=True)
        writer = cv2.VideoWriter(
            save_path,
            cv2.VideoWriter_fourcc(*"mp4v"),
            fps,
            (width, height),
        )

    frame_index = 0
    try:
        while True:
            ok, frame = capture.read()
            if not ok:
                break
            frame_index += 1
            result = predictor.predict(frame, frame_id=str(frame_index), fps=fps)
            annotated = draw_prediction(frame, result)
            if writer is not None:
                writer.write(annotated)
            if display:
                cv2.imshow("VisionGuard", annotated)
                if cv2.waitKey(1) & 0xFF == 27:
                    break
    finally:
        capture.release()
        if writer is not None:
            writer.release()
        if display:
            cv2.destroyAllWindows()


def main() -> None:
    parser = argparse.ArgumentParser(description="VisionGuard video inference")
    parser.add_argument("--source", required=True, help="video path or camera number")
    parser.add_argument("--model", default="AI/models/production/best.pt")
    parser.add_argument("--conf", type=float, default=0.35)
    parser.add_argument("--imgsz", type=int, default=640)
    parser.add_argument("--device", default=None)
    parser.add_argument("--save", default=None)
    parser.add_argument("--display", action="store_true")
    args = parser.parse_args()
    run_video(
        args.source,
        model_path=args.model,
        confidence=args.conf,
        image_size=args.imgsz,
        device=args.device,
        save_path=args.save,
        display=args.display,
    )


if __name__ == "__main__":
    main()
