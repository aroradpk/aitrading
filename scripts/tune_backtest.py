#!/usr/bin/env python3
"""Grid-search conviction_min and signal_cooldown_days for backtest hit rates."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.engines.backtest import tune_backtest


def main() -> None:
    payload = tune_backtest()
    recommended = payload.get("recommended")
    print(f"Tuning grid: {len(payload['grid'])} combinations")
    if recommended:
        print(
            "Recommended:",
            f"conviction_min={recommended['conviction_min']},",
            f"cooldown={recommended['signal_cooldown_days']},",
            f"hit_1w={recommended['summary'].get('hit_1w_rate')},",
            f"signals={recommended['summary'].get('signals')}",
        )
    else:
        print("No combo met tuning_min_signals — widen grid or lower min_signals in settings.")


if __name__ == "__main__":
    main()
