import json
from pathlib import Path

import pytest

from app.engines.event_content import analyze_event_content, score_analyzed_event
from app.engines.event_transcripts import (
    body_text_for_event,
    is_transcript_attachment,
    load_cached_transcript_text,
    save_transcript,
)
from app.engines.events import score_events


def test_is_transcript_attachment_detects_url_keyword() -> None:
    item = {
        "title": "Analysts/Institutional Investor Meet/Con. Call Updates",
        "attachment_url": "https://nsearchives.nseindia.com/corporate/FOO_transcript.pdf",
        "type": "announcement",
    }
    assert is_transcript_attachment(item) is True


def test_is_transcript_attachment_skips_schedule() -> None:
    item = {
        "title": "Schedule of investor meet",
        "attachment_url": "https://nsearchives.nseindia.com/corporate/FOO.pdf",
        "type": "analyst_meet",
    }
    assert is_transcript_attachment(item) is False


def test_analyze_event_with_transcript_body_scores_positive() -> None:
    item = {
        "type": "concall",
        "title": "Analysts/Institutional Investor Meet/Con. Call Updates",
        "attachment_url": "https://example.com/transcript.pdf",
    }
    body = "Management reported record revenue and margin expansion with raised guidance."
    analysis = analyze_event_content(item, body_text=body)
    assert analysis.get("requires_transcript") is False
    assert analysis["alignment"] == "positive"
    assert score_analyzed_event(item, analysis) > 0


def test_save_and_load_transcript_cache(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    import app.engines.event_transcripts as transcripts_module

    monkeypatch.setattr(transcripts_module, "events_transcripts_dir", lambda: tmp_path)
    item = {
        "date": "2026-01-15",
        "title": "Earnings call transcript",
        "attachment_url": "https://example.com/CO_transcript_jan.pdf",
        "type": "concall",
    }
    save_transcript("CO", item, "Strong demand and order book growth.")
    loaded = load_cached_transcript_text("CO", item)
    assert loaded == "Strong demand and order book growth."
    record = json.loads((tmp_path / "CO" / "CO_transcript_jan.json").read_text(encoding="utf-8"))
    assert record["text_file"].endswith(".txt")


def test_score_events_uses_cached_transcript(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    import app.engines.event_transcripts as transcripts_module
    import app.ingest.nse_client as nse_client

    nse_dir = tmp_path / "nse"
    nse_dir.mkdir()
    monkeypatch.setattr(transcripts_module, "events_transcripts_dir", lambda: tmp_path / "transcripts")
    monkeypatch.setattr(nse_client, "events_nse_dir", lambda: nse_dir)

    item = {
        "type": "announcement",
        "title": "Analysts/Institutional Investor Meet/Con. Call Updates",
        "attachment_url": "https://example.com/CO_learnings_call_transcript.pdf",
        "date": "2026-07-29",
    }
    (nse_dir / "CO.json").write_text(json.dumps([item]), encoding="utf-8")
    save_transcript("CO", item, "Management reported record revenue and margin expansion.")

    text = body_text_for_event("CO", item)
    assert text is not None
    analysis = analyze_event_content(item, body_text=text)
    assert analysis["alignment"] == "positive"

    score, reasons = score_events("CO")
    assert score > 0
    assert any(
        "record revenue" in reason.get("text", "").lower() or "margin" in reason.get("text", "").lower()
        for reason in reasons
    )
