#!/usr/bin/env python3
"""Score the 1-day-ahead rare EOD rule (1/day, 4/week) on committed daily parquet."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import importlib.util
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.engines.target_trade import is_rare_eod_setup, pick_rare_eod_trades, rare_eod_score


def _setups_mod():
    path = Path(__file__).resolve().parent / "eval_target_setups.py"
    spec = importlib.util.spec_from_file_location("eval_target_setups", path)
    mod = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(mod)
    return mod


def conf_from_row(row: pd.Series) -> dict[str, bool]:
    return {name[2:]: bool(row[name]) for name in row.index if str(name).startswith("f_")}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--cache", type=Path, default=Path("/tmp/target_setup_rows.parquet"))
    args = parser.parse_args()
    helper = _setups_mod()
    frame = pd.read_parquet(args.cache) if args.cache.exists() else helper.collect_rows()
    rows = []
    for _, row in frame.iterrows():
        conf = conf_from_row(row)
        rsi = row.get("rsi_14")
        rows.append(
            {
                "symbol": row["symbol"],
                "as_of": row["date"],
                "rare_eod": is_rare_eod_setup(conf, rsi=None if pd.isna(rsi) else float(rsi)),
                "rare_eod_score": rare_eod_score(conf, rsi=None if pd.isna(rsi) else float(rsi)),
                "hit": bool(row["hit"]),
                "date": row["date"],
                "reasons": [],
            }
        )
    picked = pick_rare_eod_trades(rows)
    frame = frame.copy()
    frame["rare_eod"] = [r["rare_eod"] for r in picked]
    ins, oos = helper.split_oos(frame)
    print("Rare EOD = no uptrend, RSI<30, rumble or strong close; 1/day, 4/week")
    print("Hit = next high vs setup close >= book target (1 day ahead)")
    print("lookback", frame["date"].min(), "→", frame["next_date"].max())
    for label, part in ("in-sample", ins), ("holdout year", oos):
        stats = helper.pack(part["rare_eod"], part, label)
        weeks = max(1, (pd.to_datetime(part["date"]).max() - pd.to_datetime(part["date"]).min()).days / 7)
        stats["per_week"] = round(stats["n"] / weeks, 2)
        print(label, json.dumps(stats))


if __name__ == "__main__":
    main()
