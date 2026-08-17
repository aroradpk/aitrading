from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

from app.core.config import get_settings
from app.core.paths import moves_dir, technical_snapshots_dir
from app.engines.chart_patterns import load_formation_catalog
from app.engines.technical import (
    LONG_HEADWIND_TAGS,
    LONG_TAILWIND_TAGS,
    SHORT_HEADWIND_TAGS,
    SHORT_TAILWIND_TAGS,
    build_snapshot,
    exhaustion_fade_side,
    position_bias,
    snapshot_similarity,
)


def _formation_alignment(formations: list[dict], side: str) -> str:
    bias = load_formation_catalog().get("formation_bias", {})
    ids = {formation.get("id") for formation in formations}
    bullish = set(bias.get("bullish", []))
    bearish = set(bias.get("bearish", []))
    if side == "long":
        if ids & bearish:
            return "conflict"
        if ids & bullish:
            return "support"
    elif side == "short":
        if ids & bullish:
            return "conflict"
        if ids & bearish:
            return "support"
    return "neutral"


def _elliott_alignment(tags: set[str], side: str) -> str:
    if side == "long":
        if "elliott_impulse_down" in tags and "elliott_impulse_up" not in tags:
            return "conflict"
        if "elliott_impulse_up" in tags or "elliott_abc_corrective_down" in tags:
            return "support"
    elif side == "short":
        if "elliott_impulse_up" in tags and "elliott_impulse_down" not in tags:
            return "conflict"
        if "elliott_impulse_down" in tags or "elliott_abc_corrective_up" in tags:
            return "support"
    return "neutral"


def _side_context_adjustment(snapshot: dict, side: str) -> float:
    """Penalize long at resistance/overbought; reward fade shorts and EMA support entries."""
    tags = set(snapshot.get("tags", []))
    weekly = set(snapshot.get("weekly", {}).get("tags", []))
    all_tags = tags | weekly
    adjustment = 0.0

    if side == "long":
        adjustment += 1.0 * len(all_tags & LONG_TAILWIND_TAGS)
        adjustment -= 1.25 * len(all_tags & LONG_HEADWIND_TAGS)
        if "rsi_overbought" in all_tags and "near_resistance" in all_tags:
            adjustment -= 2.5
        if "ema20_extended_long" in all_tags and "near_resistance" in all_tags:
            adjustment -= 1.5
    elif side == "short":
        adjustment += 1.0 * len(all_tags & SHORT_TAILWIND_TAGS)
        adjustment -= 1.25 * len(all_tags & SHORT_HEADWIND_TAGS)
        if exhaustion_fade_side(snapshot) == "short":
            adjustment += 2.0

    return adjustment


def _apply_side_context_caps(technical_score: float, snapshot: dict, side: str) -> float:
    tags = set(snapshot.get("tags", []))
    weekly = set(snapshot.get("weekly", {}).get("tags", []))
    all_tags = tags | weekly

    if side == "long":
        if ("rsi_overbought" in all_tags or "weekly_rsi_overbought" in all_tags) and "near_resistance" in all_tags:
            if "ema20_extended_long" in all_tags or "ema20_support_touch" not in all_tags:
                technical_score = min(technical_score, 3.5)
        if exhaustion_fade_side(snapshot) == "short" and "ema20_support_touch" not in all_tags:
            technical_score = min(technical_score, 3.0)
    elif side == "short" and exhaustion_fade_side(snapshot) == "short":
        technical_score = max(technical_score, 4.5)

    return round(min(10.0, max(0.0, technical_score)), 1)


def _pct_change(series: pd.Series, periods: int) -> pd.Series:
    return series.pct_change(periods=periods) * 100


def detect_moves(frame: pd.DataFrame, *, instrument_type: str) -> list[dict]:
    settings = get_settings()
    thresholds = settings.thresholds
    one_day = _pct_change(frame["close"], 1)
    one_week = _pct_change(frame["close"], 5)
    volume_ratio = frame["volume"] / frame["volume"].rolling(20).mean()

    moves: list[dict] = []
    symbol = str(frame["symbol"].iloc[-1])

    for idx in frame.index[30:]:
        move_1d = one_day.loc[idx]
        move_1w = one_week.loc[idx]
        if pd.isna(move_1d):
            continue

        if instrument_type == "index":
            triggered = abs(move_1d) >= thresholds.index_1d_pct
            trigger_type = "index_1d"
            threshold = thresholds.index_1d_pct
        else:
            triggered = abs(move_1d) >= thresholds.stock_1d_pct or (
                not pd.isna(move_1w) and abs(move_1w) >= thresholds.stock_1w_pct
            )
            trigger_type = "stock_1d" if abs(move_1d) >= thresholds.stock_1d_pct else "stock_1w"
            threshold = (
                thresholds.stock_1d_pct
                if trigger_type == "stock_1d"
                else thresholds.stock_1w_pct
            )

        if not triggered:
            continue

        direction = "up" if (move_1d if trigger_type != "stock_1w" else move_1w) > 0 else "down"
        snapshot = build_snapshot(frame.loc[:idx])

        move = {
            "symbol": symbol,
            "date": idx.date().isoformat(),
            "instrument_type": instrument_type,
            "trigger_type": trigger_type,
            "threshold_pct": threshold,
            "move_1d_pct": round(float(move_1d), 2),
            "move_1w_pct": round(float(move_1w), 2) if not pd.isna(move_1w) else None,
            "direction": direction,
            "close": round(float(frame.loc[idx, "close"]), 2),
            "volume_ratio_vs_20d": round(float(volume_ratio.loc[idx]), 2)
            if not pd.isna(volume_ratio.loc[idx])
            else None,
            "technical_snapshot": snapshot,
        }
        moves.append(move)

    return moves


def save_moves(symbol: str, moves: list[dict], *, frame: pd.DataFrame | None = None) -> Path:
    from app.core.config import get_settings
    from app.engines.chart_render import render_charts_for_moves

    settings = get_settings()
    if frame is not None and settings.charts.enabled:
        render_charts_for_moves(symbol, frame, moves)

    symbol_dir = moves_dir() / symbol
    symbol_dir.mkdir(parents=True, exist_ok=True)
    for move in moves:
        path = symbol_dir / f"{move['date']}.json"
        path.write_text(json.dumps(move, indent=2), encoding="utf-8")
        snapshot_path = technical_snapshots_dir() / symbol / f"{move['date']}.json"
        snapshot_path.parent.mkdir(parents=True, exist_ok=True)
        snapshot_path.write_text(json.dumps(move["technical_snapshot"], indent=2), encoding="utf-8")
    summary_path = symbol_dir / "_summary.json"
    summary_path.write_text(
        json.dumps({"symbol": symbol, "count": len(moves), "moves": moves}, indent=2),
        encoding="utf-8",
    )
    return symbol_dir


def load_moves(symbol: str | None = None) -> list[dict]:
    root = moves_dir()
    if symbol:
        summary = root / symbol / "_summary.json"
        if summary.exists():
            return json.loads(summary.read_text(encoding="utf-8")).get("moves", [])
        return []

    all_moves: list[dict] = []
    for summary in root.glob("*/_summary.json"):
        all_moves.extend(json.loads(summary.read_text(encoding="utf-8")).get("moves", []))
    all_moves.sort(key=lambda item: item["date"], reverse=True)
    return all_moves


def scan_today_setup(
    frame: pd.DataFrame,
    historical_moves: list[dict],
    *,
    side: str | None = None,
    intraday: bool = False,
) -> dict:
    settings = get_settings()
    side = side or settings.technical.position_focus
    if side == "both":
        side = "long"

    match_direction = "up" if side == "long" else "down"
    current = build_snapshot(frame, focus=side)
    comparisons: list[dict] = []
    intraday_threshold = settings.technical.intraday.stock_target_1d_pct

    for move in historical_moves:
        if move.get("direction") != match_direction:
            continue
        if intraday and abs(move.get("move_1d_pct", 0)) < intraday_threshold:
            continue
        score = snapshot_similarity(current, move.get("technical_snapshot", {}))
        if score <= 0:
            continue
        comparisons.append(
            {
                "date": move["date"],
                "move_1d_pct": move.get("move_1d_pct"),
                "move_1w_pct": move.get("move_1w_pct"),
                "similarity": round(score, 3),
                "tags": move.get("technical_snapshot", {}).get("tags", []),
            }
        )

    comparisons.sort(key=lambda item: item["similarity"], reverse=True)
    min_score = settings.technical.pattern_match_min_score
    strong = [item for item in comparisons if item["similarity"] >= min_score]

    technical_score = 0.0
    if strong:
        technical_score = min(10.0, 4.0 + (strong[0]["similarity"] * 6.0))
    technical_score += min(2.0, len(current.get("tags", [])) * 0.5)
    technical_score += _side_context_adjustment(current, side)
    technical_score = round(min(10.0, technical_score), 1)

    tag_set = set(current.get("tags", []))
    formation_state = _formation_alignment(current.get("formations", []), side)
    elliott_state = _elliott_alignment(tag_set, side)
    if formation_state == "conflict" or elliott_state == "conflict":
        technical_score = round(min(technical_score, 3.0), 1)
    elif formation_state == "support" or elliott_state == "support":
        technical_score = round(min(10.0, technical_score + 0.5), 1)

    bias = position_bias(current, focus=side)
    if settings.technical.require_trend_for_setup:
        if side == "long" and bias != "long":
            technical_score = round(min(technical_score, 3.0), 1)
        elif side == "short" and bias != "short":
            technical_score = round(min(technical_score, 3.0), 1)

    technical_score = _apply_side_context_caps(technical_score, current, side)

    thresholds = settings.thresholds
    if intraday:
        horizon = "intraday"
        target = intraday_threshold
    elif side == "short":
        horizon = "short_1d/1w"
        target = thresholds.stock_short_1d_pct
    else:
        horizon = "1d/1w"
        target = thresholds.stock_1d_pct

    return {
        "as_of": frame.index[-1].date().isoformat(),
        "current_snapshot": current,
        "top_matches": comparisons[:5],
        "match_count": len(strong),
        "technical_score": technical_score,
        "position_bias": bias,
        "position_side": side,
        "horizon": horizon,
        "target_move_pct": target,
        "intraday": intraday,
        "formation_alignment": formation_state,
        "elliott_alignment": elliott_state,
    }


def scan_setups_for_symbol(frame: pd.DataFrame, historical_moves: list[dict]) -> list[dict]:
    settings = get_settings()
    focus = settings.technical.position_focus
    sides = ["long", "short"] if focus == "both" else [focus]

    setups: list[dict] = []
    for side in sides:
        if side not in {"long", "short"}:
            continue
        setups.append(scan_today_setup(frame, historical_moves, side=side, intraday=False))

    if settings.technical.intraday.enabled:
        intraday_side = settings.technical.intraday.position_side
        if intraday_side in {"long", "short"} and (focus == "both" or focus == intraday_side):
            setups.append(
                scan_today_setup(frame, historical_moves, side=intraday_side, intraday=True)
            )

    return setups

