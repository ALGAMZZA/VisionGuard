#!/usr/bin/env bash
set -euo pipefail
cd -- "$(dirname -- "${BASH_SOURCE[0]}")/../backend"
export AI_MODE=http
export AI_BASE_URL="${AI_BASE_URL:-http://127.0.0.1:8000}"
exec bash gradlew bootRun --args='--spring.profiles.active=demo'
