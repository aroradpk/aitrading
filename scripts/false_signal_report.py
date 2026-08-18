#!/usr/bin/env python3
"""False-conviction report: random non-5% days vs true 5% days, all universe stocks."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.core.paths import ohlcv_daily_dir
from app.engines.pattern_confirmations import detect_daily_confirmations
from app.engines.pattern_scoring import score_technical_confirmations
from app.engines.technical import build_snapshot
from app.ingest.yfinance_client import load_ohlcv

SYMBOLS = [
    "ABB",
    "MOTHERSON",
    "ADANIPOWER",
    "ADANIENSOL",
    "TMCV",
    "ADANIGREEN",
    "TVSMOTOR",
    "CUMMINSIND",
    "DIVISLAB",
    "UNIONBANK",
    "SOLARINDS",
    "HINDZINC",
    "TORNTPHARM",
    "CGPOWER",
    "SIEMENS",
    "CHOLAFIN",
    "CANBK",
    "BOSCHLTD",
    "ZYDUSLIFE",
    "UNITDSPR",
]


def high_conviction(frame: pd.DataFrame, side: str) -> bool:
    conf = detect_daily_confirmations(frame, side)
    snap = build_snapshot(frame, focus=side)
    scored = score_technical_confirmations(conf, side=side, snapshot=snap)
    return scored["technical_score"] >= 7.0


def evaluate_symbol(symbol: str, quiet_sample: int, rng: np.random.Generator) -> dict:
    frame = load_ohlcv(ohlcv_daily_dir() / f"{symbol}.parquet")
    pct = frame["close"].pct_change() * 100
    big_idx: list[int] = []
    quiet_idx: list[int] = []
    for i in range(40, len(frame) - 1):
        nxt = pct.iloc[i + 1]
        if pd.isna(nxt):
            continue
        if abs(float(nxt)) >= 5:
            big_idx.append(i)
        else:
            quiet_idx.append(i)

    sample = list(rng.choice(quiet_idx, size=min(quiet_sample, len(quiet_idx)), replace=False))
    tp = fn = fp = tn = 0
    for i in big_idx:
        nxt = float(pct.iloc[i + 1])
        side = "long" if nxt > 0 else "short"
        if high_conviction(frame.iloc[: i + 1], side):
            tp += 1
        else:
            fn += 1
    for i in sample:
        sl = frame.iloc[: i + 1]
        fired = high_conviction(sl, "long") or high_conviction(sl, "short")
        if fired:
            fp += 1
        else:
            tn += 1

    n_big = tp + fn
    n_quiet = fp + tn
    return {
        "symbol": symbol,
        "true_5pct_days": n_big,
        "quiet_sampled": n_quiet,
        "true_hits_ge7": tp,
        "recall_pct": round(100 * tp / n_big, 1) if n_big else 0.0,
        "false_signals": fp,
        "false_rate_pct": round(100 * fp / n_quiet, 1) if n_quiet else 0.0,
    }


def main() -> None:
    rng = np.random.default_rng(42)
    rows = [evaluate_symbol(symbol, 80, rng) for symbol in SYMBOLS]
    for row in rows:
        print(
            f"{row['symbol']:12} quiet={row['quiet_sampled']:3} FP={row['false_signals']:3} "
            f"FPR={row['false_rate_pct']:5.1f}%  5%days={row['true_5pct_days']:3} "
            f"hits={row['true_hits_ge7']:3} recall={row['recall_pct']:5.1f}%",
            flush=True,
        )
    n_q = sum(r["quiet_sampled"] for r in rows)
    n_fp = sum(r["false_signals"] for r in rows)
    n_b = sum(r["true_5pct_days"] for r in rows)
    n_tp = sum(r["true_hits_ge7"] for r in rows)
    overall = {
        "quiet_sampled": n_q,
        "false_signals": n_fp,
        "false_rate_pct": round(100 * n_fp / n_q, 1) if n_q else 0.0,
        "true_5pct_days": n_b,
        "true_hits_ge7": n_tp,
        "recall_pct": round(100 * n_tp / n_b, 1) if n_b else 0.0,
        "per_symbol": rows,
    }
    out = Path("/opt/cursor/artifacts/false_signal_report.json")
    out.write_text(json.dumps(overall, indent=2), encoding="utf-8")
    print("\nOVERALL", overall["false_rate_pct"], "FPR", overall["recall_pct"], "recall")
    print("wrote", out)


if __name__ == "__main__":
    main()
