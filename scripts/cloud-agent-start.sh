#!/usr/bin/env bash
set -euo pipefail

cd /workspace

# shellcheck disable=SC1091
source .venv/bin/activate
exec uvicorn app.main:app --host 0.0.0.0 --port 8000
