#!/usr/bin/env python3
"""Download daily OHLCV for active universe into data/ohlcv/daily/."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.core.config import get_settings
from app.core.paths import ohlcv_daily_dir
from app.engines.universe import all_instruments, load_active_universe
from app.ingest.yfinance_client import fetch_ohlcv, save_ohlcv


def main() -> None:
    settings = get_settings()
    if settings.offline_mode:
        print("offline_mode=true — skipping OHLCV download (use saved parquet files)")
        return

    universe = load_active_universe()
    instruments = all_instruments()
    print(f"Fetching OHLCV for {len(instruments)} instruments...")

    for instrument in instruments:
        symbol = instrument["symbol"]
        instrument_type = instrument.get("type", "stock")
        output = ohlcv_daily_dir() / f"{symbol}.parquet"
        try:
            frame = fetch_ohlcv(
                symbol,
                instrument_type=instrument_type,
                yahoo=instrument.get("yahoo"),
            )
            save_ohlcv(frame, output)
            print(f"  OK {symbol}: {len(frame)} rows -> {output}")
        except Exception as exc:  # noqa: BLE001
            print(f"  FAIL {symbol}: {exc}")


if __name__ == "__main__":
    main()
