#!/usr/bin/env python3
"""Hit-and-trial: find a day-before rule with FPR<=5% and recall>=80% on |next|>=5% days."""

from __future__ import annotations

import json
import itertools
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.core.paths import ohlcv_daily_dir, universe_dir
from app.engines.pattern_confirmations import detect_daily_confirmations, detect_ema20_support
from app.engines.pattern_scoring import matched_families
from app.engines.technical import _ema, _rsi
from app.ingest.yfinance_client import load_ohlcv

SEED = 42
QUIET = 80
OUT = Path("/opt/cursor/artifacts/fpr_recall_search.json")


def symbols() -> list[str]:
    payload = json.loads((universe_dir() / "active.json").read_text(encoding="utf-8"))
    return [s["symbol"] for s in payload["stocks"]]


def numerics(frame: pd.DataFrame) -> dict[str, float]:
    close = float(frame["close"].iloc[-1])
    high = float(frame["high"].iloc[-1])
    low = float(frame["low"].iloc[-1])
    span = high - low
    atr = float((frame["high"] - frame["low"]).tail(20).mean())
    vol = frame["volume"]
    vol_mean = float(vol.tail(20).mean()) or 1.0
    vr = float(vol.iloc[-1] / vol_mean)
    vol5 = float(vol.tail(5).mean() / vol_mean)
    coil4 = float(frame["high"].tail(4).max() - frame["low"].tail(4).min())
    coil5 = float(frame["high"].tail(5).max() - frame["low"].tail(5).min())
    ema20 = _ema(frame["close"], 20)
    ema50 = _ema(frame["close"], 50)
    rsi = _rsi(frame["close"]) or 50.0
    loc = (close - low) / span if span > 0 else 0.5
    hi20 = float(frame["high"].tail(20).max())
    lo20 = float(frame["low"].tail(20).min())
    inside = 0
    for i in range(1, min(6, len(frame))):
        prev, cur = frame.iloc[-i - 1], frame.iloc[-i]
        if cur["high"] <= prev["high"] and cur["low"] >= prev["low"]:
            inside += 1
        else:
            break
    shrinking = 0
    for i in range(1, min(5, len(frame))):
        a = float(frame["high"].iloc[-i] - frame["low"].iloc[-i])
        b = float(frame["high"].iloc[-i - 1] - frame["low"].iloc[-i - 1])
        if b > 0 and a < b:
            shrinking += 1
        else:
            break
    vol_dry = 0
    for i in range(1, min(5, len(frame))):
        if float(vol.iloc[-i]) < float(vol.iloc[-i - 1]):
            vol_dry += 1
        else:
            break
    return {
        "vr": vr,
        "vol5": vol5,
        "range_atr": (span / atr) if atr else 0.0,
        "coil4_atr": (coil4 / atr) if atr else 99.0,
        "coil5_atr": (coil5 / atr) if atr else 99.0,
        "ema_dist": abs(close - ema20) / ema20 if ema20 else 9.0,
        "ema_stack": 1.0 if (ema20 and ema50 and ema20 > ema50) else 0.0,
        "rsi": rsi,
        "loc": loc,
        "near_high": close / hi20 if hi20 else 0.0,
        "near_low": close / lo20 if lo20 else 9.0,
        "inside": float(inside),
        "shrinking": float(shrinking),
        "vol_dry": float(vol_dry),
        "ema20_support": 1.0 if detect_ema20_support(frame) else 0.0,
    }


def collect() -> pd.DataFrame:
    rng = np.random.default_rng(SEED)
    rows: list[dict] = []
    for symbol in symbols():
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
        sample = list(rng.choice(quiet_idx, size=min(QUIET, len(quiet_idx)), replace=False))
        for i in big_idx + sample:
            nxt = float(pct.iloc[i + 1])
            sl = frame.iloc[: i + 1]
            side = "long" if nxt > 0 else "short"
            conf = detect_daily_confirmations(sl, side)
            fam = matched_families(conf, side=side)
            row = {
                "sym": symbol,
                "big": abs(nxt) >= 5,
                "side": side,
                "n_fam": len(fam),
                "n_act": int(sum(1 for v in conf.values() if v)),
            }
            row.update({k: bool(v) for k, v in conf.items()})
            row.update(numerics(sl))
            rows.append(row)
        print(f"done {symbol} big={len(big_idx)} quiet={len(sample)}", flush=True)
    return pd.DataFrame(rows)


def eval_mask(name: str, big: pd.DataFrame, quiet: pd.DataFrame, bmask, qmask) -> dict:
    rec = float(np.mean(bmask)) if len(big) else 0.0
    fpr = float(np.mean(qmask)) if len(quiet) else 0.0
    return {
        "name": name,
        "recall": round(100 * rec, 1),
        "fpr": round(100 * fpr, 1),
        "tp": int(np.sum(bmask)),
        "fp": int(np.sum(qmask)),
        "target": rec >= 0.80 and fpr <= 0.05,
        "score": rec - 8 * max(0.0, fpr - 0.05) - 4 * max(0.0, 0.80 - rec),
    }


def search(df: pd.DataFrame) -> list[dict]:
    big = df[df["big"]].reset_index(drop=True)
    quiet = df[~df["big"]].reset_index(drop=True)
    results: list[dict] = []

    def add(name, bmask, qmask):
        results.append(eval_mask(name, big, quiet, np.asarray(bmask), np.asarray(qmask)))

    bool_cols = [
        c
        for c in df.columns
        if c not in {"sym", "big", "side"} and df[c].dtype == bool
    ]
    print("\n=== lift (bool) ===")
    lifts = []
    for col in bool_cols + ["ema20_support"]:
        if col not in big.columns:
            continue
        rb = float(big[col].mean())
        rq = float(quiet[col].mean())
        lift = rb / rq if rq else 99.0
        lifts.append((lift, rb, rq, col))
        print(f"  {col:28} big={100*rb:5.1f}% quiet={100*rq:5.1f}% lift={lift:.2f}")
    lifts.sort(reverse=True)

    print("\n=== numeric means ===")
    for col in ["vr", "vol5", "range_atr", "coil4_atr", "coil5_atr", "ema_dist", "rsi", "loc", "near_high", "inside", "shrinking", "vol_dry", "n_fam", "n_act"]:
        print(f"  {col:14} big={big[col].mean():7.3f} quiet={quiet[col].mean():7.3f}")

    # threshold grids
    for vr_min in (1.2, 1.4, 1.6, 1.8, 2.0, 2.5, 3.0):
        add(f"vr>={vr_min}", big["vr"] >= vr_min, quiet["vr"] >= vr_min)
    for ra in (1.0, 1.2, 1.4, 1.6, 1.8, 2.0):
        add(f"range_atr>={ra}", big["range_atr"] >= ra, quiet["range_atr"] >= ra)
    for c4 in (1.5, 2.0, 2.5, 3.0, 3.5):
        add(f"coil4<={c4}", big["coil4_atr"] <= c4, quiet["coil4_atr"] <= c4)
    for d in (0.01, 0.015, 0.02, 0.03, 0.05):
        add(f"ema_dist<={d}", big["ema_dist"] <= d, quiet["ema_dist"] <= d)
    for loc_min in (0.6, 0.7, 0.8, 0.9):
        add(f"close_loc>={loc_min}", big["loc"] >= loc_min, quiet["loc"] >= loc_min)
    for nh in (0.96, 0.97, 0.98, 0.99):
        add(f"near_high>={nh}", big["near_high"] >= nh, quiet["near_high"] >= nh)
    for nf in (1, 2, 3, 4):
        add(f"n_fam>={nf}", big["n_fam"] >= nf, quiet["n_fam"] >= nf)

    # AND combos of best-looking pieces
    combos = [
        ("fam1+vr2", (big["n_fam"] >= 1) & (big["vr"] >= 2.0), (quiet["n_fam"] >= 1) & (quiet["vr"] >= 2.0)),
        ("fam1+vr2+ra1.6", (big["n_fam"] >= 1) & (big["vr"] >= 2.0) & (big["range_atr"] >= 1.6), (quiet["n_fam"] >= 1) & (quiet["vr"] >= 2.0) & (quiet["range_atr"] >= 1.6)),
        ("coil+ema+fib", big["tight_range"] & big["ema20_support"] & big["sr_fib_confluence"], quiet["tight_range"] & quiet["ema20_support"] & quiet["sr_fib_confluence"]),
        ("coil|anchor + ema + fib", (big["tight_range"] | big["consolidation_anchor"]) & big["ema20_support"] & big["sr_fib_confluence"], (quiet["tight_range"] | quiet["consolidation_anchor"]) & quiet["ema20_support"] & quiet["sr_fib_confluence"]),
        ("dead+coil+ema+fib", (big["dead_volume"] & (big["tight_range"] | big["consolidation_anchor"]) & big["ema20_support"] & big["sr_fib_confluence"]), (quiet["dead_volume"] & (quiet["tight_range"] | quiet["consolidation_anchor"]) & quiet["ema20_support"] & quiet["sr_fib_confluence"])),
        ("exp+ema+fib", big["vol_expansion"] & big["range_expansion"] & big["ema20_support"] & big["sr_fib_confluence"], quiet["vol_expansion"] & quiet["range_expansion"] & quiet["ema20_support"] & quiet["sr_fib_confluence"]),
        ("vr2+loc0.7", (big["vr"] >= 2) & (big["loc"] >= 0.7), (quiet["vr"] >= 2) & (quiet["loc"] >= 0.7)),
        ("vr1.6+ra1.4+loc0.7", (big["vr"] >= 1.6) & (big["range_atr"] >= 1.4) & (big["loc"] >= 0.7), (quiet["vr"] >= 1.6) & (quiet["range_atr"] >= 1.4) & (quiet["loc"] >= 0.7)),
        ("vr1.8+ra1.5", (big["vr"] >= 1.8) & (big["range_atr"] >= 1.5), (quiet["vr"] >= 1.8) & (quiet["range_atr"] >= 1.5)),
        ("inside>=2+ema", (big["inside"] >= 2) & (big["ema_dist"] <= 0.02), (quiet["inside"] >= 2) & (quiet["ema_dist"] <= 0.02)),
        ("vol_dry>=2+coil4<=2.5+ema", (big["vol_dry"] >= 2) & (big["coil4_atr"] <= 2.5) & (big["ema_dist"] <= 0.02), (quiet["vol_dry"] >= 2) & (quiet["coil4_atr"] <= 2.5) & (quiet["ema_dist"] <= 0.02)),
        ("shrinking>=2+dead+ema+fib", (big["shrinking"] >= 2) & big["dead_volume"] & big["ema20_support"] & big["sr_fib_confluence"], (quiet["shrinking"] >= 2) & quiet["dead_volume"] & quiet["ema20_support"] & quiet["sr_fib_confluence"]),
        ("near_high+vr1.5", (big["near_high"] >= 0.98) & (big["vr"] >= 1.5), (quiet["near_high"] >= 0.98) & (quiet["vr"] >= 1.5)),
        ("ema_exp+fib+coil+dead", big["ema_momentum_expanding"] & big["sr_fib_confluence"] & (big["tight_range"] | big["consolidation_anchor"]) & big["dead_volume"], quiet["ema_momentum_expanding"] & quiet["sr_fib_confluence"] & (quiet["tight_range"] | quiet["consolidation_anchor"]) & quiet["dead_volume"]),
        ("ema_exp+fib+vr2+ra1.6", big["ema_momentum_expanding"] & big["sr_fib_confluence"] & (big["vr"] >= 2) & (big["range_atr"] >= 1.6), quiet["ema_momentum_expanding"] & quiet["sr_fib_confluence"] & (quiet["vr"] >= 2) & (quiet["range_atr"] >= 1.6)),
    ]
    for name, b, q in combos:
        add(name, b, q)

    # brute AND of 2 high-lift bools
    top = [c for _, rb, rq, c in lifts if rb >= 0.15 and c in big.columns][:18]
    for a, b in itertools.combinations(top, 2):
        add(f"{a}&{b}", big[a] & big[b], quiet[a] & quiet[b])
    for a, b, c in itertools.combinations(top[:12], 3):
        add(f"{a}&{b}&{c}", big[a] & big[b] & big[c], quiet[a] & quiet[b] & quiet[c])

    # numeric 2D grids for the only features with historical lift
    for vr_min in (1.3, 1.5, 1.7, 1.9, 2.2, 2.6):
        for ra in (1.1, 1.3, 1.5, 1.7, 2.0):
            add(
                f"vr>={vr_min}&ra>={ra}",
                (big["vr"] >= vr_min) & (big["range_atr"] >= ra),
                (quiet["vr"] >= vr_min) & (quiet["range_atr"] >= ra),
            )
            add(
                f"fam1+vr>={vr_min}&ra>={ra}",
                (big["n_fam"] >= 1) & (big["vr"] >= vr_min) & (big["range_atr"] >= ra),
                (quiet["n_fam"] >= 1) & (quiet["vr"] >= vr_min) & (quiet["range_atr"] >= ra),
            )

    results.sort(key=lambda r: (not r["target"], -r["score"], r["fpr"], -r["recall"]))
    return results


def main() -> None:
    df = collect()
    results = search(df)
    Path("/opt/cursor/artifacts/fpr_recall_rows.parquet")
    df.to_pickle("/tmp/fpr_rows.pkl")
    hits = [r for r in results if r["target"]]
    fpr_ok = [r for r in results if r["fpr"] <= 5.0]
    rec_ok = [r for r in results if r["recall"] >= 80.0]
    print("\n=== TARGET hits ===", len(hits))
    for r in hits[:20]:
        print(r)
    print("\n=== best FPR<=5% by recall ===")
    for r in sorted(fpr_ok, key=lambda x: -x["recall"])[:15]:
        print(r)
    print("\n=== best recall>=80% by FPR ===")
    for r in sorted(rec_ok, key=lambda x: x["fpr"])[:15]:
        print(r)
    print("\n=== top score overall ===")
    for r in results[:20]:
        print(r)
    OUT.write_text(
        json.dumps(
            {
                "n_big": int(df["big"].sum()),
                "n_quiet": int((~df["big"]).sum()),
                "target_hits": hits[:20],
                "best_fpr_le_5": sorted(fpr_ok, key=lambda x: -x["recall"])[:20],
                "best_recall_ge_80": sorted(rec_ok, key=lambda x: x["fpr"])[:20],
                "top": results[:40],
            },
            indent=2,
        )
    )
    print("wrote", OUT)


if __name__ == "__main__":
    main()
