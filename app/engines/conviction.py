from __future__ import annotations

import json
from datetime import datetime, timezone

from app.core.paths import reports_dir
from app.core.paths import ohlcv_daily_dir
from app.engines.events import score_events
from app.engines.fundamental import score_fundamentals
from app.engines.move_detector import load_moves, scan_today_setup
from app.engines.universe import all_instruments
from app.ingest.yfinance_client import load_ohlcv


def conviction_from_scores(
    technical: float,
    fundamental: float = 0.0,
    events: float = 0.0,
    theme: float = 0.0,
) -> dict:
    from app.core.config import get_settings

    settings = get_settings()
    weights = settings.conviction_weights
    weighted = (
        technical * weights.technical
        + fundamental * weights.fundamental
        + events * weights.events
        + theme * weights.theme
    )
    if weighted <= 0:
        final = 0.0
    else:
        final = min(10.0, max(1.0, weighted))
    return {
        "technical": round(technical, 1),
        "fundamental": round(fundamental, 1),
        "events": round(events, 1),
        "theme": round(theme, 1),
        "final": round(final, 1),
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
        setup = scan_today_setup(frame, historical_moves)

        fundamental_score, fundamental_reasons = (0.0, [])
        event_score, event_reasons = (0.0, [])
        if instrument_type == "stock":
            fundamental_score, fundamental_reasons = score_fundamentals(symbol)
            event_score, event_reasons = score_events(symbol)

        scores = conviction_from_scores(
            technical=setup["technical_score"],
            fundamental=fundamental_score,
            events=event_score,
        )

        reasons = [
            {
                "layer": "technical",
                "text": tag.replace("_", " "),
                "weight": "medium",
            }
            for tag in setup["current_snapshot"].get("tags", [])
        ]
        for match in setup.get("top_matches", [])[:3]:
            reasons.append(
                {
                    "layer": "technical",
                    "text": (
                        f"Similar to {match['date']} move "
                        f"({match.get('move_1d_pct')}% 1D) — "
                        f"{int(match['similarity'] * 100)}% match"
                    ),
                    "weight": "high" if match["similarity"] >= 0.6 else "medium",
                    "date": match["date"],
                }
            )
        reasons.extend(fundamental_reasons)
        reasons.extend(event_reasons)

        horizon = "1d" if instrument_type == "index" else "1d/1w"
        target = 2.0 if instrument_type == "index" else 5.0

        entries.append(
            {
                "symbol": symbol,
                "name": instrument.get("name", symbol),
                "type": instrument_type,
                "as_of": setup["as_of"],
                "horizon": horizon,
                "target_move_pct": target,
                "conviction": scores["final"],
                "scores": scores,
                "match_count": setup["match_count"],
                "top_matches": setup["top_matches"],
                "current_snapshot": setup["current_snapshot"],
                "reasons": reasons,
            }
        )

    entries.sort(key=lambda item: item["conviction"], reverse=True)
    payload = {
        "report_date": report_date,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "count": len(entries),
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
