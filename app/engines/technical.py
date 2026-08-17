from __future__ import annotations

import pandas as pd

from app.core.config import get_settings


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


def _sma(series: pd.Series, period: int) -> float | None:
    if len(series) < period:
        return None
    return round(float(series.rolling(period).mean().iloc[-1]), 2)


def _candle_tags(row: pd.Series, prev: pd.Series | None) -> list[str]:
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
        curr_body = row["close"] - row["open"]
        if prev_body < 0 < curr_body and row["close"] > prev["open"] and row["open"] < prev["close"]:
            tags.append("bullish_engulfing")
        if prev_body > 0 > curr_body and row["close"] < prev["open"] and row["open"] > prev["close"]:
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


def build_snapshot(frame: pd.DataFrame) -> dict:
    settings = get_settings()
    daily = frame.copy()
    weekly = frame.resample("W").agg(
        {"open": "first", "high": "max", "low": "min", "close": "last", "volume": "sum"}
    ).dropna()

    last = daily.iloc[-1]
    prev = daily.iloc[-2] if len(daily) > 1 else None
    rsi = _rsi(daily["close"])
    sma20 = _sma(daily["close"], 20)
    sma50 = _sma(daily["close"], 50)
    sma200 = _sma(daily["close"], 200)

    tags = _candle_tags(last, prev)
    tags.extend(_support_resistance_tags(daily))

    if rsi is not None and rsi <= settings.technical.rsi_oversold:
        tags.append("rsi_oversold")
    if rsi is not None and rsi >= settings.technical.rsi_overbought:
        tags.append("rsi_overbought")
    if sma20 and sma50 and sma20 > sma50:
        tags.append("short_term_uptrend")
    if sma50 and sma200 and sma50 > sma200:
        tags.append("long_term_uptrend")
    if sma20 and last["close"] > sma20:
        tags.append("above_sma20")

    weekly_rsi = _rsi(weekly["close"]) if len(weekly) >= 15 else None
    weekly_tags: list[str] = []
    if weekly_rsi is not None and weekly_rsi <= settings.technical.rsi_oversold:
        weekly_tags.append("weekly_rsi_oversold")
    if len(weekly) >= 10 and weekly["close"].iloc[-1] > weekly["close"].rolling(10).mean().iloc[-1]:
        weekly_tags.append("weekly_uptrend")

    volume_ratio = None
    if len(daily) >= 20:
        avg_vol = daily["volume"].rolling(20).mean().iloc[-1]
        if avg_vol > 0:
            volume_ratio = round(float(daily["volume"].iloc[-1] / avg_vol), 2)
            if volume_ratio >= 1.5:
                tags.append("volume_spike")

    return {
        "date": daily.index[-1].date().isoformat(),
        "close": round(float(last["close"]), 2),
        "rsi_14": rsi,
        "sma_20": sma20,
        "sma_50": sma50,
        "sma_200": sma200,
        "volume_ratio_vs_20d": volume_ratio,
        "tags": sorted(set(tags)),
        "weekly": {
            "rsi_14": weekly_rsi,
            "tags": weekly_tags,
        },
    }


def snapshot_similarity(current: dict, historical: dict) -> float:
    if not historical:
        return 0.0

    score = 0.0
    current_tags = set(current.get("tags", []))
    historical_tags = set(historical.get("tags", []))
    if current_tags or historical_tags:
        union = current_tags | historical_tags
        overlap = current_tags & historical_tags
        score += (len(overlap) / len(union)) * 0.55 if union else 0.0

    current_weekly = set(current.get("weekly", {}).get("tags", []))
    historical_weekly = set(historical.get("weekly", {}).get("tags", []))
    if current_weekly or historical_weekly:
        union = current_weekly | historical_weekly
        overlap = current_weekly & historical_weekly
        score += (len(overlap) / len(union)) * 0.15 if union else 0.0

    for field, weight in (("rsi_14", 0.15), ("sma_20", 0.05), ("sma_50", 0.05)):
        a = current.get(field)
        b = historical.get(field)
        if a is None or b is None or b == 0:
            continue
        diff = abs(a - b)
        if field.startswith("rsi"):
            closeness = max(0.0, 1 - (diff / 30))
        else:
            closeness = max(0.0, 1 - (diff / abs(b)))
        score += closeness * weight

    return min(1.0, score)
