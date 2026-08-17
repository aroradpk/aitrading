#!/usr/bin/env python3
"""Per-symbol 5%+ move backtest: day-before conviction table and gap buckets."""

from __future__ import annotations

import json
import sys
from collections import Counter
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.core.paths import ohlcv_daily_dir
from app.engines.conviction import conviction_from_scores
from app.engines.events import score_events
from app.engines.fundamental import score_fundamentals
from app.engines.move_detector import load_moves, scan_today_setup
from app.engines.pattern_confirmations import detect_daily_confirmations
from app.engines.themes import score_themes
from app.ingest.yfinance_client import load_ohlcv

DEFAULT_SYMBOLS = [
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


def gap_reason(row: dict) -> str:
    conf = row["confirmations"]
    tech = row["technical"]
    if tech >= 7:
        return "hit"
    if conf.get("ema20_support") and conf.get("ema_momentum_expanding") and not conf.get("consolidation_anchor"):
        return "missing_consolidation"
    if conf.get("ema_momentum_expanding") and not conf.get("ema20_support"):
        return "missing_ema20_support"
    if conf.get("ema20_support") and not conf.get("ema_momentum_expanding"):
        return "missing_ema_momentum"
    if conf.get("rsi_60_reclaim") and not conf.get("ema20_support"):
        return "rsi_only"
    if conf.get("bullish_formation") and tech < 4:
        return "formation_without_base"
    if tech >= 5:
        return "near_miss_5_7"
    if tech >= 3:
        return "partial_setup_3_5"
    return "weak_or_news_gap"


def evaluate_symbol(symbol: str, threshold: float = 5.0) -> list[dict]:
    path = ohlcv_daily_dir() / f"{symbol}.parquet"
    if not path.exists():
        return []
    frame = load_ohlcv(path)
    pct = frame["close"].pct_change() * 100
    fund, _ = score_fundamentals(symbol)
    theme, _, _ = score_themes(symbol)
    rows: list[dict] = []
    for i in range(1, len(frame)):
        move_pct = pct.iloc[i]
        if pd.isna(move_pct) or abs(move_pct) < threshold:
            continue
        signal_idx = i - 1
        signal_date = frame.index[signal_idx].date().isoformat()
        move_date = frame.index[i].date().isoformat()
        side = "long" if float(move_pct) > 0 else "short"
        slice_ = frame.iloc[: signal_idx + 1]
        hist = [m for m in load_moves(symbol) if m.get("date", "") < signal_date]
        setup = scan_today_setup(slice_, hist, side=side, symbol=symbol)
        events, _ = score_events(symbol, as_of=frame.index[signal_idx].date())
        scores = conviction_from_scores(setup["technical_score"], fund, events, theme)
        conf = setup.get("pattern_confirmations") or detect_daily_confirmations(slice_, side)
        row = {
            "symbol": symbol,
            "signal_date": signal_date,
            "move_date": move_date,
            "move_pct": round(float(move_pct), 2),
            "side": side,
            "technical": scores["technical"],
            "research": scores["research"],
            "theme_bonus": scores["theme_bonus"],
            "conviction": scores["final"],
            "confirmations": {k: bool(v) for k, v in conf.items() if isinstance(v, (bool, int))},
            "labels": setup.get("confirmation_labels", []),
            "breakout_base": bool(setup.get("breakout_base")),
        }
        row["gap"] = gap_reason(row)
        rows.append(row)
    return rows


def summarize(rows: list[dict]) -> dict:
    n = len(rows)
    if not n:
        return {"moves": 0}
    return {
        "moves": n,
        "up": sum(1 for r in rows if r["side"] == "long"),
        "down": sum(1 for r in rows if r["side"] == "short"),
        "hit_ge_7": sum(1 for r in rows if r["conviction"] >= 7),
        "ok_ge_5": sum(1 for r in rows if r["conviction"] >= 5),
        "pct_ge_7": round(100 * sum(1 for r in rows if r["conviction"] >= 7) / n, 1),
        "pct_ge_5": round(100 * sum(1 for r in rows if r["conviction"] >= 5) / n, 1),
        "avg_tech": round(sum(r["technical"] for r in rows) / n, 2),
        "avg_conv": round(sum(r["conviction"] for r in rows) / n, 2),
        "max_conv": max(r["conviction"] for r in rows),
        "gaps": dict(Counter(r["gap"] for r in rows)),
    }


def main() -> None:
    all_rows: list[dict] = []
    by_symbol: dict[str, dict] = {}
    for symbol in DEFAULT_SYMBOLS:
        rows = evaluate_symbol(symbol)
        all_rows.extend(rows)
        by_symbol[symbol] = summarize(rows)
        print(f"done {symbol} moves={by_symbol[symbol].get('moves', 0)}")

    payload = {
        "symbols": DEFAULT_SYMBOLS,
        "total_moves": len(all_rows),
        "summary": by_symbol,
        "overall": summarize(all_rows),
        "hits": [r for r in all_rows if r["conviction"] >= 7],
        "near_misses": [
            r
            for r in all_rows
            if 5 <= r["conviction"] < 7
        ][:40],
    }
    out = Path("/opt/cursor/artifacts/prior_day_17_stocks.json")
    out.parent.mkdir(parents=True, exist_ok=True)
    serializable = json.loads(json.dumps(payload, default=str))
    out.write_text(json.dumps(serializable, indent=2), encoding="utf-8")

    print("\n=== PER SYMBOL ===")
    print(f"{'symbol':12} {'n':>4} {'>=7':>4} {'>=5':>4} {'avgT':>5} {'avgC':>5} {'maxC':>5}")
    for symbol in DEFAULT_SYMBOLS:
        s = by_symbol[symbol]
        print(
            f"{symbol:12} {s.get('moves',0):4} {s.get('hit_ge_7',0):4} {s.get('ok_ge_5',0):4} "
            f"{s.get('avg_tech',0):5.2f} {s.get('avg_conv',0):5.2f} {s.get('max_conv',0):5.1f}"
        )
    overall = summarize(all_rows)
    print("\n=== OVERALL ===")
    print(overall)
    print("\n=== GAP BUCKETS ===")
    print(overall.get("gaps"))
    print(f"\nwrote {out}")


if __name__ == "__main__":
    main()
