"""Collision-risk assessment using tracked detections and motion history."""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from AI.inference.schemas import Detection, ObjectClass, RiskLevel, RiskResult


@dataclass(frozen=True, slots=True)
class CollisionConfig:
    """Thresholds for the constant-velocity collision approximation."""

    future_horizon_s: float = 4.0
    proximity_threshold_px: float = 120.0
    warning_score: float = 35.0
    danger_score: float = 65.0
    velocity_smoothing: float = 0.2
    stale_after_frames: int = 30

    def __post_init__(self) -> None:
        if self.future_horizon_s <= 0 or self.proximity_threshold_px <= 0:
            raise ValueError(
                "collision horizon and distance threshold must be positive"
            )
        if not 0.0 <= self.velocity_smoothing <= 1.0:
            raise ValueError("velocity_smoothing must be between zero and one")
        if not 0.0 <= self.warning_score <= self.danger_score <= 100.0:
            raise ValueError("risk score thresholds must be ordered within 0..100")
        if self.stale_after_frames < 1:
            raise ValueError("stale_after_frames must be positive")


@dataclass(slots=True)
class TrackState:
    """Last known position and smoothed velocity for one DeepSORT track."""

    position: np.ndarray
    velocity_px_s: np.ndarray
    last_frame_index: int

    @classmethod
    def from_detection(cls, detection: Detection, frame_index: int) -> TrackState:
        return cls(
            position=np.asarray(detection.bbox.bottom_center, dtype=np.float64),
            velocity_px_s=np.zeros(2, dtype=np.float64),
            last_frame_index=frame_index,
        )

    def update(
        self,
        detection: Detection,
        frame_index: int,
        fps: float,
        smoothing: float,
    ) -> None:
        new_position = np.asarray(detection.bbox.bottom_center, dtype=np.float64)
        elapsed_frames = max(frame_index - self.last_frame_index, 1)
        elapsed_seconds = elapsed_frames / fps
        measured_velocity = (new_position - self.position) / elapsed_seconds
        self.velocity_px_s = (
            1.0 - smoothing
        ) * self.velocity_px_s + smoothing * measured_velocity
        self.position = new_position
        self.last_frame_index = frame_index


class CollisionDetector:
    """Score every tracked person/forklift pair in a frame."""

    def __init__(self, config: CollisionConfig | None = None) -> None:
        self.config = config or CollisionConfig()
        self._tracks: dict[int, TrackState] = {}

    def reset(self) -> None:
        self._tracks.clear()

    def assess(
        self,
        detections: list[Detection],
        *,
        frame_index: int,
        fps: float = 30.0,
    ) -> list[RiskResult]:
        """Update motion state and return risk results for the current frame."""

        if fps <= 0:
            raise ValueError("fps must be greater than zero")

        for detection in detections:
            if detection.track_id is None:
                continue
            state = self._tracks.get(detection.track_id)
            if state is None:
                self._tracks[detection.track_id] = TrackState.from_detection(
                    detection, frame_index
                )
            else:
                state.update(
                    detection,
                    frame_index,
                    fps,
                    self.config.velocity_smoothing,
                )

        stale_ids = [
            track_id
            for track_id, state in self._tracks.items()
            if frame_index - state.last_frame_index > self.config.stale_after_frames
        ]
        for track_id in stale_ids:
            del self._tracks[track_id]

        people = [
            (index, detection)
            for index, detection in enumerate(detections)
            if detection.class_name == ObjectClass.PERSON
            and detection.track_id is not None
        ]
        forklifts = [
            (index, detection)
            for index, detection in enumerate(detections)
            if detection.class_name == ObjectClass.FORKLIFT
            and detection.track_id is not None
        ]

        return [
            self._score_pair(person_index, person, forklift_index, forklift)
            for person_index, person in people
            for forklift_index, forklift in forklifts
        ]

    def _score_pair(
        self,
        person_index: int,
        person: Detection,
        forklift_index: int,
        forklift: Detection,
    ) -> RiskResult:
        assert person.track_id is not None
        assert forklift.track_id is not None
        person_state = self._tracks[person.track_id]
        forklift_state = self._tracks[forklift.track_id]

        relative_position = person_state.position - forklift_state.position
        relative_velocity = person_state.velocity_px_s - forklift_state.velocity_px_s
        current_distance = float(np.linalg.norm(relative_position))
        relative_speed_squared = float(np.dot(relative_velocity, relative_velocity))
        approaching = float(np.dot(relative_position, relative_velocity)) < 0

        if approaching and relative_speed_squared > 1e-9:
            closest_time = (
                -float(np.dot(relative_position, relative_velocity))
                / relative_speed_squared
            )
            closest_time = min(max(closest_time, 0.0), self.config.future_horizon_s)
        else:
            closest_time = 0.0

        closest_position = relative_position + relative_velocity * closest_time
        future_distance = float(np.linalg.norm(closest_position))
        proximity_score = 1.0 - min(
            future_distance / self.config.proximity_threshold_px,
            1.0,
        )
        urgency_score = (
            1.0 - min(closest_time / self.config.future_horizon_s, 1.0)
            if approaching
            else 0.0
        )
        score = float(
            np.clip(
                75.0 * proximity_score
                + 15.0 * urgency_score
                + (10.0 if approaching else 0.0),
                0.0,
                100.0,
            )
        )

        if score >= self.config.danger_score:
            level = RiskLevel.DANGER
        elif score >= self.config.warning_score:
            level = RiskLevel.WARNING
        else:
            level = RiskLevel.SAFE

        if approaching:
            reason = (
                f"closest approach {future_distance:.1f}px "
                f"in {closest_time:.2f}s; objects are approaching"
            )
        else:
            reason = f"current separation {current_distance:.1f}px; not approaching"

        return RiskResult(
            level=level,
            person_index=person_index,
            forklift_index=forklift_index,
            person_track_id=person.track_id,
            forklift_track_id=forklift.track_id,
            distance_px=current_distance,
            future_distance_px=future_distance,
            time_to_closest_approach_s=closest_time if approaching else None,
            score=score,
            reason=reason,
        )
