#!/usr/bin/env bash
# Run any script with the repo venv Python (Windows Git Bash + Linux/macOS).
# Usage: ./scripts/venv-python.sh scripts/scan_historical_moves.py

set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"

if [[ -x "$ROOT/.venv/Scripts/python.exe" ]]; then
  PY="$ROOT/.venv/Scripts/python.exe"
elif [[ -x "$ROOT/.venv/bin/python" ]]; then
  PY="$ROOT/.venv/bin/python"
else
  echo "No .venv found. Create it first:" >&2
  echo "  Windows PowerShell: powershell -ExecutionPolicy Bypass -File .\\scripts\\windows-install.ps1" >&2
  echo "  Linux/macOS:        ./scripts/cloud-agent-install.sh" >&2
  exit 1
fi

export PYTHONPATH="$ROOT"
exec "$PY" "$@"
