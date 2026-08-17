from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import quote

import httpx

from app.core.config import get_settings
from app.core.paths import events_nse_dir, sources_cache_dir

NSE_HOME = "https://www.nseindia.com"
NSE_ANNOUNCEMENTS = (
    "https://www.nseindia.com/api/corporate-announcements"
    "?index=equities&symbol={symbol}&from_date={from_date}&to_date={to_date}"
)


def _nse_headers() -> dict[str, str]:
    return {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        ),
        "Accept": "application/json,text/plain,*/*",
        "Accept-Language": "en-US,en;q=0.9",
        "Referer": "https://www.nseindia.com/companies-listing/corporate-filings-announcements",
    }


def _parse_nse_date(value: str) -> str | None:
    for fmt in ("%d-%b-%Y %H:%M:%S", "%d-%b-%Y"):
        try:
            return datetime.strptime(value, fmt).date().isoformat()
        except ValueError:
            continue
    return None


def fetch_nse_announcements(symbol: str, lookback_days: int | None = None) -> list[dict]:
    settings = get_settings()
    lookback_days = lookback_days or settings.events.lookback_days
    end = datetime.now(timezone.utc).date()
    start = end - timedelta(days=lookback_days)
    from_date = start.strftime("%d-%m-%Y")
    to_date = end.strftime("%d-%m-%Y")
    url = NSE_ANNOUNCEMENTS.format(
        symbol=quote(symbol),
        from_date=from_date,
        to_date=to_date,
    )

    with httpx.Client(headers=_nse_headers(), timeout=45, follow_redirects=True) as client:
        client.get(NSE_HOME)
        response = client.get(url)
        response.raise_for_status()
        payload = response.json()

    announcements: list[dict] = []
    for item in payload if isinstance(payload, list) else []:
        subject = item.get("desc") or item.get("subject") or item.get("attchmntText") or ""
        event_date = _parse_nse_date(item.get("an_dt", ""))
        attachment = item.get("attchmntFile") or ""
        announcements.append(
            {
                "source": "nseindia.com",
                "type": _classify_announcement(subject),
                "date": event_date,
                "title": subject.strip(),
                "attachment_url": attachment,
                "fetched_at": datetime.now(timezone.utc).isoformat(),
                "raw_date": item.get("an_dt"),
            }
        )

    cache_path = sources_cache_dir() / "nse" / f"{symbol}.json"
    cache_path.parent.mkdir(parents=True, exist_ok=True)
    cache_path.write_text(json.dumps(announcements, indent=2), encoding="utf-8")

    output = events_nse_dir() / f"{symbol}.json"
    output.write_text(json.dumps(announcements, indent=2), encoding="utf-8")
    return announcements


def _classify_announcement(text: str) -> str:
    lowered = text.lower()
    if any(word in lowered for word in ("result", "financial", "quarter", "earnings")):
        return "results"
    if any(word in lowered for word in ("board meeting", "outcome of board")):
        return "board_meeting"
    if any(word in lowered for word in ("dividend", "bonus", "split")):
        return "corporate_action"
    if any(word in lowered for word in ("order", "contract", "agreement", "win")):
        return "order_contract"
    return "announcement"


def load_nse_announcements(symbol: str) -> list[dict]:
    path = events_nse_dir() / f"{symbol}.json"
    if not path.exists():
        return []
    return json.loads(path.read_text(encoding="utf-8"))
