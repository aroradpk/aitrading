from __future__ import annotations

from datetime import date, timedelta

import pandas as pd

from app.strategies.ema_rsi_config import EmaRsiConfig
from app.strategies.ema_rsi_entry import find_next_day_entry, simulate_same_day
from app.strategies.ema_rsi_expansion import classify_grade, detect_daily_setups, planned_stop_target
from app.strategies.ema_rsi_indicators import add_s1_columns


def _rising_daily(n: int = 80) -> pd.DataFrame:
    close = pd.Series(range(n)).astype(float) * 2 + 100
    close.iloc[-8:-1] = close.iloc[-8] + pd.Series(range(7)).astype(float) * 0.2
    close.iloc[-1] = close.iloc[-2] + 8
    return pd.DataFrame(
        {
            "date": pd.bdate_range("2023-01-02", periods=n).date,
            "open": close - 0.4,
            "high": close + 1.0,
            "low": close - 1.0,
            "close": close,
            "volume": 100_000.0,
        }
    )


def test_s1_columns_use_only_past_bars() -> None:
    frame = _rising_daily(90)
    base = add_s1_columns(frame)
    t = 70
    snap = base.loc[t, ["ema_20", "ema_50", "ema20_slope_atr", "ema_spread_atr", "rsi_14"]].to_dict()
    mutated = frame.copy()
    mutated.loc[t + 1 :, "close"] *= 1.5
    again = add_s1_columns(mutated)
    for key, value in snap.items():
        assert abs(float(again.loc[t, key]) - float(value)) < 1e-9


def test_planned_stop_target_atr_long() -> None:
    cfg = EmaRsiConfig(stop_mode="atr", sl_atr=1.0, tp_mode="rr", rr=1.5)
    stop, target, rr = planned_stop_target("long", 100.0, 2.0, 95.0, 105.0, cfg)
    assert stop == 98.0
    assert abs(target - 103.0) < 1e-9
    assert abs(rr - 1.5) < 1e-9


def test_pct_target_is_80bps() -> None:
    cfg = EmaRsiConfig(stop_mode="atr", sl_atr=1.0, tp_mode="pct", tp_pct=0.008)
    stop, target, rr = planned_stop_target("long", 100.0, 2.0, 95.0, 105.0, cfg)
    assert stop == 98.0
    assert abs(target - 100.8) < 1e-9


def test_lower_tf_cannot_fail_a_1d_pass() -> None:
    row = pd.Series(
        {
            "ema20_slope_atr": 0.06,
            "ema20_accel_atr": 0.01,
            "ema_spread_exp_atr": 0.03,
        }
    )
    cfg = EmaRsiConfig()
    grade = classify_grade("long", row, cfg, confirm_1h=False, confirm_15m=False)
    assert grade == "Early Setup"


def test_simulate_adverse_first() -> None:
    path = pd.DataFrame(
        {
            "ts": pd.to_datetime(["2024-01-02 04:00Z", "2024-01-02 04:15Z"]),
            "open": [100.0, 101.0],
            "high": [104.0, 104.0],
            "low": [97.0, 99.0],
            "close": [101.0, 102.0],
        }
    )
    out = simulate_same_day("long", 100.0, 98.0, 103.0, path, path["ts"].iloc[0])
    assert out["reason"] == "stop"
    assert out["hit_target"] == 0


def test_detect_runs_on_daily_frame() -> None:
    setups = detect_daily_setups(_rising_daily(120), "NIFTY", EmaRsiConfig())
    assert isinstance(setups, list)


def test_missing_15m_is_no_entry_not_a_loss() -> None:
    setups = detect_daily_setups(_rising_daily(120), "NIFTY")
    if not setups:
        return
    setup = setups[0]
    result = find_next_day_entry(setup, pd.DataFrame(), setup.asof_date + timedelta(days=1), [100.0] * 30, None)
    assert result.entered is False
    assert result.reason == "no_15m_data"
