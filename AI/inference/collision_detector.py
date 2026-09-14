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
    danger_hold_s: float = 1.0

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
        if self.danger_hold_s < 0:
            raise ValueError("danger_hold_s must not be negative")


@dataclass(slots=True)
class TrackState:
    """Last known position and smoothed velocity for one DeepSORT track."""

    position: np.ndarray
    bbox: np.ndarray
    velocity_px_s: np.ndarray
    last_frame_index: int

    @classmethod
    def from_detection(cls, detection: Detection, frame_index: int) -> TrackState:
        return cls(
            position=np.asarray(detection.bbox.bottom_center, dtype=np.float64),
            bbox=np.asarray(
                [
                    detection.bbox.x1,
                    detection.bbox.y1,
                    detection.bbox.x2,
                    detection.bbox.y2,
                ],
                dtype=np.float64,
            ),
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
        self.bbox = np.asarray(
            [
                detection.bbox.x1,
                detection.bbox.y1,
                detection.bbox.x2,
                detection.bbox.y2,
            ],
            dtype=np.float64,
        )
        self.last_frame_index = frame_index


class CollisionDetector:
    """Score every tracked person/forklift pair in a frame."""

    def __init__(self, config: CollisionConfig | None = None) -> None:
        self.config = config or CollisionConfig()
        self._tracks: dict[int, TrackState] = {}
        self._danger_until: dict[tuple[int, int], int] = {}

    def reset(self) -> None:
        self._tracks.clear()
        self._danger_until.clear()

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
                if detection.is_predicted:
                    continue
                self._tracks[detection.track_id] = TrackState.from_detection(
                    detection, frame_index
                )
            elif not detection.is_predicted:
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

        results = [
            self._score_pair(person_index, person, forklift_index, forklift)
            for person_index, person in people
            for forklift_index, forklift in forklifts
        ]
        hold_frames = round(self.config.danger_hold_s * fps)
        active_pairs = set()
        for result in results:
            assert result.person_track_id is not None
            assert result.forklift_track_id is not None
            pair = (result.person_track_id, result.forklift_track_id)
            active_pairs.add(pair)
            if result.level == RiskLevel.DANGER:
                self._danger_until[pair] = frame_index + hold_frames
            elif frame_index <= self._danger_until.get(pair, -1):
                result.level = RiskLevel.DANGER
                result.score = max(result.score, self.config.danger_score)
                result.reason = f"recent danger retained; {result.reason}"
        self._danger_until = {
            pair: until
            for pair, until in self._danger_until.items()
            if until >= frame_index and pair in active_pairs
        }
        return results

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
        person_future_bbox = _translate_bbox(
            person_state.bbox, person_state.velocity_px_s * closest_time
        )
        forklift_future_bbox = _translate_bbox(
            forklift_state.bbox, forklift_state.velocity_px_s * closest_time
        )
        current_box_gap = _box_gap(person_state.bbox, forklift_state.bbox)
        future_box_gap = _box_gap(person_future_bbox, forklift_future_bbox)
        closest_box_gap = min(current_box_gap, future_box_gap)
        # Perspective can make two 2-D boxes overlap even when their ground
        # contact points are safely separated. Use overlap only as supporting
        # evidence and scale the primary distance by the apparent object size.
        largest_height = max(
            person_state.bbox[3] - person_state.bbox[1],
            forklift_state.bbox[3] - forklift_state.bbox[1],
        )
        adaptive_distance = max(
            self.config.proximity_threshold_px,
            largest_height * 0.75,
        )
        center_proximity = 1.0 - min(future_distance / adaptive_distance, 1.0)
        box_proximity = 1.0 - min(
            closest_box_gap / self.config.proximity_threshold_px,
            1.0,
        )
        urgency_score = (
            1.0 - min(closest_time / self.config.future_horizon_s, 1.0)
            if approaching
            else 0.0
        )
        score = float(
            np.clip(
                55.0 * center_proximity
                + 20.0 * box_proximity
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


def _translate_bbox(bbox: np.ndarray, displacement: np.ndarray) -> np.ndarray:
    dx, dy = displacement
    return bbox + np.asarray([dx, dy, dx, dy], dtype=np.float64)


def _box_gap(first: np.ndarray, second: np.ndarray) -> float:
    """Return the shortest Euclidean distance between two axis-aligned boxes."""

    horizontal = max(first[0] - second[2], second[0] - first[2], 0.0)
    vertical = max(first[1] - second[3], second[1] - first[3], 0.0)
    return float(np.hypot(horizontal, vertical))
