"""YOLO detection and DeepSORT tracking.

Heavy third-party imports are intentionally delayed until ``Detector`` is
constructed.  Schema and collision unit tests can therefore run without
loading a model or initializing the DeepSORT embedder.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

import numpy as np

from AI.inference.schemas import BoundingBox, Detection, ObjectClass


@dataclass(frozen=True, slots=True)
class DetectorConfig:
    """Runtime options for YOLO and DeepSORT."""

    model_path: str = "AI/models/production/best.pt"
    confidence: float = 0.35
    image_size: int = 640
    device: str | int | None = None
    max_box_area_ratio: float = 0.5
    # Retain unmatched identities internally for one second at 30 FPS so an
    # occluded forklift can be re-associated. Stale tracks are never emitted.
    max_track_age: int = 30
    track_initialization_frames: int = 2
    max_cosine_distance: float = 0.4
    embedding_budget: int = 30
    embedder_gpu: bool = False

    def __post_init__(self) -> None:
        if not 0.0 <= self.confidence <= 1.0:
            raise ValueError("confidence must be between zero and one")
        if self.image_size <= 0:
            raise ValueError("image_size must be greater than zero")
        if not 0.0 < self.max_box_area_ratio <= 1.0:
            raise ValueError("max_box_area_ratio must be within (0, 1]")
        if self.max_track_age < 1 or self.track_initialization_frames < 1:
            raise ValueError("DeepSORT frame counts must be positive")


class Detector:
    """Detect people/forklifts and assign stable DeepSORT track IDs.

    A trained VisionGuard model is expected to expose class names containing
    ``person`` (or ``worker``) and ``forklift``.  COCO's stock ``yolov8n.pt``
    has no forklift class and is therefore suitable only for smoke testing.
    """

    def __init__(
        self,
        config: DetectorConfig | None = None,
        *,
        model: Any | None = None,
        tracker: Any | None = None,
        class_map: Mapping[int, ObjectClass] | None = None,
    ) -> None:
        self.config = config or DetectorConfig()
        self.model = (
            model if model is not None else self._load_model(self.config.model_path)
        )
        self._tracker_override = tracker
        self.tracker = tracker if tracker is not None else self._build_tracker()
        self.class_map = dict(
            class_map if class_map is not None else self._infer_class_map()
        )
        self._track_metadata: dict[int, tuple[int, float]] = {}

    @staticmethod
    def _load_model(model_path: str) -> Any:
        try:
            from ultralytics import YOLO
        except ImportError as exc:  # pragma: no cover - environment dependent
            raise RuntimeError(
                "ultralytics is not installed; install AI/requirements.txt"
            ) from exc
        return YOLO(model_path)

    def _build_tracker(self) -> Any:
        try:
            from deep_sort_realtime.deepsort_tracker import DeepSort
        except ImportError as exc:  # pragma: no cover - environment dependent
            raise RuntimeError(
                "deep-sort-realtime is not installed; install AI/requirements.txt"
            ) from exc

        return DeepSort(
            max_age=self.config.max_track_age,
            n_init=self.config.track_initialization_frames,
            max_cosine_distance=self.config.max_cosine_distance,
            nn_budget=self.config.embedding_budget,
            embedder="mobilenet",
            bgr=True,
            embedder_gpu=self.config.embedder_gpu,
        )

    def _infer_class_map(self) -> dict[int, ObjectClass]:
        names = getattr(self.model, "names", {})
        items = names.items() if isinstance(names, dict) else enumerate(names)
        class_map: dict[int, ObjectClass] = {}

        for class_id, raw_name in items:
            name = str(raw_name).lower().replace("_", " ").strip()
            if name in {"person", "worker", "human"}:
                class_map[int(class_id)] = ObjectClass.PERSON
            elif name in {"forklift", "fork lift", "forklift truck"}:
                class_map[int(class_id)] = ObjectClass.FORKLIFT

        return class_map

    def reset_tracking(self) -> None:
        """Clear all DeepSORT state while retaining the loaded YOLO model."""

        if self._tracker_override is not None:
            reset = getattr(self._tracker_override, "reset", None)
            if callable(reset):
                reset()
        else:
            self.tracker = self._build_tracker()
        self._track_metadata.clear()

    def detect(self, frame: np.ndarray) -> list[Detection]:
        """Return confirmed, tracked detections for one BGR frame."""

        if not isinstance(frame, np.ndarray) or frame.ndim != 3:
            raise ValueError("frame must be a HxWxC numpy array")

        predict_options: dict[str, Any] = {
            "source": frame,
            "conf": self.config.confidence,
            "imgsz": self.config.image_size,
            "verbose": False,
        }
        if self.config.device is not None:
            predict_options["device"] = self.config.device

        results = self.model.predict(**predict_options)
        boxes = results[0].boxes if results else None
        raw_detections: list[tuple[list[float], float, int]] = []

        if boxes is not None:
            frame_height, frame_width = frame.shape[:2]
            frame_area = float(frame_width * frame_height)
            for box in boxes:
                class_id = int(box.cls[0])
                if class_id not in self.class_map:
                    continue

                confidence = float(box.conf[0])
                x1, y1, x2, y2 = (
                    box.xyxy[0].detach().cpu().numpy().astype(float).tolist()
                )
                width = x2 - x1
                height = y2 - y1
                if width <= 2 or height <= 2:
                    continue
                if width * height / frame_area > self.config.max_box_area_ratio:
                    continue
                raw_detections.append(
                    (
                        [float(x1), float(y1), float(width), float(height)],
                        confidence,
                        class_id,
                    )
                )

        tracks = self.tracker.update_tracks(raw_detections, frame=frame)
        detections: list[Detection] = []

        for track in tracks:
            # DeepSORT keeps predicting unmatched tracks until ``max_age``.
            # Those predictions are useful internally for re-association, but
            # emitting them creates stale/duplicate boxes and false risks.
            if not track.is_confirmed() or track.time_since_update > 0:
                continue

            try:
                track_id = int(track.track_id)
            except (TypeError, ValueError):
                continue

            raw_class_id = track.get_det_class()
            raw_confidence = track.get_det_conf()
            if raw_class_id is not None:
                if raw_confidence is None:
                    continue
                class_id = int(raw_class_id)
                confidence = float(raw_confidence)
                self._track_metadata[track_id] = (class_id, confidence)
            elif track_id in self._track_metadata:
                class_id, confidence = self._track_metadata[track_id]
            else:
                continue

            if class_id not in self.class_map:
                continue

            height, width = frame.shape[:2]
            # Use the box observed by YOLO in this frame, not the Kalman-filter
            # prediction. ``orig_strict`` prevents a stale fallback.
            observed_box = track.to_ltrb(orig=True, orig_strict=True)
            if observed_box is None:
                continue
            x1, y1, x2, y2 = (float(value) for value in observed_box)
            x1 = min(max(x1, 0.0), float(width))
            x2 = min(max(x2, 0.0), float(width))
            y1 = min(max(y1, 0.0), float(height))
            y2 = min(max(y2, 0.0), float(height))
            if x2 <= x1 or y2 <= y1:
                continue

            detections.append(
                Detection(
                    class_id=class_id,
                    class_name=self.class_map[class_id],
                    confidence=min(max(confidence, 0.0), 1.0),
                    bbox=BoundingBox(x1=x1, y1=y1, x2=x2, y2=y2),
                    track_id=track_id,
                )
            )

        return detections
