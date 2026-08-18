#!/usr/bin/env python3
"""Measure which SETUP-DAY flags predict the NEXT session printing the book % rise.

Hit = next high vs today's close >= target. Same event as a target-up day,
judged from the close before it — not flags on the move bar.
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import defaultdict
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.core.paths import ohlcv_daily_dir
from app.engines.adr import attach_adr, target_for
from app.engines.pattern_confirmations import detect_daily_confirmations
from app.engines.technical import _ema, _rsi
from app.engines.universe import load_trading_instruments
from app.ingest.yfinance_client import load_ohlcv

WARMUP = 40


def collect_rows() -> pd.DataFrame:
    rows = []
    for entry in load_trading_instruments():
        symbol = entry["symbol"]
        target = target_for(symbol)
        frame = attach_adr(load_ohlcv(ohlcv_daily_dir() / f"{symbol}.parquet"))
        vol_mean = frame["volume"].rolling(20).mean()
        high_20 = frame["high"].rolling(20).max()
        for i in range(WARMUP, len(frame) - 1):
            today = frame.iloc[: i + 1]
            nxt = frame.iloc[i + 1]
            close = float(frame["close"].iloc[i])
            nxt_up = (float(nxt["high"]) / close - 1) * 100
            nxt_close = (float(nxt["close"]) / close - 1) * 100
            nxt_gap = (float(nxt["open"]) / close - 1) * 100
            conf = detect_daily_confirmations(today, "long")
            rsi = _rsi(today["close"])
            ema20 = _ema(today["close"], 20)
            dist_high = (float(high_20.iloc[i]) / close - 1) * 100 if pd.notna(high_20.iloc[i]) else None
            vr = float(frame["volume"].iloc[i] / vol_mean.iloc[i]) if pd.notna(vol_mean.iloc[i]) and vol_mean.iloc[i] else None
            loc = None
            span = float(frame["high"].iloc[i] - frame["low"].iloc[i])
            if span > 0:
                loc = (close - float(frame["low"].iloc[i])) / span
            row = {
                "symbol": symbol,
                "date": frame.index[i].date().isoformat(),
                "next_date": frame.index[i + 1].date().isoformat(),
                "target": target,
                "hit": nxt_up >= target,
                "next_upside_pct": round(nxt_up, 3),
                "next_close_pct": round(nxt_close, 3),
                "next_gap_pct": round(nxt_gap, 3),
                "rsi_14": rsi,
                "ema20": ema20,
                "close_vs_ema20_pct": ((close / ema20 - 1) * 100) if ema20 else None,
                "dist_20d_high_pct": dist_high,
                "rvol": vr,
                "close_loc": loc,
                "adr20_pct": float(frame["adr_pct"].iloc[i]) if pd.notna(frame["adr_pct"].iloc[i]) else None,
                "range_pct": float(frame["range_pct"].iloc[i]) if pd.notna(frame["range_pct"].iloc[i]) else None,
                "late_bar": bool(conf.get("late_bar")),
            }
            for key, value in conf.items():
                row[f"f_{key}"] = bool(value)
            rows.append(row)
    return pd.DataFrame(rows)


def pack(mask: pd.Series, frame: pd.DataFrame, name: str) -> dict:
    sub = frame[mask]
    n = int(len(sub))
    hits = int(sub["hit"].sum()) if n else 0
    base = float(frame["hit"].mean()) if len(frame) else 0.0
    prec = hits / n if n else 0.0
    rec = hits / int(frame["hit"].sum()) if frame["hit"].sum() else 0.0
    return {
        "rule": name,
        "n": n,
        "hits": hits,
        "misses": n - hits,
        "precision_pct": round(100 * prec, 1) if n else None,
        "false_pct": round(100 * (1 - prec), 1) if n else None,
        "recall_pct": round(100 * rec, 1),
        "base_pct": round(100 * base, 1),
        "lift": round(prec / base, 2) if base and n else None,
    }


def flag_cols(frame: pd.DataFrame) -> list[str]:
    return [c for c in frame.columns if c.startswith("f_")]


def combo_masks(frame: pd.DataFrame) -> dict[str, pd.Series]:
    f = {c[2:]: frame[c] for c in flag_cols(frame)}
    not_late = ~frame["late_bar"]
    coil = f["tight_range"] | f["consolidation_anchor"]
    quiet = f.get("dead_volume", pd.Series(False, index=frame.index))
    pullback = f["ema20_support"] & f["close_above_ema20"]
    loc_low = frame["close_loc"].fillna(1) <= 0.45
    near_high = frame["dist_20d_high_pct"].fillna(99) <= 1.5
    rsi_ok = frame["rsi_14"].fillna(50).between(45, 68)
    range_quiet = (frame["range_pct"].fillna(99) <= (frame["adr20_pct"].fillna(0) * 0.9))
    return {
        "all_days": pd.Series(True, index=frame.index),
        "not_late": not_late,
        "tight_range": f["tight_range"] & not_late,
        "dead_volume": quiet & not_late,
        "coil": coil & not_late,
        "coil_dead": coil & quiet & not_late,
        "ema20_support": f["ema20_support"] & not_late,
        "sr_fib": f["sr_fib_confluence"] & not_late,
        "higher_lows": f["higher_lows"] & not_late,
        "live_rvol": f["live_rvol"] & not_late,
        "setup_rattle": f["setup_rattle"] & not_late,
        "range_expansion": f["range_expansion"] & not_late,
        "strong_close": f["strong_close"] & not_late,
        "rsi_60_reclaim": f["rsi_60_reclaim"] & not_late,
        "pullback_ema": pullback & not_late,
        "coil_ema": coil & f["ema20_support"] & not_late,
        "coil_ema_hl": coil & f["ema20_support"] & f["higher_lows"] & not_late,
        "coil_ema_srfib": coil & f["ema20_support"] & f["sr_fib_confluence"] & not_late,
        "coil_ema_quiet": coil & f["ema20_support"] & quiet & not_late,
        "coil_ema_rsi": coil & f["ema20_support"] & rsi_ok & not_late,
        "coil_ema_hl_rsi": coil & f["ema20_support"] & f["higher_lows"] & rsi_ok & not_late,
        "coil_not_rattle": coil & f["ema20_support"] & ~f["setup_rattle"] & not_late,
        "quiet_pullback": quiet & pullback & not_late,
        "loc_low_ema": loc_low & f["ema20_support"] & not_late,
        "near_20d_high": near_high & not_late,
        "range_lt_adr_ema": range_quiet & f["ema20_support"] & not_late,
        "breakout_base": f["ema20_support"] & f["consolidation_anchor"] & f["ema_momentum_expanding"] & not_late,
        "uptrend_coil": f.get("uptrend", pd.Series(False, index=frame.index)) & coil & not_late,
        "rsi_trend_coil": f["rsi_trend_long"] & coil & f["ema20_support"] & not_late,
        "rattle_rvol": f["setup_rattle"] & f["live_rvol"] & not_late,
        "rattle_range": f["setup_rattle"] & f["range_expansion"] & not_late,
        "rattle_not_uptrend": f["setup_rattle"] & ~f.get("uptrend", pd.Series(False, index=frame.index)) & not_late,
        "rattle_below_ema": f["setup_rattle"] & ~f["close_above_ema20"] & not_late,
        "below_ema": ~f["close_above_ema20"] & not_late,
        "not_uptrend": ~f.get("uptrend", pd.Series(False, index=frame.index)) & not_late,
        "rsi_lt_40": (frame["rsi_14"].fillna(50) < 40) & not_late,
        "rsi_lt_40_rattle": (frame["rsi_14"].fillna(50) < 40) & f["setup_rattle"] & not_late,
        "vol_rattle": f["vol_expansion"] & f["setup_rattle"] & not_late,
        "energy_any": (f["setup_rattle"] | f["live_rvol"] | f["range_expansion"]) & not_late,
        "energy_2of3": (
            f["setup_rattle"].astype(int) + f["live_rvol"].astype(int) + f["range_expansion"].astype(int) >= 2
        )
        & not_late,
    }


def split_oos(frame: pd.DataFrame, oos_start: str = "2025-08-18") -> tuple[pd.DataFrame, pd.DataFrame]:
    return frame[frame["date"] < oos_start], frame[frame["date"] >= oos_start]


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--json-out", type=Path, default=None)
    parser.add_argument("--cache", type=Path, default=Path("/tmp/target_setup_rows.parquet"))
    args = parser.parse_args()
    if args.cache.exists():
        frame = pd.read_parquet(args.cache)
    else:
        frame = collect_rows()
        args.cache.parent.mkdir(parents=True, exist_ok=True)
        frame.to_parquet(args.cache)
    ins, oos = split_oos(frame)
    report: dict = {
        "lookback": {
            "first": frame["date"].min(),
            "last": frame["next_date"].max(),
            "setup_rows": int(len(frame)),
            "hit_days": int(frame["hit"].sum()),
            "base_pct": round(100 * float(frame["hit"].mean()), 1),
            "insample": f"{ins['date'].min()} → {ins['date'].max()} n={len(ins)} base={round(100*float(ins['hit'].mean()),1)}%",
            "oos": f"{oos['date'].min()} → {oos['date'].max()} n={len(oos)} base={round(100*float(oos['hit'].mean()),1)}%",
        },
        "single_flags_insample": [],
        "combos": [],
        "by_symbol_best": [],
    }
    ins_hits = ins[ins["hit"]]
    ins_miss = ins[~ins["hit"]]
    singles = []
    for col in flag_cols(frame):
        name = col[2:]
        p_hit = float(ins_hits[col].mean()) if len(ins_hits) else 0
        p_all = float(ins[col].mean()) if len(ins) else 0
        singles.append(
            {
                "flag": name,
                "pct_before_hits": round(100 * p_hit, 1),
                "pct_all_setup_days": round(100 * p_all, 1),
                "lift_on_setup": round(p_hit / p_all, 2) if p_all else None,
            }
        )
        singles.sort(key=lambda x: (-(x["lift_on_setup"] or 0), -x["pct_before_hits"]))
    report["single_flags_insample"] = singles

    print("SETUP → NEXT session target rise")
    print(json.dumps(report["lookback"], indent=2))
    print("\nPrior-day flag rate before hits vs all setup days (in-sample):")
    for row in singles[:20]:
        print(
            f"  {row['flag']:28} before-hit {row['pct_before_hits']:5.1f}%  "
            f"all {row['pct_all_setup_days']:5.1f}%  lift {row['lift_on_setup']}"
        )

    print("\nRules (precision = next session printed the book %):")
    header = f"{'rule':28} {'n':6} {'hit%':6} {'FA%':6} {'rec%':6} {'lift':5} | OOS n  hit%  FA%  rec%  lift"
    print(header)
    combos = []
    for name, mask in combo_masks(frame).items():
        ins_m = pack(mask.loc[ins.index], ins, name)
        oos_m = pack(mask.loc[oos.index], oos, name)
        combos.append({"in_sample": ins_m, "oos": oos_m})
        print(
            f"{name:28} {ins_m['n']:6} {str(ins_m['precision_pct']):>6} {str(ins_m['false_pct']):>6} "
            f"{str(ins_m['recall_pct']):>6} {str(ins_m['lift']):>5} | "
            f"{oos_m['n']:4} {str(oos_m['precision_pct']):>5} {str(oos_m['false_pct']):>5} "
            f"{str(oos_m['recall_pct']):>5} {str(oos_m['lift']):>4}"
        )
    report["combos"] = combos

    print("\nBy symbol, coil_ema_hl_rsi and coil_ema_quiet:")
    for symbol, sub in frame.groupby("symbol"):
        ins_s, oos_s = split_oos(sub)
        for rule in ("coil_ema_hl_rsi", "coil_ema_quiet", "coil_ema", "live_rvol"):
            masks = combo_masks(sub)
            a = pack(masks[rule].loc[ins_s.index], ins_s, f"{symbol}:{rule}:ins")
            b = pack(masks[rule].loc[oos_s.index], oos_s, f"{symbol}:{rule}:oos")
            print(
                f"  {a['rule']:40} n={a['n']:4} hit={a['precision_pct']}% rec={a['recall_pct']}% lift={a['lift']}  "
                f"OOS n={b['n']:3} hit={b['precision_pct']}% rec={b['recall_pct']}% lift={b['lift']}"
            )

    print("\nOpen-drive: once tomorrow's gap is known, does the day finish the target?")
    oos_all = oos
    for frac in (0.25, 0.4, 0.5, 0.75, 1.0):
        gap_ok = oos_all["next_gap_pct"] >= (oos_all["target"] * frac)
        packed = pack(gap_ok, oos_all, f"oos_gap>={frac:.2f}*target")
        print(
            f"  gap>={frac:.2f}×target  n={packed['n']} hit={packed['precision_pct']}% "
            f"FA={packed['false_pct']}% rec={packed['recall_pct']}% lift={packed['lift']}"
        )
    ins_gap = pack(ins["next_gap_pct"] >= ins["target"] * 0.5, ins, "ins_gap>=0.5t")
    print("  in-sample gap>=0.5×target", ins_gap)
    print("\nBy symbol energy rules:")
    for symbol, sub in frame.groupby("symbol"):
        ins_s, oos_s = split_oos(sub)
        for rule in ("setup_rattle", "energy_2of3", "rattle_rvol", "rattle_below_ema"):
            masks = combo_masks(sub)
            a = pack(masks[rule].loc[ins_s.index], ins_s, f"{symbol}:{rule}:ins")
            b = pack(masks[rule].loc[oos_s.index], oos_s, f"{symbol}:{rule}:oos")
            print(
                f"  {a['rule']:42} n={a['n']:4} hit={a['precision_pct']}% rec={a['recall_pct']}% lift={a['lift']}  "
                f"OOS n={b['n']:3} hit={b['precision_pct']}% rec={b['recall_pct']}% lift={b['lift']}"
            )
    if args.json_out:
        args.json_out.parent.mkdir(parents=True, exist_ok=True)
        args.json_out.write_text(json.dumps(report, indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()
