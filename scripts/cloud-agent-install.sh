#!/usr/bin/env bash
set -euo pipefail

cd /workspace

if [[ ! -d .venv ]]; then
  python3 -m venv .venv
fi

# shellcheck disable=SC1091
source .venv/bin/activate
python -m pip install --upgrade pip
pip install -r requirements.txt

echo ""
echo "Install complete. Offline start (no Yahoo/NSE/PIB — uses committed data/):"
echo "  ./scripts/cloud-agent-start.sh"
echo ""
echo "Optional rebuild watchlist from disk only:"
echo "  source .venv/bin/activate && python scripts/run_pipeline.py"
echo ""
echo "To refresh from the web: set offline_mode: false in config/settings.yaml, then run_pipeline.py"
