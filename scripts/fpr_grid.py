#!/usr/bin/env python3
"""Compare pattern rates on 5% next-day vs random quiet days; grid FPR/recall."""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.core.paths import ohlcv_daily_dir
from app.engines.pattern_confirmations import detect_daily_confirmations
from app.engines.pattern_scoring import matched_families
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


def extras(frame: pd.DataFrame) -> dict[str, bool]:
    if len(frame) < 25:
        return {
            "strong_close": False,
            "vol_spike": False,
            "range_expand": False,
            "near_20d_high": False,
            "near_20d_low": False,
        }
    close = float(frame["close"].iloc[-1])
    day_low = float(frame["low"].iloc[-1])
    day_high = float(frame["high"].iloc[-1])
    span = day_high - day_low
    loc = (close - day_low) / span if span > 0 else 0.5
    vol = frame["volume"]
    vol_mean = float(vol.tail(20).mean())
    vr = float(vol.iloc[-1] / vol_mean) if vol_mean else 1.0
    atr = float((frame["high"] - frame["low"]).tail(20).mean())
    return {
        "strong_close": loc >= 0.7,
        "vol_spike": vr >= 1.4,
        "range_expand": atr > 0 and span >= 1.2 * atr,
        "near_20d_high": close >= float(frame["high"].tail(20).max()) * 0.98,
        "near_20d_low": close <= float(frame["low"].tail(20).min()) * 1.02,
    }


def collect(quiet_per_symbol: int = 60, seed: int = 42) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    rows: list[dict] = []
    for symbol in SYMBOLS:
        frame = load_ohlcv(ohlcv_daily_dir() / f"{symbol}.parquet")
        pct = frame["close"].pct_change() * 100
        big_idx: list[int] = []
        quiet_idx: list[int] = []
        for i in range(40, len(frame) - 1):
            nxt = pct.iloc[i + 1]
            if pd.isna(nxt):
                continue
            if abs(nxt) >= 5:
                big_idx.append(i)
            else:
                quiet_idx.append(i)
        sample_q = list(rng.choice(quiet_idx, size=min(quiet_per_symbol, len(quiet_idx)), replace=False))
        for i in big_idx + sample_q:
            nxt = float(pct.iloc[i + 1])
            sl = frame.iloc[: i + 1]
            big = abs(nxt) >= 5
            side = "long" if nxt > 0 else "short"
            conf = detect_daily_confirmations(sl, side)
            fam = matched_families(conf, side=side)
            row = {
                "sym": symbol,
                "big": big,
                "side": side,
                "n_fam": len(fam),
                "n_act": sum(1 for value in conf.values() if value),
            }
            row.update({key: bool(value) for key, value in conf.items()})
            row.update(extras(sl))
            rows.append(row)
        print(f"done {symbol} big={len(big_idx)} quiet={len(sample_q)}", flush=True)
    return pd.DataFrame(rows)


def report(df: pd.DataFrame) -> None:
    big = df[df["big"]]
    quiet = df[~df["big"]]
    print(f"\nN big={len(big)} quiet_sample={len(quiet)}")
    feat_cols = [
        c
        for c in df.columns
        if c not in {"sym", "big", "side", "n_fam", "n_act"} and df[c].dtype != object
    ]
    print("\nlift")
    for col in feat_cols:
        rb = float(big[col].mean()) if col in big else 0
        rq = float(quiet[col].mean()) if col in quiet else 0
        lift = rb / rq if rq else 99.0
        print(f"  {col:28} big={100*rb:5.1f}% quiet={100*rq:5.1f}% lift={lift:.2f}")

    def eval_rule(name: str, bmask: pd.Series, qmask: pd.Series) -> None:
        rec = float(bmask.mean())
        fpr = float(qmask.mean())
        flag = ""
        if rec >= 0.80 and fpr <= 0.05:
            flag = "  TARGET"
        elif rec >= 0.80:
            flag = "  recall_ok"
        print(f"  {name:32} recall={100*rec:5.1f}%  FPR={100*fpr:5.1f}%{flag}")

    print("\nRULES")
    eval_rule("fam>=1", big["n_fam"] >= 1, quiet["n_fam"] >= 1)
    eval_rule("fam>=2", big["n_fam"] >= 2, quiet["n_fam"] >= 2)
    eval_rule("fam>=3", big["n_fam"] >= 3, quiet["n_fam"] >= 3)
    eval_rule("act>=5", big["n_act"] >= 5, quiet["n_act"] >= 5)
    eval_rule("act>=6", big["n_act"] >= 6, quiet["n_act"] >= 6)
    eval_rule("fam>=2 & act>=5", (big["n_fam"] >= 2) & (big["n_act"] >= 5), (quiet["n_fam"] >= 2) & (quiet["n_act"] >= 5))
    eval_rule("vol_spike", big["vol_spike"], quiet["vol_spike"])
    eval_rule("strong_close", big["strong_close"], quiet["strong_close"])
    eval_rule("range_expand", big["range_expand"], quiet["range_expand"])
    eval_rule(
        "fam>=2 & vol",
        (big["n_fam"] >= 2) & big["vol_spike"],
        (quiet["n_fam"] >= 2) & quiet["vol_spike"],
    )
    eval_rule(
        "fam>=2 & strong_close",
        (big["n_fam"] >= 2) & big["strong_close"],
        (quiet["n_fam"] >= 2) & quiet["strong_close"],
    )
    eval_rule(
        "fam>=2 & range",
        (big["n_fam"] >= 2) & big["range_expand"],
        (quiet["n_fam"] >= 2) & quiet["range_expand"],
    )
    eval_rule(
        "fam>=3 & vol",
        (big["n_fam"] >= 3) & big["vol_spike"],
        (quiet["n_fam"] >= 3) & quiet["vol_spike"],
    )
    eval_rule(
        "fam>=2 & vol & close",
        (big["n_fam"] >= 2) & big["vol_spike"] & big["strong_close"],
        (quiet["n_fam"] >= 2) & quiet["vol_spike"] & quiet["strong_close"],
    )
    eval_rule(
        "vol | range | near_high",
        big["vol_spike"] | big["range_expand"] | big["near_20d_high"],
        quiet["vol_spike"] | quiet["range_expand"] | quiet["near_20d_high"],
    )
    eval_rule(
        "fam>=1 & vol & range",
        (big["n_fam"] >= 1) & big["vol_spike"] & big["range_expand"],
        (quiet["n_fam"] >= 1) & quiet["vol_spike"] & quiet["range_expand"],
    )
    prec_b = big["vol_spike"].astype(int) + big["range_expand"].astype(int)
    prec_q = quiet["vol_spike"].astype(int) + quiet["range_expand"].astype(int)
    eval_rule("fam>=1 & prec>=2 (vol/range)", (big["n_fam"] >= 1) & (prec_b >= 2), (quiet["n_fam"] >= 1) & (prec_q >= 2))
    eval_rule("fam>=1 & prec>=1", (big["n_fam"] >= 1) & (prec_b >= 1), (quiet["n_fam"] >= 1) & (prec_q >= 1))
    eval_rule("vol & range", big["vol_spike"] & big["range_expand"], quiet["vol_spike"] & quiet["range_expand"])
    eval_rule("vol & range & close", big["vol_spike"] & big["range_expand"] & big["strong_close"], quiet["vol_spike"] & quiet["range_expand"] & quiet["strong_close"])


def main() -> None:
    df = collect()
    report(df)


if __name__ == "__main__":
    main()
