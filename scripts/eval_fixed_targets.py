#!/usr/bin/env python3
"""Legacy live-volume vs next-session range counts.

Prefer scripts/study_target_days.py — days that already printed the book % rise,
with technical flags, newest first. This file is the old 7-gate scoreboard.
"""

from __future__ import annotations

import json
import sys
from collections import defaultdict
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.core.paths import ohlcv_daily_dir
from app.engines.adr import attach_adr, target_for
from app.engines.universe import load_trading_instruments
from app.ingest.yfinance_client import load_ohlcv


def evaluate(*, lookback: int | None) -> dict:
    rows = []
    for entry in load_trading_instruments():
        symbol = entry["symbol"]
        target = target_for(symbol)
        frame = attach_adr(load_ohlcv(ohlcv_daily_dir() / f"{symbol}.parquet"))
        vol_mean = frame["volume"].rolling(20).mean()
        live = frame["volume"] / vol_mean >= 1.5
        prev = frame["close"].shift(1)
        day_pct = (frame["close"] / prev - 1).abs() * 100
        late = day_pct >= 5.0
        fire = live.fillna(False) & ~late.fillna(False)
        nxt_range = frame["range_pct"].shift(-1)
        nxt_high = frame["high"].shift(-1)
        nxt_low = frame["low"].shift(-1)
        mfe = pd.concat(
            [
                (nxt_high / frame["close"] - 1).abs() * 100,
                (nxt_low / frame["close"] - 1).abs() * 100,
            ],
            axis=1,
        ).max(axis=1)

        valid = frame.iloc[40:-1]
        if lookback:
            valid = valid.tail(lookback)
        idx = valid.index
        n_days = len(idx)
        hits_all = int((nxt_range.loc[idx] >= target).sum())
        trade_idx = idx[fire.loc[idx].to_numpy()]
        trades = len(trade_idx)
        correct_range = int((nxt_range.loc[trade_idx] >= target).sum()) if trades else 0
        correct_mfe = int((mfe.loc[trade_idx] >= target).sum()) if trades else 0
        false_range = trades - correct_range
        false_mfe = trades - correct_mfe
        rows.append(
            {
                "symbol": symbol,
                "target_pct": target,
                "days": n_days,
                "base_hit_pct": round(100 * hits_all / n_days, 1) if n_days else None,
                "trades": trades,
                "correct_range": correct_range,
                "false_range": false_range,
                "correct_range_pct": round(100 * correct_range / trades, 1) if trades else None,
                "false_range_pct": round(100 * false_range / trades, 1) if trades else None,
                "correct_mfe": correct_mfe,
                "false_mfe": false_mfe,
                "correct_mfe_pct": round(100 * correct_mfe / trades, 1) if trades else None,
            }
        )
    totals = defaultdict(int)
    for row in rows:
        for key in ("days", "trades", "correct_range", "false_range", "correct_mfe", "false_mfe"):
            totals[key] += row[key]
    return {
        "lookback_bars": lookback,
        "hit": "next session (high-low)/prior close >= target",
        "trade": "7 = live volume >= 1.5x on setup day, one per name per day",
        "per_symbol": rows,
        "all": {
            "days": totals["days"],
            "trades": totals["trades"],
            "correct": totals["correct_range"],
            "false_signals": totals["false_range"],
            "correct_pct": round(100 * totals["correct_range"] / totals["trades"], 1)
            if totals["trades"]
            else None,
            "false_pct": round(100 * totals["false_range"] / totals["trades"], 1)
            if totals["trades"]
            else None,
            "correct_mfe": totals["correct_mfe"],
            "false_mfe": totals["false_mfe"],
        },
    }


def main() -> None:
    year = evaluate(lookback=252)
    full = evaluate(lookback=None)
    payload = {"last_252_sessions": year, "full_history": full}
    out = Path("/opt/cursor/artifacts/fixed_target_trade_scoreboard.json")
    out.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    txt = Path("/opt/cursor/artifacts/fixed_target_trade_scoreboard.txt")

    lines: list[str] = []

    def dump(title: str, block: dict) -> None:
        lines.append(title)
        lines.append(
            f"{'symbol':12} {'tgt':5} {'days':5} {'base%':6} {'trades':6} "
            f"{'correct':7} {'false':6} {'hit%':6} {'FA%':6}"
        )
        for row in block["per_symbol"]:
            lines.append(
                f"{row['symbol']:12} {row['target_pct']:5.1f} {row['days']:5} "
                f"{row['base_hit_pct']:6.1f} {row['trades']:6} "
                f"{row['correct_range']:7} {row['false_range']:6} "
                f"{(row['correct_range_pct'] or 0):6.1f} {(row['false_range_pct'] or 0):6.1f}"
            )
        tot = block["all"]
        lines.append(
            f"{'ALL':12} {'':5} {tot['days']:5} {'':6} {tot['trades']:6} "
            f"{tot['correct']:7} {tot['false_signals']:6} "
            f"{(tot['correct_pct'] or 0):6.1f} {(tot['false_pct'] or 0):6.1f}"
        )
        lines.append("")

    dump("Last ~252 sessions (1 year)", year)
    dump("Full committed history", full)
    text = "\n".join(lines)
    txt.write_text(text + "\n", encoding="utf-8")
    print(text)
    print(f"Wrote {out}")


if __name__ == "__main__":
    main()
