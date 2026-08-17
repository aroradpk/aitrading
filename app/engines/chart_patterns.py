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

