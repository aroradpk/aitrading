#!/usr/bin/env python3
"""Run full local data pipeline: universe -> OHLCV -> moves -> watchlist."""

import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.core.config import get_settings


def run(script: str) -> None:
    path = ROOT / "scripts" / script
    print(f"\n==> {script}")
    env = {**os.environ, "PYTHONPATH": str(ROOT)}
    subprocess.run([sys.executable, str(path)], check=True, cwd=str(ROOT), env=env)


def main() -> None:
    settings = get_settings()
    if settings.offline_mode:
        print("offline_mode=true — using saved data/ only (no Yahoo/NSE/PIB fetches)")
        run("build_theme_scores.py")
        run("build_watchlist.py")
        print("\nOffline pipeline complete. Visit http://localhost:8000")
        return

    run("build_universe.py")
    run("fetch_ohlcv.py")
    run("fetch_events.py")
    run("import_fundamentals.py")
    run("scan_historical_moves.py")
    run("build_theme_scores.py")
    run("build_watchlist.py")
    print("\nPipeline complete. Open data/ in VS Code or visit http://localhost:8000")


if __name__ == "__main__":
    main()
