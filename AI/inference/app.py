"""FastAPI application entry point for the VisionGuard prediction server."""

from __future__ import annotations

import os
from threading import Lock
from typing import Annotated

import cv2
import numpy as np
from fastapi import FastAPI, File, HTTPException, Query, UploadFile
from starlette.concurrency import run_in_threadpool

from AI.inference.detector import Detector, DetectorConfig
from AI.inference.predictor import Predictor
from AI.inference.schemas import PredictionResult

MAX_UPLOAD_BYTES = 25 * 1024 * 1024

app = FastAPI(title="VisionGuard AI", version="0.1.0")
_predictor: Predictor | None = None
_predictor_lock = Lock()
_inference_lock = Lock()


def _get_predictor() -> Predictor:
    global _predictor
    with _predictor_lock:
        if _predictor is None:
            device = os.getenv("VISIONGUARD_DEVICE") or None
            detector = Detector(
                DetectorConfig(
                    model_path=os.getenv(
                        "VISIONGUARD_MODEL_PATH",
                        "AI/models/production/best.pt",
                    ),
                    confidence=float(os.getenv("VISIONGUARD_CONFIDENCE", "0.35")),
                    image_size=int(os.getenv("VISIONGUARD_IMAGE_SIZE", "640")),
                    device=device,
                )
            )
            _predictor = Predictor(detector)
    return _predictor


@app.get("/health")
def health() -> dict[str, str | bool]:
    """Report API health without forcing the model to load."""

    return {"status": "ok", "model_loaded": _predictor is not None}


@app.post("/predict", response_model=PredictionResult)
async def predict_image(
    file: Annotated[UploadFile, File()],
    frame_id: Annotated[str | None, Query()] = None,
    fps: Annotated[float, Query(gt=0, le=240)] = 30.0,
) -> PredictionResult:
    """Run stateful inference for the next frame of a single video stream."""

    payload = await file.read(MAX_UPLOAD_BYTES + 1)
    if len(payload) > MAX_UPLOAD_BYTES:
        raise HTTPException(status_code=413, detail="image exceeds 25 MiB limit")

    frame = cv2.imdecode(np.frombuffer(payload, dtype=np.uint8), cv2.IMREAD_COLOR)
    if frame is None:
        raise HTTPException(status_code=400, detail="invalid or unsupported image")

    def run_prediction() -> PredictionResult:
        with _inference_lock:
            return _get_predictor().predict(frame, frame_id=frame_id, fps=fps)

    return await run_in_threadpool(run_prediction)


@app.post("/reset")
def reset_stream() -> dict[str, str]:
    """Clear tracking history before starting a different video stream."""

    if _predictor is not None:
        with _inference_lock:
            _predictor.reset()
    return {"status": "reset"}
