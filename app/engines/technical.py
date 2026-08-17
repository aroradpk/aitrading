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


def _raw_candle_tags(row: pd.Series, prev: pd.Series | None, prev2: pd.Series | None = None) -> list[str]:
    tags: list[str] = []
    body = abs(row["close"] - row["open"])
    upper_wick = row["high"] - max(row["close"], row["open"])
    lower_wick = min(row["close"], row["open"]) - row["low"]
    total_range = row["high"] - row["low"]
    if total_range <= 0:
        return tags

    if lower_wick >= body * 2 and upper_wick <= body * 0.5:
        tags.append("hammer")
    if upper_wick >= body * 2 and lower_wick <= body * 0.5:
        tags.append("inverted_hammer")
        tags.append("shooting_star")
    if body >= total_range * 0.6:
        tags.append("marubozu")
    if prev is not None:
        prev_body = prev["close"] - prev["open"]
        if prev_body < 0 < (row["close"] - row["open"]) and row["close"] > prev["open"] and row["open"] < prev["close"]:
            tags.append("bullish_engulfing")
        if prev_body > 0 > (row["close"] - row["open"]) and row["close"] < prev["open"] and row["open"] > prev["close"]:
            tags.append("bearish_engulfing")
        if prev2 is not None:
            prev2_bear = prev2["close"] < prev2["open"]
            prev_small = abs(prev["close"] - prev["open"]) <= abs(prev2["close"] - prev2["open"]) * 0.5
            row_bull = row["close"] > row["open"]
            if prev2_bear and prev_small and row_bull and row["close"] >= (prev2["open"] + prev2["close"]) / 2:
                tags.append("morning_star")
            prev2_bull = prev2["close"] > prev2["open"]
            row_bear = row["close"] < row["open"]
            if prev2_bull and prev_small and row_bear and row["close"] <= (prev2["open"] + prev2["close"]) / 2:
                tags.append("evening_star")
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
    return tags


def _ema_structure_tags(daily: pd.DataFrame, close: float, ema20: float | None, ema50: float | None, ema200: float | None) -> list[str]:
    """EMA context: support touch, momentum stack/spread, or extended (late entry)."""
    tags: list[str] = []
    if not ema20:
        return tags

    dist_pct = abs(close - ema20) / ema20
    if dist_pct <= 0.02:
        tags.append("ema20_support_touch")
    elif close > ema20 and dist_pct >= 0.05:
        tags.append("ema20_extended_long")
    elif close < ema20 and dist_pct >= 0.05:
        tags.append("ema20_extended_short")

    if ema20 and ema50 and ema200:
        if ema20 > ema50 > ema200:
            tags.append("ema_bull_stack")
        elif ema20 < ema50 < ema200:
            tags.append("ema_bear_stack")

        if len(daily) >= 30:
            e20 = daily["close"].ewm(span=20, adjust=False).mean()
            e50 = daily["close"].ewm(span=50, adjust=False).mean()
            e200 = daily["close"].ewm(span=200, adjust=False).mean()
            spread_20_50_now = (e20.iloc[-1] - e50.iloc[-1]) / e50.iloc[-1]
            spread_20_50_prev = (e20.iloc[-6] - e50.iloc[-6]) / e50.iloc[-6]
            spread_50_200_now = (e50.iloc[-1] - e200.iloc[-1]) / e200.iloc[-1]
            spread_50_200_prev = (e50.iloc[-6] - e200.iloc[-6]) / e200.iloc[-6]
            if ema20 > ema50 > ema200 and spread_20_50_now > spread_20_50_prev and spread_50_200_now > spread_50_200_prev:
                tags.append("ema_momentum_expanding")
            if ema20 < ema50 < ema200 and spread_20_50_now < spread_20_50_prev and spread_50_200_now < spread_50_200_prev:
                tags.append("ema_momentum_expanding_down")

    return tags


LEGACY_TAG_ALIASES = {
    "above_sma20": "ema_bull_stack",
    "below_sma20": "ema_bear_stack",
    "above_ema20": "ema_bull_stack",
    "below_ema20": "ema_bear_stack",
}


def normalize_tags(tags: set[str] | list[str]) -> set[str]:
    normalized: set[str] = set()
    for tag in tags:
        normalized.add(tag)
        if tag in LEGACY_TAG_ALIASES:
            normalized.add(LEGACY_TAG_ALIASES[tag])
    return normalized


LONG_HEADWIND_TAGS = {
    "rsi_overbought",
    "weekly_rsi_overbought",
    "near_resistance",
    "ema20_extended_long",
}
LONG_TAILWIND_TAGS = {
    "ema20_support_touch",
    "ema_momentum_expanding",
    "ema_bull_stack",
    "near_support",
    "rsi_oversold",
}
SHORT_HEADWIND_TAGS = {
    "rsi_oversold",
    "weekly_rsi_oversold",
    "near_support",
    "ema20_extended_short",
    "ema_bull_stack",
}
SHORT_TAILWIND_TAGS = {
    "rsi_overbought",
    "weekly_rsi_overbought",
    "near_resistance",
    "ema_momentum_expanding_down",
    "ema_bear_stack",
    "ema20_extended_long",
}


def _all_snapshot_tags(snapshot: dict) -> set[str]:
    tags = set(snapshot.get("tags", []))
    tags.update(snapshot.get("weekly", {}).get("tags", []))
    return tags


def exhaustion_fade_side(snapshot: dict) -> str | None:
    """Counter-trend fade when stretched at S/R."""
    tags = _all_snapshot_tags(snapshot)
    if ("rsi_overbought" in tags or "weekly_rsi_overbought" in tags) and "near_resistance" in tags:
        return "short"
    if ("rsi_oversold" in tags or "weekly_rsi_oversold" in tags) and "near_support" in tags:
        return "long"
    return None


def technical_reasons_for_side(snapshot: dict, side: str) -> list[dict]:
    """Ordered, side-aware reasons — headwinds flagged for the active position side."""
    tags = _all_snapshot_tags(snapshot)
    reasons: list[dict] = []

    def add(tag: str, *, weight: str, headwind: bool = False) -> None:
        label = tag.replace("_", " ")
        if headwind:
            label = f"{label} (headwind for {side})"
        reasons.append({"layer": "technical", "text": label, "weight": weight, "headwind": headwind})

    priority = [
        ("ema20_support_touch", "high", False),
        ("ema_momentum_expanding", "high", False),
        ("ema_momentum_expanding_down", "high", False),
        ("ema_bull_stack", "medium", False),
        ("ema_bear_stack", "medium", False),
        ("ema20_extended_long", "high", side == "long"),
        ("ema20_extended_short", "high", side == "short"),
        ("near_support", "high", side == "short"),
        ("near_resistance", "high", side == "long"),
        ("rsi_overbought", "high", side == "long"),
        ("rsi_oversold", "high", side == "short"),
        ("weekly_rsi_overbought", "high", side == "long"),
        ("weekly_rsi_oversold", "high", side == "short"),
        ("short_term_uptrend", "medium", False),
        ("short_term_downtrend", "medium", False),
        ("long_term_uptrend", "medium", False),
        ("long_term_downtrend", "medium", False),
    ]
    seen: set[str] = set()
    for tag, weight, headwind in priority:
        if tag in tags and tag not in seen:
            add(tag, weight=weight, headwind=headwind)
            seen.add(tag)

    for tag in sorted(tags):
        if tag in seen:
            continue
        if tag.startswith(("elliott_", "fib_", "formation_")):
            add(tag, weight="high")
            seen.add(tag)
            continue
        if tag.startswith("candle_"):
            add(tag, weight="medium")
            seen.add(tag)
            continue
        add(tag, weight="low", headwind=tag in (LONG_HEADWIND_TAGS if side == "long" else SHORT_HEADWIND_TAGS))
        seen.add(tag)

    return reasons


def position_bias(snapshot: dict, *, focus: str = "long") -> str:
    """Primary trend gate for buy (long) vs sell (short) setups."""
    tags = set(snapshot.get("tags", []))
    weekly_tags = set(snapshot.get("weekly", {}).get("tags", []))
    all_tags = tags | weekly_tags

    fade = exhaustion_fade_side(snapshot)
    at_ema_support = "ema20_support_touch" in all_tags
    in_momentum = "ema_momentum_expanding" in all_tags or "ema_momentum_expanding_down" in all_tags

    if focus == "short" and fade == "short":
        return "short"
    if focus == "long" and fade == "long":
        return "long"

    long_ok = "long_term_uptrend" in all_tags or "short_term_uptrend" in all_tags
    short_ok = "long_term_downtrend" in all_tags or "short_term_downtrend" in all_tags

    if focus == "short":
        return "short" if short_ok or fade == "short" else "neutral"
    if focus == "long":
        extended_exhaustion = (
            fade == "short" and "ema20_extended_long" in all_tags and not at_ema_support
        )
        if extended_exhaustion or (fade == "short" and not at_ema_support and not in_momentum):
            return "neutral"
        return "long" if long_ok else "neutral"
    if long_ok and not short_ok:
        return "long"
    if short_ok and not long_ok:
        return "short"
    return "neutral"


def _confirm_candles(raw_candles: list[str], context_tags: list[str], formations: list[dict]) -> list[str]:
    """Candlesticks only count when combined with formation, S/R, or Fib context."""
    has_context = bool(formations) or any(
        tag.startswith(("near_", "fib_", "elliott_", "ema20_support", "formation_")) for tag in context_tags
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
    prev2 = daily.iloc[-3] if len(daily) > 2 else None
    rsi = _rsi(daily["close"])
    ema20 = _ema(daily["close"], 20)
    ema50 = _ema(daily["close"], 50)
    ema200 = _ema(daily["close"], 200)

    formations = detect_formations(daily)
    sr_tags = _support_resistance_tags(daily)
    fib_tags = fibonacci_tags(daily)
    elliott = elliott_tags(daily)
    trend_tags = _trend_tags(float(last["close"]), ema20, ema50, ema200)
    ema_tags = _ema_structure_tags(daily, float(last["close"]), ema20, ema50, ema200)

    context_tags = sr_tags + fib_tags + elliott + ema_tags + [f"formation_{f['id']}" for f in formations]
    raw_candles = _raw_candle_tags(last, prev, prev2)
    candle_tags = _confirm_candles(raw_candles, context_tags, formations)

    tags: list[str] = []
    tags.extend(trend_tags)
    tags.extend(ema_tags)
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
    current_tags = normalize_tags(current.get("tags", []))
    historical_tags = normalize_tags(historical.get("tags", []))
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
