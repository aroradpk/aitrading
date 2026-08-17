from __future__ import annotations

import hashlib
import json
import re
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse

from app.core.config import get_settings
from app.core.paths import events_transcripts_dir
from app.ingest.nse_pdf import download_pdf, extract_text_from_pdf, pdf_filename_from_url
from app.ingest.nse_client import load_nse_announcements

TRANSCRIPT_KEYWORDS = (
    "transcript",
    "concall",
    "con call",
    "earnings call",
    "earningscall",
    "audioandtranscript",
    "conference call",
)

SKIP_TITLE_KEYWORDS = (
    "schedule of",
    "intimation of",
    "audio link",
    "investor presentation",
    "corporate presentation",
    "scrutinizer",
    "voting results",
    "proceedings",
)


def is_transcript_attachment(item: dict) -> bool:
    title = (item.get("title") or "").lower()
    url = (item.get("attachment_url") or "").lower()
    if not url.endswith(".pdf"):
        return False
    if any(skip in title for skip in SKIP_TITLE_KEYWORDS):
        return "transcript" in title or "transcript" in url
    if any(key in title or key in url for key in TRANSCRIPT_KEYWORDS):
        return True
    event_type = item.get("type", "")
    if event_type in {"concall", "earnings_call"} and "outcome" in title:
        return True
    return False


def _cache_slug(item: dict) -> str:
    url = item.get("attachment_url") or ""
    if url:
        stem = Path(urlparse(url).path).stem
        slug = re.sub(r"[^\w\-]+", "_", stem).strip("_")
        if slug:
            return slug[:120]
    digest = hashlib.sha1(
        f"{item.get('date')}|{item.get('title')}|{url}".encode("utf-8")
    ).hexdigest()[:12]
    return digest


def transcript_record_path(symbol: str, item: dict) -> Path:
    return events_transcripts_dir() / symbol.upper() / f"{_cache_slug(item)}.json"


def transcript_text_path(symbol: str, item: dict) -> Path:
    return events_transcripts_dir() / symbol.upper() / f"{_cache_slug(item)}.txt"


def load_cached_transcript_text(symbol: str, item: dict) -> str | None:
    record_path = transcript_record_path(symbol, item)
    if record_path.exists():
        record = json.loads(record_path.read_text(encoding="utf-8"))
        text_path = events_transcripts_dir() / symbol.upper() / record.get("text_file", "")
        if text_path.exists():
            text = text_path.read_text(encoding="utf-8").strip()
            return text or None
        inline = record.get("text")
        if isinstance(inline, str) and inline.strip():
            return inline.strip()
    text_path = transcript_text_path(symbol, item)
    if text_path.exists():
        text = text_path.read_text(encoding="utf-8").strip()
        return text or None
    return None


def save_transcript(symbol: str, item: dict, text: str) -> Path:
    symbol = symbol.upper()
    out_dir = events_transcripts_dir() / symbol
    out_dir.mkdir(parents=True, exist_ok=True)
    slug = _cache_slug(item)
    text_file = f"{slug}.txt"
    text_path = out_dir / text_file
    text_path.write_text(text, encoding="utf-8")
    record = {
        "symbol": symbol,
        "event_date": item.get("date"),
        "title": item.get("title"),
        "attachment_url": item.get("attachment_url"),
        "type": item.get("type"),
        "text_file": text_file,
        "text_length": len(text),
        "fetched_at": datetime.now(timezone.utc).isoformat(),
    }
    record_path = out_dir / f"{slug}.json"
    record_path.write_text(json.dumps(record, indent=2), encoding="utf-8")
    return record_path


def fetch_transcript_for_event(symbol: str, item: dict) -> str | None:
    cached = load_cached_transcript_text(symbol, item)
    if cached:
        return cached
    if not is_transcript_attachment(item):
        return None
    settings = get_settings()
    if settings.offline_mode:
        return None
    url = item.get("attachment_url")
    if not url:
        return None
    pdf_bytes = download_pdf(url)
    text = extract_text_from_pdf(pdf_bytes)
    if not text.strip():
        raise ValueError(f"No extractable text in PDF {pdf_filename_from_url(url)}")
    save_transcript(symbol, item, text)
    return text


def body_text_for_event(symbol: str, item: dict) -> str | None:
    if not is_transcript_attachment(item):
        return None
    return load_cached_transcript_text(symbol, item)


def fetch_transcripts_for_symbol(symbol: str, limit: int | None = None) -> dict[str, int]:
    symbol = symbol.upper()
    fetched = 0
    skipped = 0
    failed = 0
    for item in load_nse_announcements(symbol):
        if not is_transcript_attachment(item):
            continue
        if load_cached_transcript_text(symbol, item):
            skipped += 1
            continue
        try:
            text = fetch_transcript_for_event(symbol, item)
            if text:
                fetched += 1
            else:
                skipped += 1
        except Exception:
            failed += 1
        if limit is not None and fetched >= limit:
            break
    return {"symbol": symbol, "fetched": fetched, "skipped": skipped, "failed": failed}


def fetch_transcripts_for_universe(limit_per_symbol: int | None = None) -> dict[str, dict[str, int]]:
    from app.engines.universe import all_instruments

    summary: dict[str, dict[str, int]] = {}
    for instrument in all_instruments():
        if instrument.get("type") != "stock":
            continue
        symbol = instrument["symbol"]
        summary[symbol] = fetch_transcripts_for_symbol(symbol, limit=limit_per_symbol)
    return summary


def list_transcript_candidates(symbol: str) -> list[dict]:
    symbol = symbol.upper()
    candidates: list[dict] = []
    for item in load_nse_announcements(symbol):
        if not is_transcript_attachment(item):
            continue
        cached = load_cached_transcript_text(symbol, item) is not None
        candidates.append(
            {
                "date": item.get("date"),
                "title": item.get("title"),
                "attachment_url": item.get("attachment_url"),
                "cached": cached,
            }
        )
    return candidates
