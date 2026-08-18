#!/usr/bin/env python3
"""Day-before 5% catch: rumble 7 vs quiet FPR. Never scores the 5% close itself."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.core.paths import ohlcv_daily_dir, universe_dir
from app.engines.pattern_confirmations import detect_energy_triggers
from app.ingest.yfinance_client import load_ohlcv

SEED = 42
QUIET = 80
OUT = Path("/opt/cursor/artifacts/day_before_60.json")


def symbols() -> list[str]:
    next50 = [s["symbol"] for s in json.loads((universe_dir() / "active.json").read_text())["stocks"]]
    extra_path = Path("config/nifty_50_top20.json")
    extra: list[str] = []
    if extra_path.exists():
        extra = [s["symbol"] for s in json.loads(extra_path.read_text())["stocks"]]
        extra = [s for s in extra if (ohlcv_daily_dir() / f"{s}.parquet").exists()]
    return list(dict.fromkeys(next50 + extra))


def fires(frame: pd.DataFrame) -> bool:
    return bool(detect_energy_triggers(frame).get("setup_rattle"))


def main() -> None:
    rng = np.random.default_rng(SEED)
    tp = fp = n5 = nq = 0
    per: list[dict] = []
    for sym in symbols():
        frame = load_ohlcv(ohlcv_daily_dir() / f"{sym}.parquet")
        ret = frame["close"].pct_change() * 100
        big_idx, quiet_idx = [], []
        for i in range(40, len(frame) - 1):
            nxt = ret.iloc[i + 1]
            if pd.isna(nxt):
                continue
            (big_idx if abs(float(nxt)) >= 5 else quiet_idx).append(i)
        sample = list(rng.choice(quiet_idx, size=min(QUIET, len(quiet_idx)), replace=False)) if quiet_idx else []
        hits = sum(1 for i in big_idx if fires(frame.iloc[: i + 1]))
        false = sum(1 for i in sample if fires(frame.iloc[: i + 1]))
        n5 += len(big_idx)
        nq += len(sample)
        tp += hits
        fp += false
        rec = 100 * hits / len(big_idx) if big_idx else 0
        fpr = 100 * false / len(sample) if sample else 0
        per.append({"symbol": sym, "n5": len(big_idx), "recall": round(rec, 1), "fpr": round(fpr, 1), "hits": hits})
        print(f"{sym:12} n5={len(big_idx):3d} rec={rec:5.1f}% fpr={fpr:5.1f}%")
    overall_rec = round(100 * tp / n5, 1) if n5 else 0
    overall_fpr = round(100 * fp / nq, 1) if nq else 0
    print("OVERALL", overall_rec, "recall", overall_fpr, "fpr", f"({tp}/{n5} vs {fp}/{nq})")
    OUT.write_text(
        json.dumps(
            {
                "overall_recall": overall_rec,
                "overall_fpr": overall_fpr,
                "tp": tp,
                "n5": n5,
                "fp": fp,
                "nq": nq,
                "per_symbol": per,
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
