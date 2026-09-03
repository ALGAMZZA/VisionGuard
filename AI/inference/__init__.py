"""Online object detection and collision-risk inference package."""

from AI.inference.schemas import (
    BoundingBox,
    Detection,
    ObjectClass,
    PredictionResult,
    RiskLevel,
    RiskResult,
)

__all__ = [
    "BoundingBox",
    "Detection",
    "ObjectClass",
    "PredictionResult",
    "RiskLevel",
    "RiskResult",
]
