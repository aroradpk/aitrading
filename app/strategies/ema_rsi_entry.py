from __future__ import annotations

from dataclasses import dataclass
from datetime import date

import pandas as pd

from app.features.technical import _rsi
from app.strategies.ema_rsi_config import EmaRsiConfig
from app.strategies.ema_rsi_expansion import DailySetup, htf_structure_agrees, planned_stop_target
from app.strategies.ema_rsi_indicators import add_s1_columns


@dataclass
class EntryResult:
    entered: bool
    failed_before_entry: bool
    entry_ts: object | None
    entry_price: float | None
    stop: float | None
    target: float | None
    confirm_tf: str
    reason: str


def _forming_daily_rsi(daily_closes: list[float], forming_close: float, length: int) -> float:
    series = pd.Series([*daily_closes, forming_close], dtype=float)
    rsi = _rsi(series, length)
    return float(rsi.iloc[-1])


def _price_confirms(side: str, bar: pd.Series, prev: pd.Series | None, cfg: EmaRsiConfig) -> bool:
    if cfg.price_confirm == "close_above_prev_high" and prev is not None:
        if side == "long":
            return float(bar["close"]) > float(prev["high"])
        return float(bar["close"]) < float(prev["low"])
    if side == "long":
        return float(bar["close"]) > float(bar["open"])
    return float(bar["close"]) < float(bar["open"])


def _h1_ok(h1: pd.DataFrame | pd.Series | None, ts, side: str) -> bool:
    if h1 is None:
        return True
    if isinstance(h1, pd.DataFrame):
        if "ts" not in h1.columns or ts is None:
            last = h1.iloc[-1]
        else:
            prior = h1[pd.to_datetime(h1["ts"]) <= pd.to_datetime(ts)]
            if prior.empty:
                return True
            last = prior.iloc[-1]
        return htf_structure_agrees(last, side) is not False
    return htf_structure_agrees(h1, side) is not False


def find_next_day_entry(
    setup: DailySetup,
    bars_15m: pd.DataFrame,
    next_session: date,
    daily_closes_through_setup: list[float],
    h1_last_completed: pd.DataFrame | pd.Series | None,
    cfg: EmaRsiConfig | None = None,
) -> EntryResult:
    """Compute 15m RSI on the full history, then only *act* on next-session bars."""
    cfg = cfg or EmaRsiConfig()
    if bars_15m is None or bars_15m.empty:
        return EntryResult(False, True, None, None, None, None, "15m", "no_15m_data")
    bars = add_s1_columns(bars_15m, cfg)
    if "session_date" not in bars.columns:
        ts = pd.to_datetime(bars["ts"], utc=True)
        bars["session_date"] = ts.dt.tz_convert("Asia/Kolkata").dt.date
    session = bars[bars["session_date"] == next_session].reset_index(drop=True)
    if session.empty:
        return EntryResult(False, True, None, None, None, None, "15m", "no_15m_session")
    pulled = False
    rows = list(session.itertuples(index=False))
    for i, row in enumerate(rows):
        bar = pd.Series(row._asdict())
        ts = bar.get("ts")
        if not _h1_ok(h1_last_completed, ts, setup.side):
            continue
        forming_rsi = _forming_daily_rsi(daily_closes_through_setup, float(bar["close"]), cfg.rsi_length)
        if setup.side == "long" and forming_rsi <= cfg.rsi_long_level:
            continue
        if setup.side == "short" and forming_rsi >= cfg.rsi_short_level:
            continue
        rsi = float(bar["rsi_14"])
        if pd.isna(rsi):
            continue
        if setup.side == "long" and rsi <= cfg.ltf_rsi_long_pullback:
            pulled = True
        if setup.side == "short" and rsi >= cfg.ltf_rsi_short_rally:
            pulled = True
        prev = pd.Series(rows[i - 1]._asdict()) if i else None
        prev_rsi = float(prev["rsi_14"]) if prev is not None and pd.notna(prev["rsi_14"]) else rsi
        if setup.side == "long":
            rebound = pulled and prev_rsi <= cfg.ltf_rsi_long_pullback and rsi > cfg.ltf_rsi_long_pullback
        else:
            rebound = pulled and prev_rsi >= cfg.ltf_rsi_short_rally and rsi < cfg.ltf_rsi_short_rally
        if not rebound or not _price_confirms(setup.side, bar, prev, cfg):
            continue
        if cfg.enter_next_bar_open:
            if i + 1 >= len(rows):
                return EntryResult(False, True, None, None, None, None, "15m", "confirmed_but_no_next_bar")
            fill_bar = pd.Series(rows[i + 1]._asdict())
            fill = float(fill_bar["open"])
            fill_ts = fill_bar.get("ts")
        else:
            fill = float(bar["close"])
            fill_ts = bar.get("ts")
        stop, target, _ = planned_stop_target(
            setup.side, fill, setup.atr, setup.day_low, setup.day_high, cfg
        )
        return EntryResult(True, False, fill_ts, fill, stop, target, "15m", "entered")
    return EntryResult(False, True, None, None, None, None, "15m", "no_bounce_confirmation")


def simulate_same_day(
    side: str,
    fill: float,
    stop: float,
    target: float,
    path: pd.DataFrame,
    fill_ts,
) -> dict:
    after = path
    if fill_ts is not None and "ts" in path.columns:
        after = path[pd.to_datetime(path["ts"]) >= pd.to_datetime(fill_ts)]
    if after.empty:
        return {"exit": fill, "reason": "close", "mfe": 0.0, "mae": 0.0, "hit_target": 0}
    mfe = 0.0
    mae = 0.0
    for row in after.itertuples(index=False):
        high = float(row.high)
        low = float(row.low)
        if side == "long":
            mfe = max(mfe, (high - fill) / fill)
            mae = min(mae, (low - fill) / fill)
            hit_stop = low <= stop
            hit_tgt = high >= target
        else:
            mfe = max(mfe, (fill - low) / fill)
            mae = min(mae, (fill - high) / fill)
            hit_stop = high >= stop
            hit_tgt = low <= target
        if hit_stop and hit_tgt:
            return {"exit": stop, "reason": "stop", "mfe": mfe, "mae": mae, "hit_target": 0}
        if hit_stop:
            return {"exit": stop, "reason": "stop", "mfe": mfe, "mae": mae, "hit_target": 0}
        if hit_tgt:
            return {"exit": target, "reason": "target", "mfe": mfe, "mae": mae, "hit_target": 1}
    last = float(after.iloc[-1]["close"])
    return {"exit": last, "reason": "close", "mfe": mfe, "mae": mae, "hit_target": 0}
