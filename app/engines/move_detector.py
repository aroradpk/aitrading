from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

from app.core.config import get_settings
from app.core.paths import moves_dir, technical_snapshots_dir
from app.engines.adr import snapshot_adr
from app.engines.pattern_confirmations import detect_daily_confirmations
from app.engines.mtf_analysis import analyze_intraday_confirmations
from app.engines.pattern_scoring import (
    elliott_alignment,
    formation_alignment,
    score_technical_confirmations,
)
from app.engines.technical import (
    LONG_HEADWIND_TAGS,
    LONG_TAILWIND_TAGS,
    SHORT_HEADWIND_TAGS,
    SHORT_TAILWIND_TAGS,
    build_snapshot,
    exhaustion_fade_side,
    position_bias,
)


def _formation_alignment(formations: list[dict], side: str) -> str:
    return formation_alignment(formations, side)


def _elliott_alignment(tags: set[str], side: str) -> str:
    return elliott_alignment(tags, side)


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
        snapshot["pattern_confirmations"] = detect_daily_confirmations(frame.loc[:idx], "long")

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
    symbol: str | None = None,
) -> dict:
    settings = get_settings()
    side = side or settings.technical.position_focus
    if side == "both":
        side = "long"

    symbol = symbol or str(frame["symbol"].iloc[-1])
    current = build_snapshot(frame, focus=side)
    confirmations = detect_daily_confirmations(frame, side)
    if not intraday:
        try:
            mtf = analyze_intraday_confirmations(symbol, current["date"], side=side)
            confirmations.update(mtf)
        except Exception:
            pass

    current["pattern_confirmations"] = confirmations
    adr = snapshot_adr(frame, symbol=symbol)
    current["adr"] = adr
    scored = score_technical_confirmations(
        confirmations,
        side=side,
        historical_moves=historical_moves,
        snapshot=current,
        adr=adr,
    )
    technical_score = scored["technical_score"]
    comparisons = scored["top_matches"]
    strong_count = scored["match_count"]

    formation_state = scored.get("formation_alignment") or _formation_alignment(
        current.get("formations", []), side
    )
    elliott_state = scored.get("elliott_alignment") or _elliott_alignment(
        set(current.get("tags", [])), side
    )
    families = scored.get("pattern_families") or []

    bias = position_bias(current, focus=side)
    energy = bool(scored.get("precision_energy"))
    expected = float(scored.get("expected_move_pct") or 0.0)
    horizon_days = int(scored.get("expected_horizon_days") or 1)
    ladder = energy or expected > 0
    if (
        settings.technical.require_trend_for_setup
        and technical_score < 6.0
        and not scored.get("breakout_base")
        and not ladder
    ):
        if side == "long" and bias != "long":
            technical_score = round(min(technical_score, 3.0), 1)
        elif side == "short" and bias != "short":
            technical_score = round(min(technical_score, 3.0), 1)

    if not ladder and not scored.get("breakout_base"):
        technical_score = _apply_side_context_caps(technical_score, current, side)
    horizon = "next_session"
    target = expected or float(adr.get("target_range_pct") or adr.get("adr20_pct") or 0.0)

    return {
        "as_of": frame.index[-1].date().isoformat(),
        "current_snapshot": current,
        "top_matches": comparisons[:5],
        "match_count": strong_count,
        "technical_score": technical_score,
        "pattern_confirmations": confirmations,
        "confirmation_labels": scored.get("confirmation_labels", []),
        "breakout_base": scored.get("breakout_base", False),
        "pattern_families": families,
        "position_bias": bias,
        "position_side": side,
        "horizon": horizon,
        "target_move_pct": target,
        "expected_move_pct": expected,
        "expected_horizon_days": horizon_days,
        "session_seven": bool(scored.get("session_seven")),
        "mtf_precision": bool(scored.get("mtf_precision")),
        "intraday": intraday,
        "adr": adr,
        "formation_alignment": formation_state,
        "elliott_alignment": elliott_state,
        "score_layers": scored.get("score_layers", {}),
    }


def scan_setups_for_symbol(frame: pd.DataFrame, historical_moves: list[dict]) -> list[dict]:
    settings = get_settings()
    focus = settings.technical.position_focus
    sides = ["long", "short"] if focus == "both" else [focus]
    symbol = str(frame["symbol"].iloc[-1])

    setups: list[dict] = []
    for side in sides:
        if side not in {"long", "short"}:
            continue
        setups.append(scan_today_setup(frame, historical_moves, side=side, intraday=False, symbol=symbol))

    if settings.technical.intraday.enabled:
        already = {setup["position_side"] for setup in setups}
        extra_side = settings.technical.intraday.position_side
        if extra_side in {"long", "short"} and extra_side not in already:
            setups.append(
                scan_today_setup(frame, historical_moves, side=extra_side, intraday=True, symbol=symbol)
            )

    return setups

