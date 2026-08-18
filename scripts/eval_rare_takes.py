#!/usr/bin/env python3
"""Score the rare 1-trade/day open take (gap 75–99% of the book target)."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.engines.target_trade import TAKE_GAP_FRAC, classify_open_gap, pick_daily_takes


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--cache", type=Path, default=Path("/tmp/target_setup_rows.parquet"))
    args = parser.parse_args()
    if not args.cache.exists():
        print("Run scripts/eval_target_setups.py once to build", args.cache, file=sys.stderr)
        sys.exit(1)
    frame = pd.read_parquet(args.cache)
    rows = []
    for _, row in frame.iterrows():
        info = classify_open_gap(row["next_gap_pct"], row["target"])
        rows.append(
            {
                "symbol": row["symbol"],
                "as_of": row["date"],
                "next_date": row["next_date"],
                "hit": bool(row["hit"]),
                "rare_take": bool(info["rare_take"]),
                "gap_frac": info["gap_frac"],
            }
        )
    picked = [r for r in pick_daily_takes(rows) if r.get("rare_take")]
    table = pd.DataFrame(picked)
    print(f"Rare take: {TAKE_GAP_FRAC:.0%} <= open gap / target < 100%, max 1 name/day")
    print("Hit = that next session high vs setup close >= book target")
    if table.empty:
        print("no takes")
        return
    for label, lo, hi in (
        ("in-sample", None, "2025-08-18"),
        ("holdout", "2025-08-18", None),
        ("full", None, None),
    ):
        part = table
        if lo:
            part = part[part["as_of"] >= lo]
        if hi:
            part = part[part["as_of"] < hi]
        if part.empty:
            print(label, "n=0")
            continue
        n = len(part)
        hits = int(part["hit"].sum())
        weeks = (pd.Timestamp(part["as_of"].max()) - pd.Timestamp(part["as_of"].min())).days / 7
        print(
            json.dumps(
                {
                    "window": label,
                    "n": n,
                    "hits": hits,
                    "hit_pct": round(100 * hits / n, 1),
                    "false_pct": round(100 * (n - hits) / n, 1),
                    "per_week": round(n / weeks, 2) if weeks else None,
                    "first": part["as_of"].min(),
                    "last": part["next_date"].max(),
                }
            )
        )


if __name__ == "__main__":
    main()
