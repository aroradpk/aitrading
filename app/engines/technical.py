from __future__ import annotations

import pandas as pd

from app.core.config import get_settings
from app.engines.chart_patterns import detect_formations, fibonacci_tags
from app.engines.elliott import elliott_tags


def _rsi(series: pd.Series, period: int = 14) -> float | None:
    if len(series) < period + 1:
        return None
    delta = series.diff()
    gain = delta.clip(lower=0).rolling(period).mean()
    loss = -delta.clip(upper=0).rolling(period).mean()
    last_gain = gain.iloc[-1]
    last_loss = loss.iloc[-1]
    if last_loss == 0:
        return 100.0
    rs = last_gain / last_loss
    return round(float(100 - (100 / (1 + rs))), 2)


def _ema(series: pd.Series, period: int) -> float | None:
    if len(series) < period:
        return None
    return round(float(series.ewm(span=period, adjust=False).mean().iloc[-1]), 2)


def _raw_candle_tags(row: pd.Series, prev: pd.Series | None) -> list[str]:
    tags: list[str] = []
    body = abs(row["close"] - row["open"])
    upper_wick = row["high"] - max(row["close"], row["open"])
    lower_wick = min(row["close"], row["open"]) - row["low"]
    total_range = row["high"] - row["low"]
    if total_range <= 0:
        return tags

    if lower_wick >= body * 2 and upper_wick <= body * 0.5:
        tags.append("hammer")
    if body >= total_range * 0.6:
        tags.append("marubozu")
    if prev is not None:
        prev_body = prev["close"] - prev["open"]
        if prev_body < 0 < (row["close"] - row["open"]) and row["close"] > prev["open"] and row["open"] < prev["close"]:
            tags.append("bullish_engulfing")
        if prev_body > 0 > (row["close"] - row["open"]) and row["close"] < prev["open"] and row["open"] > prev["close"]:
            tags.append("bearish_engulfing")
    return tags


def _support_resistance_tags(frame: pd.DataFrame) -> list[str]:
    tags: list[str] = []
    if len(frame) < 25:
        return tags
    recent = frame.tail(25)
    close = recent["close"].iloc[-1]
    support = recent["low"].min()
    resistance = recent["high"].max()
    span = resistance - support
    if span <= 0:
        return tags
    if abs(close - support) / span <= 0.12:
        tags.append("near_support")
    if abs(close - resistance) / span <= 0.12:
        tags.append("near_resistance")
    return tags


def _trend_tags(close: float, ema20: float | None, ema50: float | None, ema200: float | None) -> list[str]:
    tags: list[str] = []
    if ema20 and ema50 and ema20 > ema50:
        tags.append("short_term_uptrend")
    elif ema20 and ema50 and ema20 < ema50:
        tags.append("short_term_downtrend")
    if ema50 and ema200 and ema50 > ema200:
        tags.append("long_term_uptrend")
    elif ema50 and ema200 and ema50 < ema200:
        tags.append("long_term_downtrend")
    if ema20 and close > ema20:
        tags.append("above_ema20")
    elif ema20 and close < ema20:
        tags.append("below_ema20")
    return tags


def position_bias(snapshot: dict, *, focus: str = "long") -> str:
    """Primary trend gate for buy (long) vs sell (short) setups."""
    tags = set(snapshot.get("tags", []))
    weekly_tags = set(snapshot.get("weekly", {}).get("tags", []))
    all_tags = tags | weekly_tags

    long_ok = "long_term_uptrend" in all_tags or "short_term_uptrend" in all_tags
    short_ok = "long_term_downtrend" in all_tags or "short_term_downtrend" in all_tags

    if focus == "short":
        return "short" if short_ok else "neutral"
    if focus == "long":
        return "long" if long_ok else "neutral"
    if long_ok and not short_ok:
        return "long"
    if short_ok and not long_ok:
        return "short"
    return "neutral"


def _confirm_candles(raw_candles: list[str], context_tags: list[str], formations: list[dict]) -> list[str]:
    """Candlesticks only count when combined with formation, S/R, or Fib context."""
    has_context = bool(formations) or any(
        tag.startswith(("near_", "fib_")) or tag.startswith("elliott_") for tag in context_tags
    )
    if not has_context:
        return []
    return [f"candle_{tag}" for tag in raw_candles]


def build_snapshot(frame: pd.DataFrame, *, focus: str | None = None) -> dict:
    settings = get_settings()
    focus = focus or settings.technical.position_focus
    if focus == "both":
        focus = "long"
    daily = frame.copy()
    weekly = frame.resample("W").agg(
        {"open": "first", "high": "max", "low": "min", "close": "last", "volume": "sum"}
    ).dropna()

    last = daily.iloc[-1]
    prev = daily.iloc[-2] if len(daily) > 1 else None
    rsi = _rsi(daily["close"])
    ema20 = _ema(daily["close"], 20)
    ema50 = _ema(daily["close"], 50)
    ema200 = _ema(daily["close"], 200)

    formations = detect_formations(daily)
    sr_tags = _support_resistance_tags(daily)
    fib_tags = fibonacci_tags(daily)
    elliott = elliott_tags(daily)
    trend_tags = _trend_tags(float(last["close"]), ema20, ema50, ema200)

    context_tags = sr_tags + fib_tags + elliott + [f"formation_{f['id']}" for f in formations]
    raw_candles = _raw_candle_tags(last, prev)
    candle_tags = _confirm_candles(raw_candles, context_tags, formations)

    tags: list[str] = []
    tags.extend(trend_tags)
    tags.extend(sr_tags)
    tags.extend(fib_tags)
    tags.extend(elliott)
    tags.extend(candle_tags)
    tags.extend(f"formation_{f['id']}" for f in formations)

    if rsi is not None and rsi <= settings.technical.rsi_oversold:
        tags.append("rsi_oversold")
    if rsi is not None and rsi >= settings.technical.rsi_overbought:
        tags.append("rsi_overbought")

    weekly_rsi = _rsi(weekly["close"]) if len(weekly) >= 15 else None
    weekly_ema20 = _ema(weekly["close"], 20) if len(weekly) >= 20 else None
    weekly_tags: list[str] = []
    if weekly_rsi is not None and weekly_rsi <= settings.technical.rsi_oversold:
        weekly_tags.append("weekly_rsi_oversold")
    if weekly_rsi is not None and weekly_rsi >= settings.technical.rsi_overbought:
        weekly_tags.append("weekly_rsi_overbought")
    if weekly_ema20 and len(weekly) >= 10:
        if weekly["close"].iloc[-1] > weekly_ema20:
            weekly_tags.append("weekly_uptrend")
        elif weekly["close"].iloc[-1] < weekly_ema20:
            weekly_tags.append("weekly_downtrend")

    snapshot = {
        "date": daily.index[-1].date().isoformat(),
        "close": round(float(last["close"]), 2),
        "rsi_14": rsi,
        "ema_20": ema20,
        "ema_50": ema50,
        "ema_200": ema200,
        "tags": sorted(set(tags)),
        "formations": formations,
        "raw_candle_patterns": raw_candles,
        "weekly": {
            "rsi_14": weekly_rsi,
            "ema_20": weekly_ema20,
            "tags": weekly_tags,
        },
    }
    snapshot["position_bias"] = position_bias(snapshot, focus=focus)
    snapshot["position_bias_long"] = position_bias(snapshot, focus="long")
    snapshot["position_bias_short"] = position_bias(snapshot, focus="short")
    return snapshot


def _field(snapshot: dict, *keys: str) -> float | None:
    for key in keys:
        value = snapshot.get(key)
        if value is not None:
            return value
    return None


def snapshot_similarity(current: dict, historical: dict) -> float:
    if not historical:
        return 0.0

    score = 0.0
    current_tags = set(current.get("tags", []))
    historical_tags = set(historical.get("tags", []))
    if current_tags or historical_tags:
        union = current_tags | historical_tags
        overlap = current_tags & historical_tags
        score += (len(overlap) / len(union)) * 0.50 if union else 0.0

    current_formations = {f.get("id") for f in current.get("formations", [])}
    historical_formations = {f.get("id") for f in historical.get("formations", [])}
    if current_formations or historical_formations:
        union = current_formations | historical_formations
        overlap = current_formations & historical_formations
        score += (len(overlap) / len(union)) * 0.15 if union else 0.0

    current_weekly = set(current.get("weekly", {}).get("tags", []))
    historical_weekly = set(historical.get("weekly", {}).get("tags", []))
    if current_weekly or historical_weekly:
        union = current_weekly | historical_weekly
        overlap = current_weekly & historical_weekly
        score += (len(overlap) / len(union)) * 0.10 if union else 0.0

    if current.get("position_bias") == historical.get("position_bias") and current.get("position_bias") in {
        "long",
        "short",
    }:
        score += 0.10

    for field, weight in (("rsi_14", 0.10), ("ema_20", 0.05), ("ema_50", 0.05), ("sma_20", 0.05), ("sma_50", 0.05)):
        a = _field(current, field)
        b = _field(historical, field)
        if a is None or b is None or b == 0:
            continue
        diff = abs(a - b)
        if field.startswith("rsi"):
            closeness = max(0.0, 1 - (diff / 30))
        else:
            closeness = max(0.0, 1 - (diff / abs(b)))
        score += closeness * weight

    return min(1.0, score)
