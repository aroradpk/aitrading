from __future__ import annotations

from app.engines.pattern_confirmations import (
    confirmation_labels,
    detect_daily_confirmations,
    is_breakout_base,
)
from app.engines.technical import snapshot_similarity


LONG_WEIGHTS: dict[str, float] = {
    "ema20_support": 1.2,
    "consolidation_anchor": 1.0,
    "ema_momentum_expanding": 1.0,
    "ema_bull_stack": 0.6,
    "rsi_60_reclaim": 0.8,
    "uptrend": 0.5,
    "bullish_formation": 0.8,
    "compressing_wedge": 0.9,
    "rounding_bottom": 0.7,
    "mtf_15m_wedge": 1.0,
    "mtf_1h_rounding_ema20": 1.0,
}

SHORT_WEIGHTS: dict[str, float] = {
    "ema20_resistance": 1.2,
    "consolidation_anchor": 0.8,
    "ema_momentum_expanding_down": 1.0,
    "ema_bear_stack": 0.6,
    "rsi_60_reject": 0.8,
    "downtrend": 0.5,
    "bearish_formation": 0.8,
    "compressing_wedge": 0.9,
}

TECHNICAL_MAX = 7.0


def _pattern_overlap(current: dict[str, bool], historical: dict[str, bool]) -> float:
    keys = set(current) | set(historical)
    if not keys:
        return 0.0
    active_current = {k for k, v in current.items() if v}
    active_hist = {k for k, v in historical.items() if v}
    if not active_current or not active_hist:
        return 0.0
    union = active_current | active_hist
    overlap = active_current & active_hist
    return len(overlap) / len(union)


def historical_pattern_bonus(
    confirmations: dict[str, bool],
    historical_moves: list[dict],
    *,
    side: str,
) -> tuple[float, list[dict]]:
    direction = "up" if side == "long" else "down"
    matches: list[dict] = []
    for move in historical_moves:
        if move.get("direction") != direction:
            continue
        snap = move.get("technical_snapshot", {})
        hist_conf = snap.get("pattern_confirmations", {})
        if not hist_conf:
            continue
        overlap = _pattern_overlap(confirmations, hist_conf)
        if overlap <= 0:
            continue
        matches.append(
            {
                "date": move["date"],
                "move_1d_pct": move.get("move_1d_pct"),
                "move_1w_pct": move.get("move_1w_pct"),
                "similarity": round(overlap, 3),
                "tags": snap.get("tags", []),
                "confirmations": [k for k, v in hist_conf.items() if v],
            }
        )

    matches.sort(key=lambda item: item["similarity"], reverse=True)
    strong = [m for m in matches if m["similarity"] >= 0.35]
    bonus = 0.0
    if strong:
        bonus = min(1.4, 0.6 + strong[0]["similarity"] * 2.0)
    return bonus, matches[:5]


def score_technical_confirmations(
    confirmations: dict[str, bool],
    *,
    side: str,
    historical_moves: list[dict] | None = None,
    snapshot: dict | None = None,
) -> dict:
    weights = LONG_WEIGHTS if side == "long" else SHORT_WEIGHTS
    score = 0.0
    for key, weight in weights.items():
        if confirmations.get(key):
            score += weight

    # Legacy tag similarity (small additive)
    if snapshot and historical_moves:
        tag_sim = 0.0
        for move in historical_moves[:50]:
            tag_sim = max(tag_sim, snapshot_similarity(snapshot, move.get("technical_snapshot", {})))
        score += min(0.5, tag_sim * 0.5)

    bonus, top_matches = historical_pattern_bonus(
        confirmations, historical_moves or [], side=side
    )
    score += bonus

    # Headwinds for long chase without base
    if side == "long" and snapshot and not is_breakout_base(confirmations):
        tags = set(snapshot.get("tags", []))
        if "ema20_extended_long" in tags and "near_resistance" in tags:
            score -= 1.5
        if "rsi_overbought" in tags and "near_resistance" in tags and not confirmations.get("ema20_support"):
            score -= 1.0
    elif is_breakout_base(confirmations):
        score += 0.5

    score = round(min(TECHNICAL_MAX, max(0.0, score)), 1)
    match_count = sum(1 for m in top_matches if m["similarity"] >= 0.35)

    return {
        "technical_score": score,
        "pattern_confirmations": confirmations,
        "confirmation_labels": confirmation_labels(confirmations),
        "top_matches": top_matches,
        "match_count": match_count,
        "breakout_base": is_breakout_base(confirmations),
    }
