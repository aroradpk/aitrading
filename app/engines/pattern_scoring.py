from __future__ import annotations

from app.engines.pattern_confirmations import confirmation_labels, is_breakout_base
from app.engines.technical import snapshot_similarity

TECHNICAL_MAX = 7.0

LONG_FAMILIES: dict[str, tuple[str, ...]] = {
    "ema_pullback": ("ema20_support", "uptrend", "ema_bull_stack", "close_above_ema20"),
    "coil_breakout": ("tight_range", "consolidation_anchor", "compressing_wedge", "bullish_formation", "higher_lows"),
    "momentum_stack": ("ema_bull_stack", "ema_momentum_expanding", "close_above_ema20", "uptrend"),
    "formation_base": ("bullish_formation", "ema20_support", "consolidation_anchor", "rounding_bottom", "uptrend"),
    "rsi_reclaim": ("rsi_60_reclaim", "rsi_trend_long", "ema20_support", "uptrend"),
    "rising_structure": ("higher_lows", "close_above_ema20", "tight_range", "uptrend"),
}

SHORT_FAMILIES: dict[str, tuple[str, ...]] = {
    "ema_reject": ("ema20_resistance", "downtrend", "ema_bear_stack", "close_below_ema20"),
    "coil_breakdown": ("tight_range", "consolidation_anchor", "compressing_wedge", "bearish_formation", "lower_highs"),
    "momentum_down": ("ema_bear_stack", "ema_momentum_expanding_down", "close_below_ema20", "downtrend"),
    "formation_top": ("bearish_formation", "ema20_resistance", "consolidation_anchor", "downtrend"),
    "rsi_reject": ("rsi_60_reject", "rsi_trend_short", "ema20_resistance", "downtrend"),
    "falling_structure": ("lower_highs", "close_below_ema20", "tight_range", "downtrend"),
}

# A family fires when at least 2 of its members are true (any 2-piece pattern, not MOTHERSON-only).
FAMILY_MIN_HITS = 2


def _active(confirmations: dict[str, bool]) -> set[str]:
    return {key for key, value in confirmations.items() if value}


def matched_families(confirmations: dict[str, bool], *, side: str) -> list[str]:
    catalog = LONG_FAMILIES if side == "long" else SHORT_FAMILIES
    active = _active(confirmations)
    names: list[str] = []
    for name, members in catalog.items():
        hits = sum(1 for member in members if member in active)
        if hits >= FAMILY_MIN_HITS:
            names.append(name)
    return names


def _pattern_overlap(current: dict[str, bool], historical: dict[str, bool]) -> float:
    active_current = _active(current)
    active_hist = _active(historical)
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


def has_precision_energy(confirmations: dict[str, bool]) -> bool:
    """High conviction requires expansion energy (keeps quiet-day FPR near 5%)."""
    return bool(confirmations.get("vol_expansion") and confirmations.get("range_expansion"))


def score_technical_confirmations(
    confirmations: dict[str, bool],
    *,
    side: str,
    historical_moves: list[dict] | None = None,
    snapshot: dict | None = None,
) -> dict:
    families = matched_families(confirmations, side=side)
    active_count = len(_active(confirmations))
    energy = has_precision_energy(confirmations)

    if families and energy:
        score = TECHNICAL_MAX
    elif families or active_count >= 2:
        score = 4.0
    elif active_count == 1:
        score = 2.5
    else:
        score = 1.0

    if snapshot and historical_moves:
        tag_sim = 0.0
        for move in historical_moves[:50]:
            tag_sim = max(tag_sim, snapshot_similarity(snapshot, move.get("technical_snapshot", {})))
        if score < TECHNICAL_MAX:
            score += min(0.5, tag_sim * 0.5)

    bonus, top_matches = historical_pattern_bonus(
        confirmations, historical_moves or [], side=side
    )
    if score < TECHNICAL_MAX:
        score += bonus

    # Only fade a long chase when there is no pattern family at all.
    if side == "long" and snapshot and not families:
        tags = set(snapshot.get("tags", []))
        if "ema20_extended_long" in tags and "near_resistance" in tags:
            score = min(score, 3.0)

    score = round(min(TECHNICAL_MAX, max(0.0, score)), 1)
    match_count = sum(1 for m in top_matches if m["similarity"] >= 0.35)
    labels = confirmation_labels(confirmations)
    for family in families:
        labels.insert(0, f"Pattern family: {family.replace('_', ' ')}")

    return {
        "technical_score": score,
        "pattern_confirmations": confirmations,
        "confirmation_labels": labels,
        "pattern_families": families,
        "top_matches": top_matches,
        "match_count": match_count,
        "breakout_base": is_breakout_base(confirmations) or (bool(families) and energy),
        "precision_energy": energy,
    }
