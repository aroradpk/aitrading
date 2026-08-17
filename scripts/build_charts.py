#!/usr/bin/env python3
"""Generate PNG charts for existing moves (no move rescan)."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import json

from app.core.paths import moves_dir, ohlcv_daily_dir
from app.engines.chart_render import render_charts_for_moves
from app.engines.universe import all_instruments, load_active_universe
from app.ingest.yfinance_client import load_ohlcv


def main() -> None:
    load_active_universe()
    total = 0
    for instrument in all_instruments():
        symbol = instrument["symbol"]
        summary_path = moves_dir() / symbol / "_summary.json"
        ohlcv_path = ohlcv_daily_dir() / f"{symbol}.parquet"
        if not summary_path.exists() or not ohlcv_path.exists():
            continue
        moves = json.loads(summary_path.read_text(encoding="utf-8")).get("moves", [])
        frame = load_ohlcv(ohlcv_path)
        count = render_charts_for_moves(symbol, frame, moves)
        summary_path.write_text(
            json.dumps({"symbol": symbol, "count": len(moves), "moves": moves}, indent=2),
            encoding="utf-8",
        )
        for move in moves:
            day_path = moves_dir() / symbol / f"{move['date']}.json"
            day_path.write_text(json.dumps(move, indent=2), encoding="utf-8")
        total += count
        print(f"  {symbol}: {count} charts")
    print(f"Done — {total} chart PNGs in data/technical/charts/")


if __name__ == "__main__":
    main()
