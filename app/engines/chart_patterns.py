from __future__ import annotations

import json
from functools import lru_cache

import numpy as np
import pandas as pd

from app.core.paths import CONFIG_DIR


@lru_cache
def load_formation_catalog() -> dict:
    path = CONFIG_DIR / "technical" / "chart_formations.json"
    return json.loads(path.read_text(encoding="utf-8"))


def _swing_points(series: pd.Series, order: int = 3) -> list[tuple[int, float, str]]:
    """Local extrema: (index, price, peak|trough)."""
    values = series.values
    points: list[tuple[int, float, str]] = []
    for i in range(order, len(values) - order):
        window = values[i - order : i + order + 1]
        if values[i] == window.max():
            points.append((i, float(values[i]), "peak"))
        elif values[i] == window.min():
            points.append((i, float(values[i]), "trough"))
    return points


def _linreg_slope(indices: list[int], prices: list[float]) -> float:
    if len(indices) < 2:
        return 0.0
    x = np.array(indices, dtype=float)
    y = np.array(prices, dtype=float)
    slope = np.polyfit(x, y, 1)[0]
    return float(slope)


def detect_formations(frame: pd.DataFrame, lookback: int = 40) -> list[dict]:
    if len(frame) < lookback:
        return []

    window = frame.tail(lookback).reset_index(drop=True)
    highs = window["high"]
    lows = window["low"]
    closes = window["close"]
    formations: list[dict] = []

    peaks = [p for p in _swing_points(highs) if p[2] == "peak"][-4:]
    troughs = [p for p in _swing_points(lows) if p[2] == "trough"][-4:]

    if len(peaks) >= 2 and len(troughs) >= 2:
        peak_slope = _linreg_slope([p[0] for p in peaks], [p[1] for p in peaks])
        trough_slope = _linreg_slope([t[0] for t in troughs], [t[1] for t in troughs])
        converging = abs(peak_slope - trough_slope) > 0.01

        if converging and peak_slope > 0 and trough_slope > 0:
            formations.append({"id": "rising_wedge", "name": "Rising wedge", "bias": "bearish_reversal"})
        elif converging and peak_slope < 0 and trough_slope < 0:
            formations.append({"id": "falling_wedge", "name": "Falling wedge", "bias": "bullish_reversal"})
        elif abs(peak_slope) < abs(trough_slope) * 0.35 and trough_slope > 0:
            formations.append({"id": "ascending_triangle", "name": "Ascending triangle", "bias": "bullish_continuation"})
        elif abs(trough_slope) < abs(peak_slope) * 0.35 and peak_slope < 0:
            formations.append({"id": "descending_triangle", "name": "Descending triangle", "bias": "bearish_continuation"})
        elif converging:
            formations.append({"id": "symmetrical_triangle", "name": "Symmetrical triangle", "bias": "neutral_breakout"})

    if len(troughs) >= 2:
        t1, t2 = troughs[-2], troughs[-1]
        if abs(t1[1] - t2[1]) / t1[1] <= 0.02 and t2[0] > t1[0]:
            formations.append({"id": "double_bottom", "name": "Double bottom", "bias": "bullish_reversal"})

    if len(peaks) >= 2:
        p1, p2 = peaks[-2], peaks[-1]
        if abs(p1[1] - p2[1]) / p1[1] <= 0.02 and p2[0] > p1[0]:
            formations.append({"id": "double_top", "name": "Double top", "bias": "bearish_reversal"})

    if len(peaks) >= 3:
        left, head, right = peaks[-3], peaks[-2], peaks[-1]
        if head[1] > left[1] and head[1] > right[1] and abs(left[1] - right[1]) / left[1] <= 0.03:
            formations.append({"id": "head_shoulders", "name": "Head and shoulders", "bias": "bearish_reversal"})

    if len(troughs) >= 3:
        left, head, right = troughs[-3], troughs[-2], troughs[-1]
        if head[1] < left[1] and head[1] < right[1] and abs(left[1] - right[1]) / left[1] <= 0.03:
            formations.append({"id": "inverse_head_shoulders", "name": "Inverse H&S", "bias": "bullish_reversal"})

    if len(window) >= 20:
        pole = closes.iloc[-20:-8]
        flag = closes.iloc[-8:]
        pole_move = float(pole.iloc[-1] - pole.iloc[0])
        flag_range = float(flag.max() - flag.min())
        if pole_move > 0 and flag_range < abs(pole_move) * 0.45 and flag.iloc[-1] < flag.iloc[0]:
            formations.append({"id": "bull_flag", "name": "Bull flag", "bias": "bullish_continuation"})
        if pole_move < 0 and flag_range < abs(pole_move) * 0.45 and flag.iloc[-1] > flag.iloc[0]:
            formations.append({"id": "bear_flag", "name": "Bear flag", "bias": "bearish_continuation"})

    return formations


def detect_compressing_wedge(frame: pd.DataFrame, *, side: str = "long", lookback: int = 25) -> bool:
    """Range narrows with converging trendlines (apex forming)."""
    if len(frame) < lookback:
        return False
    window = frame.tail(lookback).reset_index(drop=True)
    highs = window["high"]
    lows = window["low"]
    peaks = [p for p in _swing_points(highs, order=2) if p[2] == "peak"][-3:]
    troughs = [p for p in _swing_points(lows, order=2) if p[2] == "trough"][-3:]
    if len(peaks) < 2 or len(troughs) < 2:
        return False

    peak_slope = _linreg_slope([p[0] for p in peaks], [p[1] for p in peaks])
    trough_slope = _linreg_slope([t[0] for t in troughs], [t[1] for t in troughs])
    early_span = float(window["high"].iloc[:8].max() - window["low"].iloc[:8].min())
    late_span = float(window["high"].iloc[-8:].max() - window["low"].iloc[-8:].min())
    if early_span <= 0:
        return False
    narrowing = late_span / early_span <= 0.65
    converging = abs(peak_slope - trough_slope) > 0.005

    if side == "long":
        return narrowing and converging and trough_slope >= 0
    return narrowing and converging and peak_slope <= 0


def detect_rounding_bottom(frame: pd.DataFrame, lookback: int = 30) -> bool:
    """Curved bottom: lower lows then higher lows with mid-window trough."""
    if len(frame) < lookback:
        return False
    lows = frame.tail(lookback)["low"].reset_index(drop=True)
    third = lookback // 3
    left_min = float(lows.iloc[:third].min())
    mid_min = float(lows.iloc[third : 2 * third].min())
    right_min = float(lows.iloc[2 * third :].min())
    # trough in middle third, right side lifting
    return mid_min <= left_min * 1.01 and right_min > mid_min * 1.01 and right_min > left_min * 0.985


def fibonacci_tags(frame: pd.DataFrame, lookback: int = 60) -> list[str]:
    if len(frame) < lookback:
        return []
    window = frame.tail(lookback)
    swing_high = float(window["high"].max())
    swing_low = float(window["low"].min())
    span = swing_high - swing_low
    if span <= 0:
        return []
    close = float(window["close"].iloc[-1])
    tags: list[str] = []
    catalog = load_formation_catalog()
    for level in catalog.get("fibonacci_levels", [0.382, 0.5, 0.618]):
        for direction in ("retrace", "ext"):
            if direction == "retrace":
                price = swing_high - span * level
                label = f"fib_{level:.3f}_retrace"
            else:
                price = swing_high + span * (level - 1) if level > 1 else swing_high + span * level
                label = f"fib_{level:.3f}_ext"
            if abs(close - price) / span <= 0.03:
                tags.append(label)
    return tags


SR_FIB_LEVELS = (0.382, 0.5, 0.618)
SR_FIB_LOOKBACKS = (20, 40, 60)


def _price_near(level_price: float, reference: float, atr: float) -> bool:
    if reference <= 0 or level_price <= 0:
        return False
    tol = max(0.01 * reference, 0.35 * atr if atr > 0 else 0.0)
    return abs(reference - level_price) <= tol


def detect_sr_fib_confluence(frame: pd.DataFrame, *, side: str, sr_prices: list[float]) -> bool:
    """True when an S/R price (EMA20 or swing level) sits on a 38.2/50/61.8 retrace."""
    if len(frame) < 25 or not sr_prices:
        return False
    atr = float((frame["high"] - frame["low"]).tail(20).mean())
    refs = [p for p in sr_prices if p and p > 0]
    close = float(frame["close"].iloc[-1])
    for lookback in SR_FIB_LOOKBACKS:
        if len(frame) < lookback:
            continue
        window = frame.tail(lookback)
        swing_high = float(window["high"].max())
        swing_low = float(window["low"].min())
        span = swing_high - swing_low
        if span <= 0:
            continue
        if side == "long":
            targets = [swing_high - span * level for level in SR_FIB_LEVELS]
        else:
            targets = [swing_low + span * level for level in SR_FIB_LEVELS]
        for ref in refs:
            if any(_price_near(target, ref, atr) for target in targets):
                return True
        if any(_price_near(target, close, atr) for target in targets):
            return True
    return False


