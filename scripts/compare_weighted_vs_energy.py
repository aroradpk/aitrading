#!/usr/bin/env python3
"""Compare energy-gate (previous) vs weighted-layer (current) scores on 5% days and quiet days."""

from __future__ import annotations

import json
import sys
from collections import Counter
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.core.paths import ohlcv_daily_dir, universe_dir
from app.engines.conviction import conviction_from_scores
from app.engines.events import score_events
from app.engines.fundamental import score_fundamentals
from app.engines.pattern_confirmations import detect_daily_confirmations
from app.engines.pattern_scoring import has_precision_energy, matched_families, score_technical_confirmations
from app.engines.technical import build_snapshot
from app.engines.themes import score_themes
from app.ingest.yfinance_client import load_ohlcv

QUIET_SAMPLE = 80
SEED = 42
ARTIFACT = Path("/opt/cursor/artifacts/weighted_vs_energy_compare.json")


def load_symbols() -> list[str]:
    payload = json.loads((universe_dir() / "active.json").read_text(encoding="utf-8"))
    return [s["symbol"] for s in payload.get("stocks", [])]


def old_technical(confirmations: dict[str, bool], *, side: str) -> float:
    """Previous main rule: family + vol/range energy => 7, else 4/2.5/1."""
    families = matched_families(confirmations, side=side)
    energy = has_precision_energy(confirmations)
    active_count = sum(1 for value in confirmations.values() if value)
    if families and energy:
        return 7.0
    if families or active_count >= 2:
        return 4.0
    if active_count == 1:
        return 2.5
    return 1.0


def new_technical(frame: pd.DataFrame, confirmations: dict[str, bool], *, side: str, snapshot: dict) -> dict:
    scored = score_technical_confirmations(confirmations, side=side, snapshot=snapshot)
    return scored


def evaluate_symbol(symbol: str, rng: np.random.Generator) -> dict:
    frame = load_ohlcv(ohlcv_daily_dir() / f"{symbol}.parquet")
    pct = frame["close"].pct_change() * 100
    fund, _ = score_fundamentals(symbol)
    theme, _, _ = score_themes(symbol)

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

    sample = list(rng.choice(quiet_idx, size=min(QUIET_SAMPLE, len(quiet_idx)), replace=False)) if quiet_idx else []

    events_5: list[dict] = []
    old_tp = new_tp = 0
    for i in big_idx:
        nxt = float(pct.iloc[i + 1])
        side = "long" if nxt > 0 else "short"
        sl = frame.iloc[: i + 1]
        conf = detect_daily_confirmations(sl, side)
        snap = build_snapshot(sl, focus=side)
        old = old_technical(conf, side=side)
        scored = new_technical(sl, conf, side=side, snapshot=snap)
        new = float(scored["technical_score"])
        signal_date = sl.index[-1].date()
        events, _ = score_events(symbol, as_of=signal_date)
        conv_old = conviction_from_scores(old, fund, events, theme)
        conv_new = conviction_from_scores(new, fund, events, theme)
        if old >= 7:
            old_tp += 1
        if new >= 7:
            new_tp += 1
        events_5.append(
            {
                "symbol": symbol,
                "signal_date": signal_date.isoformat(),
                "move_date": frame.index[i + 1].date().isoformat(),
                "move_pct": round(nxt, 2),
                "side": side,
                "old_tech": old,
                "new_tech": new,
                "old_conv": conv_old["final"],
                "new_conv": conv_new["final"],
                "layers": scored.get("score_layers", {}),
                "families": scored.get("pattern_families", []),
                "delta_tech": round(new - old, 1),
            }
        )

    old_fp = new_fp = 0
    for i in sample:
        sl = frame.iloc[: i + 1]
        snap = build_snapshot(sl, focus="long")
        old_fire = new_fire = False
        for side in ("long", "short"):
            conf = detect_daily_confirmations(sl, side)
            if old_technical(conf, side=side) >= 7:
                old_fire = True
            scored = new_technical(sl, conf, side=side, snapshot=snap)
            if float(scored["technical_score"]) >= 7:
                new_fire = True
        if old_fire:
            old_fp += 1
        if new_fire:
            new_fp += 1

    n_big = len(big_idx)
    n_quiet = len(sample)
    return {
        "symbol": symbol,
        "true_5pct_days": n_big,
        "quiet_sampled": n_quiet,
        "old_hits_ge7": old_tp,
        "new_hits_ge7": new_tp,
        "old_recall_pct": round(100 * old_tp / n_big, 1) if n_big else 0.0,
        "new_recall_pct": round(100 * new_tp / n_big, 1) if n_big else 0.0,
        "old_false_signals": old_fp,
        "new_false_signals": new_fp,
        "old_fpr_pct": round(100 * old_fp / n_quiet, 1) if n_quiet else 0.0,
        "new_fpr_pct": round(100 * new_fp / n_quiet, 1) if n_quiet else 0.0,
        "old_avg_tech_5pct": round(sum(r["old_tech"] for r in events_5) / n_big, 2) if n_big else 0.0,
        "new_avg_tech_5pct": round(sum(r["new_tech"] for r in events_5) / n_big, 2) if n_big else 0.0,
        "old_avg_conv_5pct": round(sum(r["old_conv"] for r in events_5) / n_big, 2) if n_big else 0.0,
        "new_avg_conv_5pct": round(sum(r["new_conv"] for r in events_5) / n_big, 2) if n_big else 0.0,
        "old_conv_ge7": sum(1 for r in events_5 if r["old_conv"] >= 7),
        "new_conv_ge7": sum(1 for r in events_5 if r["new_conv"] >= 7),
        "improved": sum(1 for r in events_5 if r["new_tech"] > r["old_tech"]),
        "degraded": sum(1 for r in events_5 if r["new_tech"] < r["old_tech"]),
        "unchanged": sum(1 for r in events_5 if r["new_tech"] == r["old_tech"]),
        "events": events_5,
    }


def main() -> None:
    rng = np.random.default_rng(SEED)
    symbols = load_symbols()
    rows: list[dict] = []
    for symbol in symbols:
        print(f"evaluating {symbol}...", flush=True)
        rows.append(evaluate_symbol(symbol, rng))
        r = rows[-1]
        print(
            f"  5%={r['true_5pct_days']:3} old_hit={r['old_hits_ge7']:3} ({r['old_recall_pct']:5.1f}%) "
            f"new_hit={r['new_hits_ge7']:3} ({r['new_recall_pct']:5.1f}%) "
            f"FPR old={r['old_fpr_pct']:4.1f}% new={r['new_fpr_pct']:4.1f}% "
            f"avgT {r['old_avg_tech_5pct']:.2f}->{r['new_avg_tech_5pct']:.2f}",
            flush=True,
        )

    n_big = sum(r["true_5pct_days"] for r in rows)
    n_quiet = sum(r["quiet_sampled"] for r in rows)
    old_tp = sum(r["old_hits_ge7"] for r in rows)
    new_tp = sum(r["new_hits_ge7"] for r in rows)
    old_fp = sum(r["old_false_signals"] for r in rows)
    new_fp = sum(r["new_false_signals"] for r in rows)
    all_events = [e for r in rows for e in r["events"]]
    delta_counts = Counter("up" if e["delta_tech"] > 0 else "down" if e["delta_tech"] < 0 else "same" for e in all_events)

    overall = {
        "true_5pct_days": n_big,
        "quiet_sampled": n_quiet,
        "old_hits_ge7": old_tp,
        "new_hits_ge7": new_tp,
        "old_recall_pct": round(100 * old_tp / n_big, 1) if n_big else 0.0,
        "new_recall_pct": round(100 * new_tp / n_big, 1) if n_big else 0.0,
        "old_false_signals": old_fp,
        "new_false_signals": new_fp,
        "old_fpr_pct": round(100 * old_fp / n_quiet, 1) if n_quiet else 0.0,
        "new_fpr_pct": round(100 * new_fp / n_quiet, 1) if n_quiet else 0.0,
        "old_avg_tech_5pct": round(sum(e["old_tech"] for e in all_events) / n_big, 2) if n_big else 0.0,
        "new_avg_tech_5pct": round(sum(e["new_tech"] for e in all_events) / n_big, 2) if n_big else 0.0,
        "old_avg_conv_5pct": round(sum(e["old_conv"] for e in all_events) / n_big, 2) if n_big else 0.0,
        "new_avg_conv_5pct": round(sum(e["new_conv"] for e in all_events) / n_big, 2) if n_big else 0.0,
        "old_conv_ge7": sum(1 for e in all_events if e["old_conv"] >= 7),
        "new_conv_ge7": sum(1 for e in all_events if e["new_conv"] >= 7),
        "tech_up": delta_counts["up"],
        "tech_down": delta_counts["down"],
        "tech_same": delta_counts["same"],
    }

    slim_rows = [{k: v for k, v in r.items() if k != "events"} for r in rows]
    hits_new_not_old = [e for e in all_events if e["new_tech"] >= 7 > e["old_tech"]]
    hits_old_not_new = [e for e in all_events if e["old_tech"] >= 7 > e["new_tech"]]
    payload = {
        "overall": overall,
        "per_symbol": slim_rows,
        "gained_7s": hits_new_not_old[:40],
        "lost_7s": hits_old_not_new[:40],
        "gained_7s_count": len(hits_new_not_old),
        "lost_7s_count": len(hits_old_not_new),
    }
    ARTIFACT.parent.mkdir(parents=True, exist_ok=True)
    ARTIFACT.write_text(json.dumps(payload, indent=2), encoding="utf-8")

    print("\n=== OVERALL (same 20 stocks, seed=42, 80 quiet days/stock) ===")
    print(json.dumps(overall, indent=2))
    print(f"gained 7s (new only): {len(hits_new_not_old)}")
    print(f"lost 7s (old only): {len(hits_old_not_new)}")
    print(f"wrote {ARTIFACT}")


if __name__ == "__main__":
    main()
