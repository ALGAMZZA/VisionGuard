"""FastAPI application entry point for the VisionGuard prediction server."""

from __future__ import annotations

import os
from threading import Lock
from typing import Annotated, Any

import cv2
import numpy as np
from fastapi import FastAPI, File, HTTPException, Query, UploadFile
from starlette.concurrency import run_in_threadpool

from AI.inference.detector import Detector, DetectorConfig
from AI.inference.predictor import Predictor
from AI.inference.schemas import PredictionResult

MAX_UPLOAD_BYTES = 25 * 1024 * 1024

app = FastAPI(title="VisionGuard AI", version="0.2.0")

# One Predictor per camera/stream.
# Each Predictor owns its own DeepSORT + collision history.
_predictors: dict[str, Predictor] = {}

# YOLO model is shared by every stream.
_shared_model: Any | None = None
_shared_class_map = None
_detector_config: DetectorConfig | None = None

_predictor_lock = Lock()

# The shared YOLO model is used serially.
# camera-1/2 state is still independent because each Predictor has its own tracker.
_inference_lock = Lock()


def _scope_key(camera_id: str, stream_id: str) -> str:
    return f"{camera_id}\0{stream_id}"


def _get_detector_config() -> DetectorConfig:
    global _detector_config

    if _detector_config is None:
        device = os.getenv("VISIONGUARD_DEVICE") or None

        _detector_config = DetectorConfig(
            model_path=os.getenv(
                "VISIONGUARD_MODEL_PATH",
                "AI/models/production/best.pt",
            ),
            confidence=float(
                os.getenv("VISIONGUARD_CONFIDENCE", "0.35")
            ),
            person_confidence=float(
                os.getenv("VISIONGUARD_PERSON_CONFIDENCE", "0.50")
            ),
            forklift_confidence=float(
                os.getenv("VISIONGUARD_FORKLIFT_CONFIDENCE", "0.60")
            ),
            image_size=int(
                os.getenv("VISIONGUARD_IMAGE_SIZE", "640")
            ),
            device=device,
        )

    return _detector_config


def _get_predictor(camera_id: str, stream_id: str) -> Predictor:
    global _shared_model, _shared_class_map

    scope = _scope_key(camera_id, stream_id)

    with _predictor_lock:
        existing = _predictors.get(scope)
        if existing is not None:
            return existing

        config = _get_detector_config()

        if _shared_model is None:
            # First stream loads YOLO normally.
            detector = Detector(config)

            # Subsequent streams reuse only the YOLO model/class map.
            # Each new Detector still gets its own DeepSORT tracker.
            _shared_model = detector.model
            _shared_class_map = dict(detector.class_map)
        else:
            detector = Detector(
                config,
                model=_shared_model,
                class_map=_shared_class_map,
            )

        predictor = Predictor(detector)
        _predictors[scope] = predictor

        return predictor


@app.get("/health")
def health() -> dict[str, str | bool | int]:
    """Report API health without forcing the model to load."""

    return {
        "status": "ok",
        "model_loaded": _shared_model is not None,
        "active_streams": len(_predictors),
    }


@app.post("/predict", response_model=PredictionResult)
async def predict_image(
    file: Annotated[UploadFile, File()],
    camera_id: Annotated[str, Query(min_length=1, max_length=100)],
    stream_id: Annotated[str, Query(min_length=1, max_length=100)],
    frame_id: Annotated[str | None, Query()] = None,
    fps: Annotated[float, Query(gt=0, le=240)] = 30.0,
) -> PredictionResult:
    """Run inference using independent state for one camera/stream."""

    payload = await file.read(MAX_UPLOAD_BYTES + 1)

    if len(payload) > MAX_UPLOAD_BYTES:
        raise HTTPException(
            status_code=413,
            detail="image exceeds 25 MiB limit",
        )

    frame = cv2.imdecode(
        np.frombuffer(payload, dtype=np.uint8),
        cv2.IMREAD_COLOR,
    )

    if frame is None:
        raise HTTPException(
            status_code=400,
            detail="invalid or unsupported image",
        )

    def run_prediction() -> PredictionResult:
        with _inference_lock:
            predictor = _get_predictor(camera_id, stream_id)

            return predictor.predict(
                frame,
                frame_id=frame_id,
                fps=fps,
            )

    return await run_in_threadpool(run_prediction)


@app.post("/reset")
def reset_stream(
    camera_id: Annotated[str | None, Query(min_length=1, max_length=100)] = None,
    stream_id: Annotated[str | None, Query(min_length=1, max_length=100)] = None,
) -> dict[str, str | int]:
    """
    Reset one camera/stream.

    Calling /reset without parameters remains supported and resets all
    streams for compatibility with existing smoke-test scripts.
    """

    if (camera_id is None) != (stream_id is None):
        raise HTTPException(
            status_code=400,
            detail="camera_id and stream_id must be provided together",
        )

    with _inference_lock:
        if camera_id is None:
            with _predictor_lock:
                predictors = list(_predictors.values())
                _predictors.clear()

            for predictor in predictors:
                predictor.reset()

            return {
                "status": "reset",
                "reset_streams": len(predictors),
            }

        scope = _scope_key(camera_id, stream_id)

        with _predictor_lock:
            predictor = _predictors.pop(scope, None)

        if predictor is not None:
            predictor.reset()

        return {
            "status": "reset",
            "reset_streams": 1 if predictor is not None else 0,
        }
