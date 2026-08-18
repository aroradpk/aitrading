from __future__ import annotations

from app.engines.chart_patterns import load_formation_catalog
from app.engines.pattern_confirmations import confirmation_labels, is_breakout_base, is_coil_setup
from app.engines.technical import snapshot_similarity

TECHNICAL_MAX = 7.0

# Hit-and-trial on 20 stocks (day-before |next|>=5% vs quiet sample): no rule hits
# 80% recall at 5% FPR. Coil setups are *more* common on quiet days (anti-predictive).
# Pareto-best interpretable 7: EMA + S/R-Fib + expansion energy (FPR ~4–5%, recall ~11–14%).
# Coil is a watch cherry, not the alarm. Elliott / formations / candles stay cherries.
CORE_WEIGHTS = {
    "ema_structure": 2.5,
    "sr_fib": 2.5,
    "energy": 2.0,
}
CHERRY_WEIGHTS = {
    "coil": 0.5,
    "elliott": 0.5,
    "formation": 0.5,
    "candle": 0.5,
    "mtf": 0.5,
}
LAYER_WEIGHTS = {**CORE_WEIGHTS, **CHERRY_WEIGHTS}

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


def formation_alignment(formations: list[dict], side: str) -> str:
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


def elliott_alignment(tags: set[str], side: str) -> str:
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
        bonus = min(0.4, 0.15 + strong[0]["similarity"] * 0.4)
    return bonus, matches[:5]


def has_precision_energy(confirmations: dict[str, bool]) -> bool:
    """Quiet-day FPR gate: vol >= 2x and range >= 1.6x ATR. Best ~14% recall at ~5% FPR."""
    return bool(confirmations.get("vol_expansion") and confirmations.get("range_expansion"))


def _layer_scores(
    confirmations: dict[str, bool],
    *,
    side: str,
    snapshot: dict | None,
    families: list[str],
) -> dict[str, float]:
    tags = set((snapshot or {}).get("tags", []))
    layers = {name: 0.0 for name in LAYER_WEIGHTS}

    ema_piece = bool(
        families
        or confirmations.get("ema20_support")
        or confirmations.get("ema20_resistance")
        or confirmations.get("ema_bull_stack")
        or confirmations.get("ema_bear_stack")
    )
    if ema_piece:
        layers["ema_structure"] = CORE_WEIGHTS["ema_structure"]

    sr_ok = bool(confirmations.get("sr_level") or confirmations.get("ema20_support") or confirmations.get("ema20_resistance"))
    if side == "long":
        sr_ok = sr_ok or "near_support" in tags or "ema20_support_touch" in tags
    else:
        sr_ok = sr_ok or "near_resistance" in tags
    fib_ok = bool(confirmations.get("fib_level") or confirmations.get("mtf_1h_fib_sr")) or any(
        tag.startswith("fib_") for tag in tags
    )
    sr_fib = bool(confirmations.get("sr_fib_confluence") or confirmations.get("mtf_1h_fib_sr")) or (
        sr_ok and fib_ok
    )
    if sr_fib:
        layers["sr_fib"] = CORE_WEIGHTS["sr_fib"]

    if has_precision_energy(confirmations):
        layers["energy"] = CORE_WEIGHTS["energy"]

    ell_state = elliott_alignment(tags, side)
    if confirmations.get("elliott_conflict") or ell_state == "conflict":
        layers["elliott"] = 0.0
    elif confirmations.get("elliott_aligned") or ell_state == "support":
        layers["elliott"] = CHERRY_WEIGHTS["elliott"]

    form_state = formation_alignment((snapshot or {}).get("formations") or [], side)
    formation_ok = bool(confirmations.get("bullish_formation") if side == "long" else confirmations.get("bearish_formation"))
    if form_state == "conflict":
        layers["formation"] = 0.0
    elif formation_ok or form_state == "support":
        layers["formation"] = CHERRY_WEIGHTS["formation"]

    if is_coil_setup(confirmations):
        layers["coil"] = CHERRY_WEIGHTS["coil"]

    if confirmations.get("mtf_15m_wedge") or confirmations.get("mtf_1h_rounding_ema20"):
        layers["mtf"] = CHERRY_WEIGHTS["mtf"]

    candle_ok = any(tag.startswith("candle_") for tag in tags)
    if candle_ok and (sr_ok or fib_ok or sr_fib or layers["formation"] > 0 or layers["elliott"] > 0):
        layers["candle"] = CHERRY_WEIGHTS["candle"]

    return layers


def score_technical_confirmations(
    confirmations: dict[str, bool],
    *,
    side: str,
    historical_moves: list[dict] | None = None,
    snapshot: dict | None = None,
) -> dict:
    families = matched_families(confirmations, side=side)
    energy = has_precision_energy(confirmations)
    layers = _layer_scores(confirmations, side=side, snapshot=snapshot, families=families)
    score = sum(layers.values())

    if snapshot and historical_moves:
        tag_sim = 0.0
        for move in historical_moves[:50]:
            tag_sim = max(tag_sim, snapshot_similarity(snapshot, move.get("technical_snapshot", {})))
        score += min(0.3, tag_sim * 0.3)

    bonus, top_matches = historical_pattern_bonus(confirmations, historical_moves or [], side=side)
    score += bonus

    # 7 only when EMA + S/R-Fib + energy all fire. Coil-only is a watch (cap 5).
    if not layers.get("sr_fib") or not layers.get("ema_structure") or not layers.get("energy"):
        score = min(score, 5.0 if is_coil_setup(confirmations) else 4.0)

    # Blow-off: already extended into resistance — not a fresh 7 even if energy prints.
    if snapshot and energy:
        tags = set(snapshot.get("tags", []))
        late_long = side == "long" and ("ema20_extended_long" in tags and "near_resistance" in tags)
        late_short = side == "short" and ("ema20_extended_short" in tags and "near_support" in tags)
        if late_long or late_short:
            score = min(score, 4.0)

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

    layer_labels = []
    pretty = {
        "ema_structure": "EMA / trend structure",
        "sr_fib": "S/R with Fibonacci",
        "energy": "Volume + range expansion",
        "coil": "Rangebound coil cherry",
        "elliott": "Elliott wave cherry",
        "formation": "Chart formation cherry",
        "mtf": "Intraday MTF cherry",
        "candle": "Candlestick cherry (hammer / star)",
    }
    for key, value in layers.items():
        if value > 0:
            layer_labels.append(f"{pretty[key]} +{value:.1f}")
    for text in reversed(layer_labels):
        labels.insert(0, text)

    tags = set((snapshot or {}).get("tags", []))
    return {
        "technical_score": score,
        "pattern_confirmations": confirmations,
        "confirmation_labels": labels,
        "pattern_families": families,
        "score_layers": layers,
        "top_matches": top_matches,
        "match_count": match_count,
        "breakout_base": is_breakout_base(confirmations),
        "precision_energy": energy,
        "formation_alignment": formation_alignment((snapshot or {}).get("formations") or [], side),
        "elliott_alignment": elliott_alignment(tags, side),
    }
