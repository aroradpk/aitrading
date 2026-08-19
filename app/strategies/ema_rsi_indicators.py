"""Quant definitions for Strategy 1. All windows end at the current bar (no future peek)."""

from __future__ import annotations

import pandas as pd

from app.features.technical import _rsi, _true_range
from app.strategies.ema_rsi_config import EmaRsiConfig


def add_s1_columns(frame: pd.DataFrame, cfg: EmaRsiConfig | None = None) -> pd.DataFrame:
    cfg = cfg or EmaRsiConfig()
    out = frame.copy()
    if "ts" in out.columns:
        out = out.sort_values("ts").reset_index(drop=True)
    else:
        out = out.sort_values("date").reset_index(drop=True)
    close = out["close"].astype(float)
    if "atr_14" not in out.columns:
        out["atr_14"] = _true_range(out).rolling(cfg.atr_length, min_periods=cfg.atr_length).mean()
    atr = out["atr_14"].replace(0.0, pd.NA)
    out["rsi_14"] = _rsi(close, cfg.rsi_length)
    out["ema_20"] = close.ewm(span=cfg.ema_fast, adjust=False).mean()
    out["ema_50"] = close.ewm(span=cfg.ema_slow, adjust=False).mean()
    k = cfg.slope_bars
    m = cfg.spread_bars
    out["ema20_slope_pct"] = out["ema_20"].pct_change()
    out["ema50_slope_pct"] = out["ema_50"].pct_change()
    out["ema20_slope_atr"] = (out["ema_20"] - out["ema_20"].shift(k)) / atr
    out["ema50_slope_atr"] = (out["ema_50"] - out["ema_50"].shift(k)) / atr
    out["ema20_accel_atr"] = out["ema20_slope_atr"] - out["ema20_slope_atr"].shift(1)
    out["ema50_accel_atr"] = out["ema50_slope_atr"] - out["ema50_slope_atr"].shift(1)
    out["ema_spread_abs"] = out["ema_20"] - out["ema_50"]
    out["ema_spread_pct"] = out["ema_spread_abs"] / close
    out["ema_spread_atr"] = out["ema_spread_abs"] / atr
    out["ema_spread_exp_atr"] = out["ema_spread_atr"] - out["ema_spread_atr"].shift(m)
    rsi = out["rsi_14"]
    p = cfg.rsi_persist_bars
    out["rsi_delta"] = rsi - rsi.shift(1)
    out["rsi_prev_max"] = rsi.shift(1).rolling(p, min_periods=p).max()
    out["rsi_prev_min"] = rsi.shift(1).rolling(p, min_periods=p).min()
    out["rsi_cross_up_60"] = (rsi >= cfg.rsi_long_level) & (rsi.shift(1) < cfg.rsi_long_level)
    out["rsi_cross_down_40"] = (rsi <= cfg.rsi_short_level) & (rsi.shift(1) > cfg.rsi_short_level)
    out["rsi_persist_below_60"] = out["rsi_prev_max"] < cfg.rsi_long_level
    out["rsi_persist_above_40"] = out["rsi_prev_min"] > cfg.rsi_short_level
    out["close_vs_ema50"] = close - out["ema_50"]
    return out


def last_bar_by_session(tf_frame: pd.DataFrame, cfg: EmaRsiConfig | None = None) -> dict:
    if tf_frame is None or tf_frame.empty:
        return {}
    annotated = add_s1_columns(tf_frame, cfg)
    if "session_date" not in annotated.columns:
        raw_ts = pd.to_datetime(annotated["ts"], utc=True, errors="coerce")
        if raw_ts.notna().any():
            annotated["session_date"] = raw_ts.dt.tz_convert("Asia/Kolkata").dt.date
        else:
            annotated["session_date"] = pd.to_datetime(annotated["ts"]).dt.date
    last = annotated.groupby("session_date", as_index=False).tail(1)
    return {row["session_date"]: row for _, row in last.iterrows()}
