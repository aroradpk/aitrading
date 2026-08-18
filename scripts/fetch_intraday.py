#!/usr/bin/env python3
"""Download 15m and 1h OHLCV (Yahoo ~60-day window) into data/ohlcv/{15m,1h}/."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.core.config import get_settings
from app.engines.mtf_analysis import fetch_intraday
from app.engines.universe import all_instruments, load_active_universe


def main() -> None:
    settings = get_settings()
    if settings.offline_mode:
        print("offline_mode=true — skipping 15m/1h download (use saved parquet files if present)")
        return

    load_active_universe()
    instruments = [i for i in all_instruments() if i.get("type", "stock") == "stock"]
    print(f"Fetching 15m/1h for {len(instruments)} stocks...")

    for instrument in instruments:
        symbol = instrument["symbol"]
        for interval in ("15m", "1h"):
            try:
                frame = fetch_intraday(symbol, interval)
                print(f"  OK {symbol} {interval}: {len(frame)} bars")
            except Exception as exc:  # noqa: BLE001
                print(f"  FAIL {symbol} {interval}: {exc}")


if __name__ == "__main__":
    main()
