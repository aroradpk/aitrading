#!/usr/bin/env python3
"""Scan historical big moves and save technical snapshots."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.core.paths import ohlcv_daily_dir
from app.engines.move_detector import detect_moves, save_moves
from app.engines.universe import all_instruments, load_active_universe
from app.ingest.yfinance_client import load_ohlcv


def main() -> None:
    load_active_universe()
    instruments = all_instruments()
    print(f"Scanning moves for {len(instruments)} instruments...")

    for instrument in instruments:
        symbol = instrument["symbol"]
        instrument_type = instrument.get("type", "stock")
        path = ohlcv_daily_dir() / f"{symbol}.parquet"
        if not path.exists():
            print(f"  SKIP {symbol}: missing OHLCV")
            continue
        frame = load_ohlcv(path)
        moves = detect_moves(frame, instrument_type=instrument_type)
        if instrument_type == "stock":
            from app.engines.events import enrich_moves_with_events

            moves = enrich_moves_with_events(symbol, moves)
        save_moves(symbol, moves, frame=frame)
        print(f"  OK {symbol}: {len(moves)} moves")


if __name__ == "__main__":
    main()
