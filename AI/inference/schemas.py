"""Shared data models for the VisionGuard inference pipeline.

These models are used first as the contract between ``detector``,
``collision_detector`` and ``predictor``.  FastAPI can later reuse
``PredictionResult`` as its response model when the backend contract is fixed.
"""

from enum import Enum

from pydantic import BaseModel, ConfigDict, Field, model_validator


class SchemaModel(BaseModel):
    """Base settings shared by all inference schemas."""

    model_config = ConfigDict(extra="forbid")


class ObjectClass(str, Enum):
    """Object classes used by the collision detection service."""

    PERSON = "person"
    FORKLIFT = "forklift"


class RiskLevel(str, Enum):
    """Collision-risk severity in ascending order."""

    SAFE = "SAFE"
    WARNING = "WARNING"
    DANGER = "DANGER"


class BoundingBox(SchemaModel):
    """Pixel coordinates in ``(left, top, right, bottom)`` form."""

    x1: float = Field(ge=0)
    y1: float = Field(ge=0)
    x2: float = Field(ge=0)
    y2: float = Field(ge=0)

    @model_validator(mode="after")
    def validate_coordinate_order(self) -> "BoundingBox":
        if self.x2 <= self.x1:
            raise ValueError("x2 must be greater than x1")
        if self.y2 <= self.y1:
            raise ValueError("y2 must be greater than y1")
        return self

    @property
    def bottom_center(self) -> tuple[float, float]:
        """Return the ground-contact approximation used for distance checks."""

        return ((self.x1 + self.x2) / 2, self.y2)


class Detection(SchemaModel):
    """One normalized detection returned by ``Detector``."""

    class_id: int = Field(ge=0)
    class_name: ObjectClass
    confidence: float = Field(ge=0, le=1)
    bbox: BoundingBox
    track_id: int | None = Field(default=None, ge=0)


class RiskResult(SchemaModel):
    """Risk assessment for one person/forklift pair."""

    level: RiskLevel
    person_index: int = Field(ge=0)
    forklift_index: int = Field(ge=0)
    distance_px: float = Field(ge=0)
    reason: str


class PredictionResult(SchemaModel):
    """Combined result produced by ``Predictor`` for a single frame."""

    frame_id: str | None = None
    image_width: int = Field(gt=0)
    image_height: int = Field(gt=0)
    detections: list[Detection] = Field(default_factory=list)
    risks: list[RiskResult] = Field(default_factory=list)
    overall_risk: RiskLevel = RiskLevel.SAFE
    processing_time_ms: float = Field(ge=0)

