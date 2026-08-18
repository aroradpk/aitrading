#!/usr/bin/env python3
"""Score the EOD target-watch rule and the next-open gap take on committed daily parquet."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import importlib.util
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.engines.target_trade import is_eod_target_watch


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
    watches = []
    for _, row in frame.iterrows():
        watches.append(is_eod_target_watch(conf_from_row(row), rsi=row.get("rsi_14")))
    frame = frame.copy()
    frame["watch"] = watches
    ins, oos = helper.split_oos(frame)
    print("EOD target watch = no uptrend and (setup_rattle or RSI<40)")
    print("Hit = next high vs setup close >= book target")
    print("lookback", frame["date"].min(), "→", frame["next_date"].max(), "rows", len(frame))
    for label, part in ("in-sample", ins), ("holdout year", oos):
        stats = helper.pack(part["watch"], part, label)
        print(label, json.dumps(stats))


if __name__ == "__main__":
    main()
