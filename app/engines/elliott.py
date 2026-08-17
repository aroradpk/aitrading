from __future__ import annotations

from functools import lru_cache

import pandas as pd

from app.engines.chart_patterns import _swing_points, load_formation_catalog


@lru_cache
def load_elliott_rules() -> dict:
    catalog = load_formation_catalog()
    defaults = {
        "swing_order": 2,
        "lookback": 50,
        "impulse_points": 6,
        "wave2_min_retrace": 0.236,
        "wave2_max_retrace": 0.786,
        "wave4_overlap_tolerance_pct": 0.01,
        "abc_min_retrace": 0.382,
        "abc_max_retrace": 0.786,
        "abc_min_c_to_a": 0.618,
        "require_trend_alignment": True,
        "min_leg_pct": 0.015,
    }
    defaults.update(catalog.get("elliott", {}))
    return defaults


def _alternating(swings: list[tuple[int, float, str]]) -> bool:
    if len(swings) < 2:
        return False
    for idx in range(1, len(swings)):
        if swings[idx][2] == swings[idx - 1][2]:
            return False
    return True


def _trend_tags_from_frame(frame: pd.DataFrame) -> set[str]:
    if len(frame) < 50:
        return set()
    from app.engines.technical import _ema, _trend_tags

    last_close = float(frame["close"].iloc[-1])
    ema20 = _ema(frame["close"], 20)
    ema50 = _ema(frame["close"], 50)
    ema200 = _ema(frame["close"], 200)
    return set(_trend_tags(last_close, ema20, ema50, ema200))


def _validate_impulse_up(swings: list[tuple[int, float, str]], rules: dict) -> bool:
    points = rules["impulse_points"]
    if len(swings) < points:
        return False
    segment = swings[-points:]
    if not _alternating(segment) or segment[0][2] != "trough" or segment[-1][2] != "peak":
        return False

    t0, p1, t2, p3, t4, p5 = [point[1] for point in segment]
    w1 = p1 - t0
    w2 = p1 - t2
    w3 = p3 - t2
    w4 = p3 - t4
    w5 = p5 - t4
    if min(w1, w3, w5) <= 0 or w2 <= 0 or w4 <= 0:
        return False

    min_leg = rules.get("min_leg_pct", 0.015)
    if w1 / t0 < min_leg or w3 / t0 < min_leg or w5 / t0 < min_leg:
        return False

    retrace = w2 / w1
    if retrace < rules["wave2_min_retrace"] or retrace > rules["wave2_max_retrace"]:
        return False
    if w3 <= min(w1, w5):
        return False

    overlap_floor = p1 * (1 - rules["wave4_overlap_tolerance_pct"])
    if t4 <= overlap_floor:
        return False
    return True


def _validate_impulse_down(swings: list[tuple[int, float, str]], rules: dict) -> bool:
    points = rules["impulse_points"]
    if len(swings) < points:
        return False
    segment = swings[-points:]
    if not _alternating(segment) or segment[0][2] != "peak" or segment[-1][2] != "trough":
        return False

    p0, t1, p2, t3, p4, t5 = [point[1] for point in segment]
    w1 = p0 - t1
    w2 = p2 - t1
    w3 = p2 - t3
    w4 = p4 - t3
    w5 = p4 - t5
    if min(w1, w3, w5) <= 0 or w2 <= 0 or w4 <= 0:
        return False

    min_leg = rules.get("min_leg_pct", 0.015)
    if w1 / p0 < min_leg or w3 / p0 < min_leg or w5 / p0 < min_leg:
        return False

    retrace = w2 / w1
    if retrace < rules["wave2_min_retrace"] or retrace > rules["wave2_max_retrace"]:
        return False
    if w3 <= min(w1, w5):
        return False

    overlap_ceiling = t1 * (1 + rules["wave4_overlap_tolerance_pct"])
    if p4 >= overlap_ceiling:
        return False
    return True


def _validate_abc_down(swings: list[tuple[int, float, str]], rules: dict) -> bool:
    """Bearish A-B-C correction (pullback in uptrend): peak → trough → peak → trough."""
    if len(swings) < 4:
        return False
    segment = swings[-4:]
    if not _alternating(segment) or segment[0][2] != "peak" or segment[-1][2] != "trough":
        return False

    p0, t1, p2, t2 = [point[1] for point in segment]
    leg_a = p0 - t1
    leg_b = p2 - t1
    leg_c = p2 - t2
    if leg_a <= 0 or leg_b <= 0 or leg_c <= 0:
        return False

    b_retrace = leg_b / leg_a
    if b_retrace < rules["abc_min_retrace"] or b_retrace > rules["abc_max_retrace"]:
        return False
    if leg_c < leg_a * rules["abc_min_c_to_a"]:
        return False
    return True


def _validate_abc_up(swings: list[tuple[int, float, str]], rules: dict) -> bool:
    """Bullish A-B-C correction (bounce in downtrend): trough → peak → trough → peak."""
    if len(swings) < 4:
        return False
    segment = swings[-4:]
    if not _alternating(segment) or segment[0][2] != "trough" or segment[-1][2] != "peak":
        return False

    t0, p1, t2, p2 = [point[1] for point in segment]
    leg_a = p1 - t0
    leg_b = p1 - t2
    leg_c = p2 - t2
    if leg_a <= 0 or leg_b <= 0 or leg_c <= 0:
        return False

    b_retrace = leg_b / leg_a
    if b_retrace < rules["abc_min_retrace"] or b_retrace > rules["abc_max_retrace"]:
        return False
    if leg_c < leg_a * rules["abc_min_c_to_a"]:
        return False
    return True


def analyze_elliott(frame: pd.DataFrame, lookback: int | None = None) -> dict:
    rules = load_elliott_rules()
    lookback = lookback or rules["lookback"]
    if len(frame) < lookback:
        return {"tags": [], "swing_count": 0}

    closes = frame.tail(lookback)["close"]
    swings = _swing_points(closes, order=rules["swing_order"])
    trends = _trend_tags_from_frame(frame)
    tags: list[str] = []

    uptrend = "long_term_uptrend" in trends or "short_term_uptrend" in trends
    downtrend = "long_term_downtrend" in trends or "short_term_downtrend" in trends
    require_trend = rules["require_trend_alignment"]

    if _validate_impulse_up(swings, rules):
        if not require_trend or uptrend:
            tags.append("elliott_impulse_up")
    if _validate_impulse_down(swings, rules):
        if not require_trend or downtrend:
            tags.append("elliott_impulse_down")
    if _validate_abc_down(swings, rules):
        if not require_trend or uptrend:
            tags.append("elliott_abc_corrective_down")
    if _validate_abc_up(swings, rules):
        if not require_trend or downtrend:
            tags.append("elliott_abc_corrective_up")

    return {
        "tags": tags,
        "swing_count": len(swings),
        "trend_context": sorted(trends),
    }


def elliott_tags(frame: pd.DataFrame, lookback: int | None = None) -> list[str]:
    return analyze_elliott(frame, lookback=lookback)["tags"]
