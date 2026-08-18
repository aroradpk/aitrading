from __future__ import annotations

import json
from datetime import datetime, timezone

from app.core.paths import reports_dir
from app.core.paths import ohlcv_daily_dir
from app.engines.events import score_events
from app.engines.fundamental import score_fundamentals
from app.engines.themes import score_themes
from app.engines.move_detector import load_moves, scan_setups_for_symbol
from app.engines.technical import technical_reasons_for_side
from app.engines.adr import build_adr_profiles
from app.engines.intraday_ledger import log_today_setups, recompute_rule_stats, resolve_open_rows
from app.engines.universe import all_instruments
from app.ingest.yfinance_client import load_ohlcv


def theme_bonus_score(theme_raw: float) -> float:
    """Separate theme column on 1–5 scale (not part of conviction)."""
    if theme_raw <= 0:
        return 1.0
    return round(min(5.0, max(1.0, 1.0 + theme_raw / 2.5)), 1)


def conviction_from_scores(
    technical: float,
    fundamental: float = 0.0,
    events: float = 0.0,
    theme: float = 0.0,
) -> dict:
    from app.core.config import get_settings

    settings = get_settings()
    tech_max = settings.conviction_weights.technical_max
    research_max = settings.conviction_weights.research_max

    technical_clamped = round(min(tech_max, max(0.0, technical)), 1)
    # Fundamental + events (meetings) share research bucket (0–3)
    fund_scaled = min(1.5, max(0.0, fundamental) * 0.15)
    event_scaled = min(1.5, max(0.0, events) * 0.15)
    research = round(min(research_max, fund_scaled + event_scaled), 1)

    final = round(min(10.0, technical_clamped + research), 1) if (technical_clamped + research) > 0 else 0.0
    if final > 0:
        final = max(1.0, final)

    return {
        "technical": technical_clamped,
        "research": research,
        "fundamental": round(fundamental, 1),
        "events": round(events, 1),
        "theme_bonus": theme_bonus_score(theme),
        "final": final,
    }


def build_daily_watchlist() -> dict:
    report_date = datetime.now(timezone.utc).date().isoformat()
    entries: list[dict] = []

    for instrument in all_instruments():
        symbol = instrument["symbol"]
        instrument_type = instrument.get("type", "stock")
        path = ohlcv_daily_dir() / f"{symbol}.parquet"
        if not path.exists():
            continue

        frame = load_ohlcv(path)
        historical_moves = load_moves(symbol)
        setups = scan_setups_for_symbol(frame, historical_moves)

        fundamental_score, fundamental_reasons = (0.0, [])
        event_score, event_reasons = (0.0, [])
        theme_score, theme_reasons = (0.0, [])
        if instrument_type == "stock":
            fundamental_score, fundamental_reasons = score_fundamentals(symbol)
            event_score, event_reasons = score_events(symbol)
            theme_score, theme_reasons, _ = score_themes(symbol)

        for setup in setups:
            if setup["technical_score"] <= 0:
                continue

            scores = conviction_from_scores(
                technical=setup["technical_score"],
                fundamental=fundamental_score,
                events=event_score,
                theme=theme_score,
            )

            reasons = technical_reasons_for_side(setup["current_snapshot"], setup["position_side"])
            for label in setup.get("confirmation_labels", []):
                reasons.insert(
                    0,
                    {"layer": "technical", "text": label, "weight": "high"},
                )
            for match in setup.get("top_matches", [])[:3]:
                confs = match.get("confirmations") or []
                conf_txt = f" [{', '.join(confs[:3])}]" if confs else ""
                reasons.append(
                    {
                        "layer": "technical",
                        "text": (
                            f"Similar pattern to {match['date']} {setup['position_side']} move "
                            f"({match.get('move_1d_pct')}% 1D) — "
                            f"{int(match['similarity'] * 100)}% overlap{conf_txt}"
                        ),
                        "weight": "high" if match["similarity"] >= 0.5 else "medium",
                        "date": match["date"],
                    }
                )
            reasons.extend(fundamental_reasons)
            reasons.extend(event_reasons)
            reasons.extend(theme_reasons)

            horizon = setup.get("horizon", "next_session")
            target = setup.get("target_move_pct") or (setup.get("adr") or {}).get("target_range_pct") or 0.0
            adr = setup.get("adr") or {}

            entries.append(
                {
                    "symbol": symbol,
                    "name": instrument.get("name", symbol),
                    "type": instrument_type,
                    "as_of": setup["as_of"],
                    "horizon": horizon,
                    "target_move_pct": target,
                    "expected_move_pct": setup.get("expected_move_pct", 0.0),
                    "expected_horizon_days": setup.get("expected_horizon_days", 1),
                    "session_seven": setup.get("session_seven", False),
                    "adr20_pct": adr.get("adr20_pct"),
                    "adr20_pts": adr.get("adr20_pts"),
                    "target_range_pct": adr.get("target_range_pct"),
                    "expansion_mult": adr.get("expansion_mult"),
                    "position_bias": setup.get("position_bias", "neutral"),
                    "position_side": setup.get("position_side", "long"),
                    "intraday": setup.get("intraday", False),
                    "conviction": scores["final"],
                    "scores": scores,
                    "match_count": setup["match_count"],
                    "top_matches": setup["top_matches"],
                    "pattern_confirmations": setup.get("pattern_confirmations", {}),
                    "current_snapshot": setup["current_snapshot"],
                    "reasons": reasons,
                }
            )

    entries.sort(key=lambda item: item["conviction"], reverse=True)
    from app.core.config import get_settings

    logged = log_today_setups(entries)
    resolved = resolve_open_rows()
    rule_stats = recompute_rule_stats()
    adr_profiles = build_adr_profiles()

    tech = get_settings().technical
    payload = {
        "report_date": report_date,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "count": len(entries),
        "config": {
            "position_focus": tech.position_focus,
            "intraday_enabled": tech.intraday.enabled,
            "conviction_model": "technical_7_plus_research_3",
            "trading_book": "intraday_5",
            "adr": {
                "window": adr_profiles.get("window"),
                "expansion_mult": adr_profiles.get("expansion_mult"),
                "hit_definition": adr_profiles.get("hit_definition"),
                "expansion_factor": adr_profiles.get("expansion_factor"),
            },
            "learn": {
                "logged_today": logged,
                "resolved": resolved,
                "resolved_rows": rule_stats.get("resolved_rows", 0),
                "min_n_to_trust": rule_stats.get("min_n_to_trust", 20),
            },
        },
        "entries": entries,
    }
    output = reports_dir() / f"{report_date}.json"
    output.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return payload


def load_latest_watchlist() -> dict | None:
    root = reports_dir()
    files = sorted(root.glob("*.json"), reverse=True)
    if not files:
        return None
    return json.loads(files[0].read_text(encoding="utf-8"))
