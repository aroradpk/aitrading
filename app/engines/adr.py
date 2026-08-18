"""Average Daily Range for the 5-scrip book.

ADR20 = mean of the last 20 sessions' (high-low)/prior close, in percent.
A trade day is a *higher-ADR* session: next range >= expansion_mult * ADR20
(default 1.25x). This replaces a fixed 5% target — Bank Nifty's ADR is ~0.9%,
Bajaj's is ~2.3%.

The factor that lifts next-session 1.25x-ADR days on all five names is live
volume (>=1.5x 20d). EMA support, dead volume, and Fib are not expansion gates.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any

import pandas as pd

from app.core.config import get_settings
from app.core.paths import adr_profile_path, ohlcv_daily_dir
from app.engines.universe import all_instruments, load_trading_instruments
from app.ingest.yfinance_client import load_ohlcv

DEFAULT_WINDOW = 20
DEFAULT_EXPANSION_MULT = 1.25


def adr_settings() -> tuple[int, float]:
    intra = get_settings().technical.intraday
    window = int(getattr(intra, "adr_window", DEFAULT_WINDOW) or DEFAULT_WINDOW)
    mult = float(getattr(intra, "expansion_mult", DEFAULT_EXPANSION_MULT) or DEFAULT_EXPANSION_MULT)
    return window, mult


def daily_range_pct(frame: pd.DataFrame) -> pd.Series:
    prev = frame["close"].shift(1)
    return (frame["high"] - frame["low"]) / prev * 100


def attach_adr(frame: pd.DataFrame, *, window: int | None = None) -> pd.DataFrame:
    if window is None:
        window, _ = adr_settings()
    out = frame.copy()
    out["range_pts"] = out["high"] - out["low"]
    out["range_pct"] = daily_range_pct(out)
    out["adr_pct"] = out["range_pct"].rolling(window).mean()
    out["adr_pts"] = out["range_pts"].rolling(window).mean()
    return out


def snapshot_adr(frame: pd.DataFrame) -> dict[str, Any]:
    window, mult = adr_settings()
    enriched = attach_adr(frame, window=window)
    last = enriched.iloc[-1]
    adr_pct = float(last["adr_pct"]) if pd.notna(last.get("adr_pct")) else 0.0
    adr_pts = float(last["adr_pts"]) if pd.notna(last.get("adr_pts")) else 0.0
    adr14 = float(enriched["range_pct"].rolling(14).mean().iloc[-1]) if len(enriched) >= 14 else adr_pct
    return {
        "window": window,
        "expansion_mult": mult,
        "adr20_pct": round(adr_pct, 2),
        "adr14_pct": round(adr14, 2) if pd.notna(adr14) else round(adr_pct, 2),
        "adr20_pts": round(adr_pts, 2),
        "target_range_pct": round(adr_pct * mult, 2),
        "as_of": frame.index[-1].date().isoformat(),
    }


def is_adr_expansion_setup(confirmations: dict[str, bool], snapshot: dict | None = None) -> bool:
    """Setup-day live volume is the portable lift vs next-session range >= 1.25x ADR."""
    if confirmations.get("late_bar"):
        return False
    return bool(confirmations.get("live_rvol"))


def next_session_range_hit(frame: pd.DataFrame, setup_date: str) -> dict | None:
    window, mult = adr_settings()
    enriched = attach_adr(frame, window=window)
    target = pd.Timestamp(setup_date).normalize()
    idx = None
    for i, stamp in enumerate(enriched.index):
        if pd.Timestamp(stamp).normalize() == target:
            idx = i
            break
    if idx is None or idx + 1 >= len(enriched):
        return None
    adr = float(enriched["adr_pct"].iloc[idx])
    nxt_range = float(enriched["range_pct"].iloc[idx + 1])
    if pd.isna(adr) or adr <= 0 or pd.isna(nxt_range):
        return None
    return {
        "next_date": enriched.index[idx + 1].date().isoformat(),
        "next_range_pct": round(nxt_range, 3),
        "adr20_pct": round(adr, 3),
        "expansion_mult": round(nxt_range / adr, 3),
        "hit_adr": bool(nxt_range >= mult * adr),
        "target_range_pct": round(adr * mult, 3),
    }


def build_adr_profiles() -> dict[str, Any]:
    window, mult = adr_settings()
    instruments = []
    for entry in load_trading_instruments() or all_instruments():
        symbol = entry["symbol"]
        path = ohlcv_daily_dir() / f"{symbol}.parquet"
        if not path.exists():
            continue
        frame = load_ohlcv(path)
        snap = snapshot_adr(frame)
        instruments.append(
            {
                "symbol": symbol,
                "name": entry.get("name", symbol),
                "type": entry.get("type", "stock"),
                **snap,
            }
        )
    payload = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "window": window,
        "expansion_mult": mult,
        "hit_definition": (
            f"Next session (high-low)/prior close >= {mult} × ADR{window}. "
            "Not a 5% close target."
        ),
        "expansion_factor": {
            "name": "live_rvol",
            "rule": "Volume >= 1.5x 20-day average on the setup day",
            "note": (
                "Backtest (~252 sessions): live_rvol lifts next-session 1.25x-ADR hit rate "
                "on all 5 names (HDFC +4.6pp, BAJ +12pp, M&M +17pp, Nifty +25pp n=10, "
                "Bank Nifty +12pp). Range expansion helps M&M/Nifty; EMA support and dead "
                "volume do not. A 7 is an ADR-expansion call, not a 5% prediction."
            ),
        },
        "instruments": instruments,
    }
    adr_profile_path().write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return payload
