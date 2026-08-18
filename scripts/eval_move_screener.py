#!/usr/bin/env python3
"""Score the 1-day-ahead movement screener on committed daily parquet.

Hit is close-to-close, not gaps and not high vs prior close:
  movement_05 = |next close / today close - 1| >= 0.5%
  trend_05    = movement_05 and next close in the top or bottom 30% of that day's range

Setup = today's range >= 2.5% of prior close and close not ±5%, then 1 name/day and 4/week.
Direction is not scored — the trader picks side the next morning.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import importlib.util
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.core.paths import ohlcv_daily_dir
from app.engines.target_trade import is_move_setup, move_setup_score, next_day_outcome, pick_move_setups
from app.ingest.yfinance_client import load_ohlcv


def _setups_mod():
    path = Path(__file__).resolve().parent / "eval_target_setups.py"
    spec = importlib.util.spec_from_file_location("eval_target_setups", path)
    mod = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(mod)
    return mod


def conf_from_row(row: pd.Series) -> dict[str, bool]:
    return {name[2:]: bool(row[name]) for name in row.index if str(name).startswith("f_")}


def attach_outcomes(frame: pd.DataFrame) -> pd.DataFrame:
    loaded: dict[str, pd.DataFrame] = {}
    index_maps: dict[str, dict[str, int]] = {}
    records = []
    for _, row in frame.iterrows():
        symbol = str(row["symbol"])
        if symbol not in loaded:
            ohlc = load_ohlcv(ohlcv_daily_dir() / f"{symbol}.parquet")
            loaded[symbol] = ohlc
            index_maps[symbol] = {
                pd.Timestamp(stamp).normalize().date().isoformat(): i for i, stamp in enumerate(ohlc.index)
            }
        ohlc = loaded[symbol]
        idx = index_maps[symbol].get(str(row["date"])[:10])
        if idx is None or idx + 1 >= len(ohlc):
            records.append(
                {
                    "movement_05": False,
                    "trend_05": False,
                    "trend_10": False,
                    "one_way": False,
                    "abs_close_pct": None,
                }
            )
            continue
        records.append(next_day_outcome(float(ohlc["close"].iloc[idx]), ohlc.iloc[idx + 1]))
    extra = pd.DataFrame(records)
    return pd.concat([frame.reset_index(drop=True), extra.reset_index(drop=True)], axis=1)


def pack_rate(mask: pd.Series, frame: pd.DataFrame, col: str, label: str) -> dict:
    sub = frame[mask]
    n = int(len(sub))
    hits = int(sub[col].fillna(False).astype(bool).sum()) if n else 0
    base = float(frame[col].fillna(False).astype(bool).mean()) if len(frame) else 0.0
    prec = hits / n if n else 0.0
    return {
        "rule": label,
        "metric": col,
        "n": n,
        "hits": hits,
        "misses": n - hits,
        "hit_pct": round(100 * prec, 1) if n else None,
        "false_pct": round(100 * (1 - prec), 1) if n else None,
        "base_pct": round(100 * base, 1),
        "lift": round(prec / base, 2) if base and n else None,
    }


def apply_picker(frame: pd.DataFrame) -> pd.Series:
    rows = []
    for _, row in frame.iterrows():
        conf = conf_from_row(row)
        rows.append(
            {
                "symbol": row["symbol"],
                "as_of": row["date"],
                "move_watch": is_move_setup(conf),
                "move_score": move_setup_score(conf, range_pct=row.get("range_pct")),
                "reasons": [],
            }
        )
    picked = pick_move_setups(rows)
    return pd.Series([bool(r["move_watch"]) for r in picked], index=frame.index)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--cache", type=Path, default=Path("/tmp/target_setup_rows.parquet"))
    parser.add_argument("--json-out", type=Path, default=None)
    args = parser.parse_args()
    helper = _setups_mod()
    frame = pd.read_parquet(args.cache) if args.cache.exists() else helper.collect_rows()
    if not args.cache.exists():
        args.cache.parent.mkdir(parents=True, exist_ok=True)
        frame.to_parquet(args.cache)
    frame = attach_outcomes(frame)
    frame["move_watch"] = apply_picker(frame)
    ins, oos = helper.split_oos(frame)
    print("Movement screener: rumble, not late; 1 name/day, 4/week")
    print("Hit = |next close vs today close| >= 0.5%. Gaps ignored. Direction not predicted.")
    print("lookback", frame["date"].min(), "→", frame["next_date"].max(), "rows", len(frame))
    report = {"lookback": [str(frame["date"].min()), str(frame["next_date"].max())], "splits": []}
    for label, part in ("in-sample", ins), ("holdout year", oos):
        weeks = max(1.0, (pd.to_datetime(part["date"]).max() - pd.to_datetime(part["date"]).min()).days / 7)
        block = {
            "label": label,
            "every_day_movement_05": pack_rate(pd.Series(True, index=part.index), part, "movement_05", "base"),
            "every_day_trend_05": pack_rate(pd.Series(True, index=part.index), part, "trend_05", "base"),
            "screener_movement_05": pack_rate(part["move_watch"], part, "movement_05", "screener"),
            "screener_trend_05": pack_rate(part["move_watch"], part, "trend_05", "screener"),
            "screener_trend_10": pack_rate(part["move_watch"], part, "trend_10", "screener"),
        }
        n = block["screener_movement_05"]["n"]
        block["per_week"] = round(n / weeks, 2)
        report["splits"].append(block)
        print(label, json.dumps(block))
    if args.json_out:
        args.json_out.parent.mkdir(parents=True, exist_ok=True)
        args.json_out.write_text(json.dumps(report, indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()
