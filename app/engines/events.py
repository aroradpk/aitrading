from __future__ import annotations

from datetime import date, datetime, timedelta, timezone

from app.core.config import get_settings
from app.engines.event_content import analyze_event_content, score_analyzed_event
from app.engines.event_transcripts import body_text_for_event
from app.engines.universe import all_instruments
from app.ingest.nse_client import fetch_nse_announcements, load_nse_announcements
from app.ingest.pib_client import fetch_pib_feed, load_pib_feed, match_pib_for_symbol


def _parse_iso(value: str | None) -> date | None:
    if not value:
        return None
    try:
        return date.fromisoformat(value[:10])
    except ValueError:
        return None


def score_events(symbol: str, as_of: date | None = None) -> tuple[float, list[dict]]:
    settings = get_settings()
    as_of = as_of or datetime.now(timezone.utc).date()
    lookback_start = as_of - timedelta(days=settings.events.lookback_days)

    score = 0.0
    reasons: list[dict] = []

    for item in load_nse_announcements(symbol):
        event_date = _parse_iso(item.get("date"))
        if event_date is None or event_date < lookback_start:
            continue

        transcript_text = body_text_for_event(symbol, item)
        analysis = analyze_event_content(item, body_text=transcript_text)
        points = score_analyzed_event(item, analysis)

        if analysis.get("requires_transcript"):
            reasons.append(
                {
                    "layer": "events",
                    "text": f"{item.get('title', 'NSE event')} — needs transcript/PDF for content scoring",
                    "weight": "low",
                    "date": item.get("date"),
                    "source": "https://www.nseindia.com",
                    "event_type": item.get("type"),
                    "analysis": analysis,
                }
            )
            continue

        if points <= 0:
            continue

        score += points
        label = item.get("title", "NSE announcement")
        if analysis.get("summary"):
            label = f"{label} — {analysis['summary']}"

        weight = "high" if analysis.get("alignment") == "positive" and points >= 2.5 else "medium"
        if analysis.get("alignment") == "negative":
            weight = "low"

        reasons.append(
            {
                "layer": "events",
                "text": label,
                "weight": weight,
                "date": item.get("date"),
                "source": "https://www.nseindia.com",
                "event_type": item.get("type"),
                "analysis": analysis,
            }
        )

    for item in match_pib_for_symbol(symbol):
        pub = item.get("pub_date", "")
        analysis = analyze_event_content(
            {"title": item.get("title", ""), "type": "pib_policy", **item}
        )
        points = score_analyzed_event({"type": "pib_policy"}, analysis)
        if points <= 0:
            continue
        score += points
        reasons.append(
            {
                "layer": "events",
                "text": f"PIB: {item.get('title', '')[:120]} — {analysis.get('summary', '')}",
                "weight": "medium" if analysis.get("alignment") != "negative" else "low",
                "date": pub[:16],
                "source": item.get("link") or "https://pib.gov.in",
                "event_type": "pib_policy",
                "analysis": analysis,
            }
        )

    return round(min(10.0, score), 1), reasons


def events_near_date(symbol: str, target: date, window_days: int | None = None) -> list[dict]:
    settings = get_settings()
    window_days = window_days or settings.events.move_alignment_days
    matched: list[dict] = []
    for item in load_nse_announcements(symbol):
        event_date = _parse_iso(item.get("date"))
        if event_date is None:
            continue
        if abs((event_date - target).days) <= window_days:
            matched.append(item)
    return matched


def enrich_moves_with_events(symbol: str, moves: list[dict]) -> list[dict]:
    enriched: list[dict] = []
    for move in moves:
        move_date = _parse_iso(move.get("date"))
        if move_date is None:
            enriched.append(move)
            continue
        aligned = events_near_date(symbol, move_date)
        move = dict(move)
        move["aligned_events"] = aligned
        move["event_reasons"] = []
        for item in aligned[:5]:
            transcript_text = body_text_for_event(symbol, item)
            analysis = analyze_event_content(item, body_text=transcript_text)
            move["event_reasons"].append(
                {
                    "type": item.get("type"),
                    "date": item.get("date"),
                    "title": item.get("title"),
                    "source": "https://www.nseindia.com",
                    "analysis": analysis,
                }
            )
        enriched.append(move)
    return enriched


def refresh_events_for_universe() -> dict[str, int]:
    fetch_pib_feed()
    counts: dict[str, int] = {"pib": len(load_pib_feed())}
    for instrument in all_instruments():
        if instrument.get("type") != "stock":
            continue
        symbol = instrument["symbol"]
        try:
            announcements = fetch_nse_announcements(symbol)
            counts[symbol] = len(announcements)
        except Exception:
            counts[symbol] = 0
    return counts
