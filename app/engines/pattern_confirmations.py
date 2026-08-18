from __future__ import annotations

import pandas as pd

from app.engines.chart_patterns import (
    detect_compressing_wedge,
    detect_formations,
    detect_rounding_bottom,
    detect_sr_fib_confluence,
    fibonacci_tags,
)
from app.engines.elliott import elliott_tags
from app.engines.technical import (
    _ema,
    _ema_structure_tags,
    _rsi,
    _support_resistance_tags,
    _trend_tags,
)


def _body_overlap_with_range(row: pd.Series, low: float, high: float, buffer_pct: float = 0.015) -> bool:
    span = high - low
    if span <= 0:
        return False
    buf = span * buffer_pct
    body_low = min(row["open"], row["close"])
    body_high = max(row["open"], row["close"])
    return body_low >= (low - buf) and body_high <= (high + buf)


def detect_ema20_support(frame: pd.DataFrame, lookback: int = 5, tolerance_pct: float = 0.025) -> bool:
    """Low wick touched EMA20 within recent bars (pullback support)."""
    if len(frame) < 25:
        return False
    daily = frame.tail(lookback + 20)
    for offset in range(lookback):
        sub = daily.iloc[: len(daily) - offset]
        if len(sub) < 20:
            continue
        row = sub.iloc[-1]
        ema20 = _ema(sub["close"], 20)
        if ema20 is None:
            continue
        if abs(row["low"] - ema20) / ema20 <= tolerance_pct:
            return True
        if row["low"] <= ema20 <= row["high"]:
            return True
    return False


def detect_reference_candle_consolidation(
    frame: pd.DataFrame,
    *,
    anchor_offset: int = 3,
    min_days: int = 3,
    min_overlap: float = 0.55,
    buffer_pct: float = 0.02,
) -> bool:
    """Sessions overlap an anchor candle range (e.g. 4-Aug base for 4/5/6-Aug)."""
    if len(frame) < anchor_offset + 1:
        return False
    anchor = frame.iloc[-anchor_offset]
    ref_low = float(anchor["low"])
    ref_high = float(anchor["high"])

    def overlap_fraction(row: pd.Series) -> float:
        span = float(row["high"] - row["low"])
        if span <= 0:
            return 0.0
        buf_low = ref_low * (1 - buffer_pct)
        buf_high = ref_high * (1 + buffer_pct)
        overlap = max(0.0, min(row["high"], buf_high) - max(row["low"], buf_low))
        return overlap / span

    recent = frame.iloc[-min_days:]
    if len(recent) < min_days:
        return False
    return all(overlap_fraction(row) >= min_overlap for _, row in recent.iterrows())


def detect_rsi_60_reclaim(frame: pd.DataFrame, lookback: int = 8) -> bool:
    """RSI held near 60 support zone then reclaimed / held above 60."""
    if len(frame) < lookback + 15:
        return False
    series = frame["close"]
    values: list[float] = []
    for i in range(lookback):
        sub = series.iloc[: len(series) - (lookback - 1 - i)]
        val = _rsi(sub)
        if val is not None:
            values.append(val)
    if len(values) < 3:
        return False
    current = values[-1]
    prior = values[:-1]
    touched_support = any(58 <= v <= 66 for v in prior)
    reclaimed = current >= 60 and current >= min(prior[-3:]) 
    return touched_support and reclaimed and current > prior[-2]


def detect_energy_triggers(frame: pd.DataFrame) -> dict[str, bool]:
    """Setup rumble vs late 5% bar. A 7 is the rumble (wide range, close not yet ±5%)."""
    empty = {
        "vol_expansion": False,
        "range_expansion": False,
        "setup_rattle": False,
        "late_bar": False,
        "strong_close": False,
        "dead_volume": False,
        "live_rvol": False,
    }
    if len(frame) < 25:
        return empty
    close = float(frame["close"].iloc[-1])
    low = float(frame["low"].iloc[-1])
    high = float(frame["high"].iloc[-1])
    span = high - low
    loc = (close - low) / span if span > 0 else 0.5
    vol = frame["volume"]
    vol_mean = float(vol.tail(20).mean())
    vr = float(vol.iloc[-1] / vol_mean) if vol_mean else 1.0
    atr = float((frame["high"] - frame["low"]).tail(20).mean())
    prev = float(frame["close"].iloc[-2])
    day_pct = abs(close / prev - 1.0) * 100 if prev else 0.0
    range_pct = (span / prev) * 100 if prev else 0.0
    return {
        "vol_expansion": vr >= 2.0,
        "range_expansion": atr > 0 and span >= 1.6 * atr,
        "setup_rattle": range_pct >= 2.5 and day_pct < 5.0,
        "late_bar": day_pct >= 5.0,
        "strong_close": loc >= 0.7,
        "dead_volume": vr <= 0.85,
        "live_rvol": vr >= 1.5,
    }


def detect_tight_range(frame: pd.DataFrame, lookback: int = 5) -> bool:
    """Recent range is compressed vs 20-bar ATR (coil)."""
    if len(frame) < lookback + 20:
        return False
    recent = frame.tail(lookback)
    span = float(recent["high"].max() - recent["low"].min())
    atr = float((frame["high"] - frame["low"]).tail(20).mean())
    return atr > 0 and span / atr <= 2.8


def detect_higher_lows(frame: pd.DataFrame, bars: int = 3) -> bool:
    if len(frame) < bars:
        return False
    lows = frame["low"].tail(bars).tolist()
    return all(lows[i] >= lows[i - 1] * 0.998 for i in range(1, bars))


def detect_lower_highs(frame: pd.DataFrame, bars: int = 3) -> bool:
    if len(frame) < bars:
        return False
    highs = frame["high"].tail(bars).tolist()
    return all(highs[i] <= highs[i - 1] * 1.002 for i in range(1, bars))


def detect_close_above_ema20(frame: pd.DataFrame) -> bool:
    if len(frame) < 20:
        return False
    ema20 = _ema(frame["close"], 20)
    if ema20 is None:
        return False
    return float(frame["close"].iloc[-1]) > ema20


def detect_rsi_trend_long(frame: pd.DataFrame) -> bool:
    rsi = _rsi(frame["close"])
    return rsi is not None and rsi >= 50


def detect_rsi_trend_short(frame: pd.DataFrame) -> bool:
    rsi = _rsi(frame["close"])
    return rsi is not None and rsi <= 50


def detect_daily_confirmations(frame: pd.DataFrame, side: str) -> dict[str, bool]:
    if len(frame) < 30:
        return {}

    close = float(frame["close"].iloc[-1])
    ema20 = _ema(frame["close"], 20)
    ema50 = _ema(frame["close"], 50)
    ema200 = _ema(frame["close"], 200)
    ema_tags = set(_ema_structure_tags(frame, close, ema20, ema50, ema200))
    trend_tags = set(_trend_tags(close, ema20, ema50, ema200))
    formations = {f["id"] for f in detect_formations(frame)}

    bullish_formations = {
        "falling_wedge",
        "ascending_triangle",
        "symmetrical_triangle",
        "double_bottom",
        "inverse_head_shoulders",
        "bull_flag",
        "compressing_wedge_bull",
        "rounding_bottom",
    }
    bearish_formations = {
        "rising_wedge",
        "descending_triangle",
        "double_top",
        "head_shoulders",
        "bear_flag",
        "compressing_wedge_bear",
    }

    energy = detect_energy_triggers(frame)
    sr_tags = set(_support_resistance_tags(frame))
    fibs = fibonacci_tags(frame)
    ell = set(elliott_tags(frame))
    ema20_support = detect_ema20_support(frame)
    ema20_resistance = ema20 is not None and close < ema20 and abs(close - ema20) / ema20 <= 0.03
    long_sr = "near_support" in sr_tags or ema20_support or "ema20_support_touch" in ema_tags
    short_sr = "near_resistance" in sr_tags or ema20_resistance
    recent = frame.tail(25)
    support = float(recent["low"].min())
    resistance = float(recent["high"].max())
    long_sr_prices = [p for p in (ema20, support if long_sr else None) if p]
    short_sr_prices = [p for p in (ema20, resistance if short_sr else None) if p]
    long_sr_fib = long_sr and detect_sr_fib_confluence(frame, side="long", sr_prices=long_sr_prices)
    short_sr_fib = short_sr and detect_sr_fib_confluence(frame, side="short", sr_prices=short_sr_prices)
    long_elliott = "elliott_impulse_up" in ell or "elliott_abc_corrective_down" in ell
    short_elliott = "elliott_impulse_down" in ell or "elliott_abc_corrective_up" in ell
    long_elliott_conflict = "elliott_impulse_down" in ell and "elliott_impulse_up" not in ell
    short_elliott_conflict = "elliott_impulse_up" in ell and "elliott_impulse_down" not in ell

    long_map = {
        "ema20_support": ema20_support,
        "consolidation_anchor": detect_reference_candle_consolidation(frame),
        "tight_range": detect_tight_range(frame),
        "higher_lows": detect_higher_lows(frame),
        "close_above_ema20": detect_close_above_ema20(frame),
        "ema_momentum_expanding": "ema_momentum_expanding" in ema_tags,
        "ema_bull_stack": "ema_bull_stack" in ema_tags,
        "rsi_60_reclaim": detect_rsi_60_reclaim(frame),
        "rsi_trend_long": detect_rsi_trend_long(frame),
        "uptrend": bool(trend_tags & {"short_term_uptrend", "long_term_uptrend"}),
        "bullish_formation": bool(formations & bullish_formations),
        "compressing_wedge": detect_compressing_wedge(frame, side="long"),
        "rounding_bottom": detect_rounding_bottom(frame),
        "sr_level": long_sr,
        "fib_level": bool(fibs),
        "sr_fib_confluence": long_sr_fib,
        "elliott_aligned": long_elliott,
        "elliott_conflict": long_elliott_conflict,
        **energy,
    }
    short_map = {
        "ema20_resistance": ema20_resistance,
        "close_below_ema20": ema20 is not None and close < ema20,
        "consolidation_anchor": detect_reference_candle_consolidation(frame),
        "tight_range": detect_tight_range(frame),
        "lower_highs": detect_lower_highs(frame),
        "ema_momentum_expanding_down": "ema_momentum_expanding_down" in ema_tags,
        "ema_bear_stack": "ema_bear_stack" in ema_tags,
        "rsi_60_reject": detect_rsi_60_reclaim(frame) is False and (_rsi(frame["close"]) or 0) >= 65,
        "rsi_trend_short": detect_rsi_trend_short(frame),
        "downtrend": bool(trend_tags & {"short_term_downtrend", "long_term_downtrend"}),
        "bearish_formation": bool(formations & bearish_formations),
        "compressing_wedge": detect_compressing_wedge(frame, side="short"),
        "sr_level": short_sr,
        "fib_level": bool(fibs),
        "sr_fib_confluence": short_sr_fib,
        "elliott_aligned": short_elliott,
        "elliott_conflict": short_elliott_conflict,
        **energy,
    }
    return long_map if side == "long" else short_map


def confirmation_labels(confirmations: dict[str, bool]) -> list[str]:
    labels = {
        "ema20_support": "EMA20 support (low touch)",
        "ema20_resistance": "EMA20 resistance rejection",
        "consolidation_anchor": "Consolidation in anchor candle range",
        "ema_momentum_expanding": "EMA gaps expanding (momentum)",
        "ema_momentum_expanding_down": "EMA gaps expanding down",
        "ema_bull_stack": "EMA bull stack (20>50>200)",
        "ema_bear_stack": "EMA bear stack",
        "rsi_60_reclaim": "RSI reclaimed above 60 from ~60 zone",
        "rsi_60_reject": "RSI rejected from overbought",
        "uptrend": "Trend alignment up",
        "downtrend": "Trend alignment down",
        "bullish_formation": "Bullish chart formation",
        "bearish_formation": "Bearish chart formation",
        "compressing_wedge": "Compressing wedge",
        "rounding_bottom": "Rounding bottom",
        "tight_range": "Tight coil vs ATR",
        "higher_lows": "Rising lows",
        "lower_highs": "Falling highs",
        "close_above_ema20": "Close above EMA20",
        "close_below_ema20": "Close below EMA20",
        "rsi_trend_long": "RSI holding above 50",
        "rsi_trend_short": "RSI holding below 50",
        "vol_expansion": "Volume >= 2.0x 20d avg (breakout bar)",
        "range_expansion": "Day range >= 1.6x ATR (late expansion bar)",
        "setup_rattle": "Setup rumble: range >= 2.5% of price, close not yet ±5%",
        "late_bar": "Late 5% bar — already printed, not a 7",
        "strong_close": "Close in top 30% of day range",
        "dead_volume": "Dead volume coil (<=0.85x 20d avg)",
        "live_rvol": "Volume >= 1.5x 20d avg",
        "mtf_15m_wedge": "15m compressing wedge",
        "mtf_15m_coil_ema": "15m coil at EMA20",
        "mtf_15m_base": "15m base at EMA20 (coil / flag / range / wedge / rising — name does not matter)",
        "mtf_1h_rounding_ema20": "1h rounding bottom at EMA20",
        "mtf_1h_coil_ema": "1h coil at EMA20",
        "mtf_1h_base": "1h base at EMA20 (coil / flag / range / rounding / rising — name does not matter)",
        "mtf_1h_fib_sr": "Hourly S/R with Fibonacci (0.382/0.5/0.618)",
        "sr_level": "Support/resistance level",
        "fib_level": "Fibonacci retrace/extension",
        "sr_fib_confluence": "S/R with Fibonacci confluence",
        "elliott_aligned": "Elliott wave aligned",
        "elliott_conflict": "Elliott wave against this side",
    }
    return [labels[key] for key, active in confirmations.items() if active and key in labels]


def is_breakout_base(confirmations: dict[str, bool]) -> bool:
    """Pullback + base before expansion — do not fade as exhaustion."""
    return bool(
        confirmations.get("ema20_support")
        and confirmations.get("consolidation_anchor")
        and confirmations.get("ema_momentum_expanding")
    )


def is_coil_setup(confirmations: dict[str, bool]) -> bool:
    """Rangebound base — the setup that precedes the breakout (dead volume is typical, not required)."""
    return bool(confirmations.get("tight_range") or confirmations.get("consolidation_anchor"))
