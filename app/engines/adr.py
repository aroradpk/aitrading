"""Per-scrip range targets on the 5-scrip book.

ADR20 is still reported for context. The *trade* target is a fixed next-session
range for each name (HDFC 2%, BAJ/M&M 3%, Nifty 1%, Bank Nifty 1.2%) — not 5%
and not 1.25× ADR.

Hit = next session (high-low)/prior close >= that name's target.
A 7 fires on setup-day live volume (>=1.5× 20d).
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
FALLBACK_TARGETS = {
    "HDFCBANK": 2.0,
    "BAJFINANCE": 3.0,
    "M&M": 3.0,
    "NIFTY_50": 1.0,
    "NIFTY_BANK": 1.2,
}


def adr_window() -> int:
    intra = get_settings().technical.intraday
    return int(getattr(intra, "adr_window", DEFAULT_WINDOW) or DEFAULT_WINDOW)


def target_map() -> dict[str, float]:
    out = dict(FALLBACK_TARGETS)
    try:
        for entry in load_trading_instruments():
            symbol = entry.get("symbol")
            if symbol and entry.get("target_range_pct") is not None:
                out[symbol] = float(entry["target_range_pct"])
    except FileNotFoundError:
        pass
    return out


def target_for(symbol: str) -> float:
    return float(target_map().get(symbol) or FALLBACK_TARGETS.get(symbol) or 0.0)


def daily_range_pct(frame: pd.DataFrame) -> pd.Series:
    prev = frame["close"].shift(1)
    return (frame["high"] - frame["low"]) / prev * 100


def attach_adr(frame: pd.DataFrame, *, window: int | None = None) -> pd.DataFrame:
    if window is None:
        window = adr_window()
    out = frame.copy()
    out["range_pts"] = out["high"] - out["low"]
    out["range_pct"] = daily_range_pct(out)
    out["adr_pct"] = out["range_pct"].rolling(window).mean()
    out["adr_pts"] = out["range_pts"].rolling(window).mean()
    return out


def snapshot_adr(frame: pd.DataFrame, *, symbol: str | None = None) -> dict[str, Any]:
    window = adr_window()
    enriched = attach_adr(frame, window=window)
    last = enriched.iloc[-1]
    adr_pct = float(last["adr_pct"]) if pd.notna(last.get("adr_pct")) else 0.0
    adr_pts = float(last["adr_pts"]) if pd.notna(last.get("adr_pts")) else 0.0
    adr14 = float(enriched["range_pct"].rolling(14).mean().iloc[-1]) if len(enriched) >= 14 else adr_pct
    symbol = symbol or str(last.get("symbol") or frame["symbol"].iloc[-1])
    target = target_for(symbol)
    return {
        "window": window,
        "symbol": symbol,
        "adr20_pct": round(adr_pct, 2),
        "adr14_pct": round(adr14, 2) if pd.notna(adr14) else round(adr_pct, 2),
        "adr20_pts": round(adr_pts, 2),
        "target_range_pct": target,
        "as_of": frame.index[-1].date().isoformat(),
    }


def is_adr_expansion_setup(confirmations: dict[str, bool], snapshot: dict | None = None) -> bool:
    """Setup-day live volume is the portable lift vs next-session range hitting the name's target."""
    if confirmations.get("late_bar"):
        return False
    return bool(confirmations.get("live_rvol"))


def next_session_range_hit(frame: pd.DataFrame, setup_date: str, *, symbol: str | None = None) -> dict | None:
    window = adr_window()
    enriched = attach_adr(frame, window=window)
    target_ts = pd.Timestamp(setup_date).normalize()
    idx = None
    for i, stamp in enumerate(enriched.index):
        if pd.Timestamp(stamp).normalize() == target_ts:
            idx = i
            break
    if idx is None or idx + 1 >= len(enriched):
        return None
    symbol = symbol or str(enriched["symbol"].iloc[idx])
    target = target_for(symbol)
    nxt_range = float(enriched["range_pct"].iloc[idx + 1])
    adr = float(enriched["adr_pct"].iloc[idx]) if pd.notna(enriched["adr_pct"].iloc[idx]) else 0.0
    if pd.isna(nxt_range):
        return None
    setup_close = float(enriched["close"].iloc[idx])
    nxt = enriched.iloc[idx + 1]
    mfe = max(
        abs(float(nxt["high"]) / setup_close - 1) * 100,
        abs(float(nxt["low"]) / setup_close - 1) * 100,
    )
    return {
        "next_date": enriched.index[idx + 1].date().isoformat(),
        "next_range_pct": round(nxt_range, 3),
        "mfe_pct": round(mfe, 3),
        "adr20_pct": round(adr, 3),
        "target_range_pct": target,
        "hit_adr": bool(nxt_range >= target),
        "hit_mfe": bool(mfe >= target),
    }


def build_adr_profiles() -> dict[str, Any]:
    window = adr_window()
    instruments = []
    for entry in load_trading_instruments() or all_instruments():
        symbol = entry["symbol"]
        path = ohlcv_daily_dir() / f"{symbol}.parquet"
        if not path.exists():
            continue
        frame = load_ohlcv(path)
        snap = snapshot_adr(frame, symbol=symbol)
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
        "hit_definition": (
            "Next session (high-low)/prior close >= that name's fixed target "
            "(HDFC 2%, BAJFINANCE 3%, M&M 3%, Nifty 1%, Bank Nifty 1.2%)."
        ),
        "expansion_factor": {
            "name": "live_rvol",
            "rule": "Volume >= 1.5x 20-day average on the setup day",
            "note": "A 7 is one trade per name per setup day. Correct = next session range hits the fixed target.",
        },
        "instruments": instruments,
    }
    adr_profile_path().write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return payload
