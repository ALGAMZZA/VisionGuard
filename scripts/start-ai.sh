#!/usr/bin/env bash
set -euo pipefail
cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.."
export VISIONGUARD_MODEL_PATH="${VISIONGUARD_MODEL_PATH:-AI/models/production/best.pt}"
export VISIONGUARD_DEVICE="${VISIONGUARD_DEVICE:-cpu}"
export OMP_NUM_THREADS="${OMP_NUM_THREADS:-4}"
export MKL_NUM_THREADS="${MKL_NUM_THREADS:-4}"
if [[ ! -f "$VISIONGUARD_MODEL_PATH" ]]; then
  echo "모델 파일을 찾을 수 없습니다: $VISIONGUARD_MODEL_PATH" >&2
  exit 1
fi
exec AI/.venv/bin/python -m uvicorn AI.inference.app:app --host 127.0.0.1 --port 8000
