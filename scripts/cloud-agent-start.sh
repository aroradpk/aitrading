#!/usr/bin/env bash
# Start the dashboard using committed data/ only (no API fetches).
# Requires: ./scripts/cloud-agent-install.sh once
# Config:   offline_mode: true in config/settings.yaml (default)
# Open:      http://localhost:8000

set -euo pipefail

cd /workspace

# shellcheck disable=SC1091
source .venv/bin/activate
exec uvicorn app.main:app --host 0.0.0.0 --port 8000
