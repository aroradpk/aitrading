from __future__ import annotations

import re

POSITIVE_PHRASES = (
    "guidance raised",
    "guidance upgrade",
    "raised guidance",
    "record revenue",
    "record profit",
    "order book",
    "order pipeline",
    "capacity expansion",
    "margin expansion",
    "margin improvement",
    "beat estimate",
    "beats estimate",
    "above expectation",
    "ahead of estimate",
    "strong demand",
    "market share gain",
    "capex plan",
    "dividend increase",
    "positive outlook",
    "robust growth",
    "in line with expectation",
    "in line with estimates",
)

NEGATIVE_PHRASES = (
    "guidance cut",
    "lowered guidance",
    "miss estimate",
    "misses estimate",
    "below expectation",
    "weak demand",
    "margin pressure",
    "delay",
    "postpone",
    "headwind",
    "impairment",
    "downgrade",
    "negative outlook",
    "underperformance",
    "slippage",
    "cost overrun",
)

THEME_KEYWORDS = {
    "orders": ("order", "contract", "tender", "booking"),
    "capacity": ("capacity", "capex", "plant", "commission"),
    "margins": ("margin", "ebitda", "profitability"),
    "guidance": ("guidance", "outlook", "forecast"),
    "capital": ("fund raise", "qip", "rights issue", "debt"),
}


def _normalize(text: str) -> str:
    return re.sub(r"\s+", " ", text.lower()).strip()


def is_interactive_event(event_type: str, title: str) -> bool:
    lowered = title.lower()
    if event_type in {"analyst_meet", "concall", "investor_meet", "earnings_call"}:
        return True
    keywords = (
        "conference call",
        "con call",
        "concall",
        "earnings call",
        "analyst meet",
        "investor meet",
        "institutional investor",
        "analysts/investor",
    )
    return any(word in lowered for word in keywords)


def analyze_event_content(item: dict, body_text: str | None = None) -> dict:
    title = item.get("title", "")
    parts = [title]
    if body_text:
        parts.append(body_text)
    text = _normalize(" ".join(parts))
    event_type = item.get("type", "announcement")

    themes = [name for name, keys in THEME_KEYWORDS.items() if any(k in text for k in keys)]
    pos_hits = [p for p in POSITIVE_PHRASES if p in text]
    neg_hits = [p for p in NEGATIVE_PHRASES if p in text]

    sentiment_score = len(pos_hits) - len(neg_hits)
    if sentiment_score > 0:
        alignment = "positive"
    elif sentiment_score < 0:
        alignment = "negative"
    else:
        alignment = "neutral"

    interactive = is_interactive_event(event_type, title)
    analyzed = interactive or bool(pos_hits or neg_hits or themes)

    if interactive and alignment == "neutral" and not themes:
        if body_text:
            return {
                "analyzed": True,
                "alignment": "neutral",
                "sentiment_score": 0,
                "themes": themes,
                "positive_hits": pos_hits,
                "negative_hits": neg_hits,
                "summary": "Transcript reviewed — no strong positive/negative phrase matches",
                "requires_transcript": False,
                "transcript_analyzed": True,
            }
        return {
            "analyzed": False,
            "alignment": "unknown",
            "sentiment_score": 0,
            "themes": themes,
            "positive_hits": pos_hits,
            "negative_hits": neg_hits,
            "summary": "Interactive event — title lacks extractable positive/negative signals",
            "requires_transcript": True,
        }

    summary_parts = []
    if pos_hits:
        summary_parts.append(f"Positive: {', '.join(pos_hits[:3])}")
    if neg_hits:
        summary_parts.append(f"Negative: {', '.join(neg_hits[:3])}")
    if themes:
        summary_parts.append(f"Themes: {', '.join(themes)}")

    return {
        "analyzed": analyzed,
        "alignment": alignment,
        "sentiment_score": sentiment_score,
        "themes": themes,
        "positive_hits": pos_hits,
        "negative_hits": neg_hits,
        "summary": "; ".join(summary_parts) if summary_parts else title[:160],
        "requires_transcript": interactive and alignment == "neutral" and not body_text,
        "transcript_analyzed": bool(body_text),
    }


def score_analyzed_event(item: dict, analysis: dict) -> float:
    if not analysis.get("analyzed"):
        return 0.0
    if analysis.get("requires_transcript"):
        return 0.0

    alignment = analysis.get("alignment")
    event_type = item.get("type", "announcement")
    base = {
        "results": 2.0,
        "concall": 2.5,
        "earnings_call": 2.5,
        "analyst_meet": 2.0,
        "investor_meet": 2.0,
        "board_meeting": 1.5,
        "order_contract": 2.0,
        "corporate_action": 1.0,
        "announcement": 0.5,
    }.get(event_type, 0.5)

    if alignment == "positive":
        return base + min(2.0, len(analysis.get("positive_hits", [])) * 0.5)
    if alignment == "negative":
        return max(0.0, base * 0.25)
    return base * 0.5
