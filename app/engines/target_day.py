"""Days that printed each name's fixed % rise, plus technical flags on those days.

Hit = session high vs prior close >= that name's target_range_pct (upside MFE).
This is anatomy, not a trade setup: no 5/6/7 gate.
"""

from __future__ import annotations

from collections import Counter
from typing import Any

import pandas as pd

from app.core.paths import ohlcv_daily_dir
from app.engines.adr import target_for
from app.engines.pattern_confirmations import confirmation_labels, detect_daily_confirmations
from app.engines.technical import _ema, _rsi
from app.engines.universe import load_trading_instruments
from app.ingest.yfinance_client import load_ohlcv

WARMUP = 40


def attach_upside(frame: pd.DataFrame) -> pd.DataFrame:
    out = frame.copy()
    prev = out["close"].shift(1)
    out["prev_close"] = prev
    out["upside_pct"] = (out["high"] / prev - 1) * 100
    out["downside_pct"] = (1 - out["low"] / prev) * 100
    out["close_pct"] = (out["close"] / prev - 1) * 100
    out["range_pct"] = (out["high"] - out["low"]) / prev * 100
    out["gap_pct"] = (out["open"] / prev - 1) * 100
    return out


def lookback_meta(frame: pd.DataFrame, *, symbol: str) -> dict[str, Any]:
    if frame.empty:
        return {"symbol": symbol, "sessions": 0, "first": None, "last": None}
    return {
        "symbol": symbol,
        "sessions": int(len(frame)),
        "first": frame.index[0].date().isoformat(),
        "last": frame.index[-1].date().isoformat(),
        "target_range_pct": target_for(symbol),
    }


def _active_flags(confirmations: dict[str, bool]) -> list[str]:
    return sorted(key for key, value in confirmations.items() if value)


def scan_symbol_up_days(frame: pd.DataFrame, *, symbol: str, side: str = "long") -> dict[str, Any]:
    target = target_for(symbol)
    enriched = attach_upside(frame)
    meta = lookback_meta(enriched, symbol=symbol)
    days: list[dict[str, Any]] = []
    flag_hits: Counter[str] = Counter()
    flag_all: Counter[str] = Counter()
    n_scored = 0
    prev_conf: dict[str, bool] = {}

    for i in range(WARMUP, len(enriched)):
        row = enriched.iloc[i]
        conf = detect_daily_confirmations(enriched.iloc[: i + 1], side)
        n_scored += 1
        for key, value in conf.items():
            if value:
                flag_all[key] += 1
        is_hit = bool(row["upside_pct"] >= target)
        if is_hit:
            for key, value in conf.items():
                if value:
                    flag_hits[key] += 1
            day = enriched.iloc[: i + 1]
            closes = day["close"]
            days.append(
                {
                    "symbol": symbol,
                    "date": enriched.index[i].date().isoformat(),
                    "target_range_pct": target,
                    "upside_pct": round(float(row["upside_pct"]), 3),
                    "close_pct": round(float(row["close_pct"]), 3),
                    "range_pct": round(float(row["range_pct"]), 3),
                    "gap_pct": round(float(row["gap_pct"]), 3),
                    "close": round(float(row["close"]), 2),
                    "volume": int(row["volume"]) if pd.notna(row.get("volume")) else None,
                    "confirmations": _active_flags(conf),
                    "labels": confirmation_labels(conf),
                    "prior_confirmations": _active_flags(prev_conf),
                    "rsi_14": _rsi(closes),
                    "ema_20": _ema(closes, 20),
                    "ema_50": _ema(closes, 50),
                    "ema_200": _ema(closes, 200),
                }
            )
        prev_conf = conf

    days.reverse()

    n_hits = len(days)
    rates = []
    for key in sorted(set(flag_all) | set(flag_hits)):
        all_n = flag_all.get(key, 0)
        hit_n = flag_hits.get(key, 0)
        base = all_n / n_scored if n_scored else 0.0
        hit_rate = hit_n / n_hits if n_hits else 0.0
        rates.append(
            {
                "flag": key,
                "hit_days": hit_n,
                "pct_of_hit_days": round(100 * hit_rate, 1),
                "pct_of_all_days": round(100 * base, 1),
                "lift": round(hit_rate / base, 2) if base else None,
            }
        )
    rates.sort(key=lambda item: (-(item["lift"] or 0), -item["pct_of_hit_days"]))

    return {
        "lookback": meta,
        "hit_definition": "high vs prior close >= target_range_pct (upside)",
        "n_scored_sessions": n_scored,
        "n_hit_days": n_hits,
        "base_hit_pct": round(100 * n_hits / n_scored, 1) if n_scored else None,
        "days": days,
        "flag_rates": rates,
    }


def scan_book(*, side: str = "long") -> dict[str, Any]:
    instruments = []
    all_days: list[dict] = []
    firsts: list[str] = []
    lasts: list[str] = []
    sessions = 0
    for entry in load_trading_instruments():
        symbol = entry["symbol"]
        path = ohlcv_daily_dir() / f"{symbol}.parquet"
        if not path.exists():
            continue
        frame = load_ohlcv(path)
        result = scan_symbol_up_days(frame, symbol=symbol, side=side)
        instruments.append(result)
        all_days.extend(result["days"])
        meta = result["lookback"]
        sessions += meta["sessions"]
        if meta["first"]:
            firsts.append(meta["first"])
        if meta["last"]:
            lasts.append(meta["last"])
    all_days.sort(key=lambda item: (item["date"], item["symbol"]), reverse=True)
    return {
        "hit_definition": "Session high vs prior close >= that name's fixed target (rise).",
        "side": side,
        "coverage": {
            "symbols": [row["lookback"]["symbol"] for row in instruments],
            "sessions_sum": sessions,
            "oldest_bar": min(firsts) if firsts else None,
            "newest_bar": max(lasts) if lasts else None,
        },
        "instruments": instruments,
        "all_hit_days_recent_first": all_days,
    }


def format_report(book: dict[str, Any], *, per_symbol_limit: int = 25) -> str:
    cov = book["coverage"]
    lines = [
        "Target-day anatomy (rise = high vs prior close >= book target)",
        f"Lookback: {cov['oldest_bar']} → {cov['newest_bar']}",
        f"Symbols: {', '.join(cov['symbols'])}",
        f"Sessions summed across names: {cov['sessions_sum']}",
        f"Definition: {book['hit_definition']}",
        "",
    ]
    for inst in book["instruments"]:
        meta = inst["lookback"]
        lines.append(
            f"=== {meta['symbol']}  target {meta['target_range_pct']}%  "
            f"{meta['first']} → {meta['last']}  ({meta['sessions']} sessions)  "
            f"hits {inst['n_hit_days']} / {inst['n_scored_sessions']} "
            f"({inst['base_hit_pct']}%) ==="
        )
        lines.append("Trait rates on hit days vs all scored days (lift >1 means more common on up-target days):")
        for rate in inst["flag_rates"][:18]:
            lift = "n/a" if rate["lift"] is None else f"{rate['lift']:.2f}x"
            lines.append(
                f"  {rate['flag']:28} hit {rate['pct_of_hit_days']:5.1f}%  "
                f"all {rate['pct_of_all_days']:5.1f}%  lift {lift}"
            )
        lines.append(f"Hit days newest → oldest (showing {min(per_symbol_limit, inst['n_hit_days'])}):")
        for day in inst["days"][:per_symbol_limit]:
            reasons = ", ".join(day["confirmations"][:12]) or "(none)"
            prior = ", ".join(day["prior_confirmations"][:8]) or "(none)"
            lines.append(
                f"  {day['date']}  up {day['upside_pct']:+.2f}%  close {day['close_pct']:+.2f}%  "
                f"range {day['range_pct']:.2f}%  gap {day['gap_pct']:+.2f}%  "
                f"RSI {day['rsi_14']}"
            )
            lines.append(f"    that day: {reasons}")
            lines.append(f"    prior day: {prior}")
        lines.append("")
    return "\n".join(lines) + "\n"
