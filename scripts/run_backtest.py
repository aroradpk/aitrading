#!/usr/bin/env python3
"""Walk-forward backtest: did high-conviction setups hit 5%/10% targets?"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.engines.backtest import run_backtest


def main() -> None:
    payload = run_backtest()
    summary = payload["summary"]
    print(f"Backtest complete: {summary['signals']} signals")
    if summary.get("hit_1d_rate") is not None:
        print(f"  Hit {payload['config']['stock_target_1d_pct']}% (1D): {summary['hit_1d_rate']*100:.1f}%")
    if summary.get("hit_1w_rate") is not None:
        print(f"  Hit {payload['config']['stock_target_1w_pct']}% (1W): {summary['hit_1w_rate']*100:.1f}%")
    if summary.get("by_conviction_bucket"):
        print("  By conviction bucket:")
        for bucket, stats in sorted(summary["by_conviction_bucket"].items(), reverse=True):
            h1 = stats.get("hit_1d_rate")
            h1s = f"{h1*100:.0f}%" if h1 is not None else "n/a"
            print(f"    {bucket}: {stats['signals']} signals, 1D hit {h1s}")


if __name__ == "__main__":
    main()
