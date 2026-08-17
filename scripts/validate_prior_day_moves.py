#!/usr/bin/env python3
"""Check day-before conviction vs next-day >=5% moves for selected symbols."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.core.paths import ohlcv_daily_dir
from app.engines.conviction import conviction_from_scores
from app.engines.events import score_events
from app.engines.fundamental import score_fundamentals
from app.engines.move_detector import load_moves, scan_today_setup
from app.engines.themes import score_themes
from app.ingest.yfinance_client import load_ohlcv


def evaluate(symbol: str, move_threshold: float = 5.0, good_conv: float = 7.0) -> list[dict]:
    frame = load_ohlcv(ohlcv_daily_dir() / f"{symbol}.parquet")
    pct = frame["close"].pct_change() * 100
    rows: list[dict] = []
    for i in range(1, len(frame)):
        move_pct = pct.iloc[i]
        if pd.isna(move_pct) or abs(move_pct) < move_threshold:
            continue
        signal_idx = i - 1
        signal_date = frame.index[signal_idx].date().isoformat()
        move_date = frame.index[i].date().isoformat()
        side = "long" if move_pct > 0 else "short"
        hist = [m for m in load_moves(symbol) if m["date"] < signal_date]
        setup = scan_today_setup(
            frame.iloc[: signal_idx + 1], hist, side=side, symbol=symbol
        )
        as_of = frame.index[signal_idx].date()
        f, _ = score_fundamentals(symbol)
        e, _ = score_events(symbol, as_of=as_of)
        t, _, _ = score_themes(symbol)
        scores = conviction_from_scores(setup["technical_score"], f, e, t)
        rows.append(
            {
                "symbol": symbol,
                "signal_date": signal_date,
                "move_date": move_date,
                "move_pct": round(float(move_pct), 2),
                "side": side,
                "technical": scores["technical"],
                "conviction": scores["final"],
                "confirmations": setup.get("confirmation_labels", []),
                "hit": scores["final"] >= good_conv,
            }
        )
    return rows


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--symbols", default="ABB,MOTHERSON,ADANIPOWER")
    parser.add_argument("--good-conviction", type=float, default=7.0)
    args = parser.parse_args()

    symbols = [s.strip().upper() for s in args.symbols.split(",") if s.strip()]
    all_rows: list[dict] = []
    for symbol in symbols:
        all_rows.extend(evaluate(symbol, good_conv=args.good_conviction))

    hits = [r for r in all_rows if r["hit"]]
    print(f"Total 5%+ moves: {len(all_rows)}")
    print(f"Day-before conviction >= {args.good_conviction}: {len(hits)} ({100*len(hits)/max(1,len(all_rows)):.1f}%)")
    print("\nHits:")
    for r in hits:
        print(
            f"  {r['symbol']} signal={r['signal_date']} -> {r['move_date']} {r['move_pct']:+.1f}% "
            f"conv={r['conviction']} tech={r['technical']}"
        )
    print("\nRecent misses (2025+):")
    for r in sorted([x for x in all_rows if not x["hit"] and x["move_date"] >= "2025-01-01"], key=lambda x: x["move_date"])[-15:]:
        print(
            f"  {r['symbol']} {r['signal_date']} -> {r['move_date']} {r['move_pct']:+.1f}% conv={r['conviction']} tech={r['technical']}"
        )


if __name__ == "__main__":
    main()
