from __future__ import annotations

import json
import re
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from pathlib import Path

import httpx

from app.core.config import get_settings
from app.core.offline import require_network
from app.core.paths import CONFIG_DIR, events_pib_dir, sources_cache_dir

_SECTOR_KEYWORDS: dict[str, list[str]] | None = None


def _load_sector_keywords() -> dict[str, list[str]]:
    global _SECTOR_KEYWORDS
    if _SECTOR_KEYWORDS is not None:
        return _SECTOR_KEYWORDS
    path = CONFIG_DIR / "sector_keywords.json"
    _SECTOR_KEYWORDS = json.loads(path.read_text(encoding="utf-8"))
    return _SECTOR_KEYWORDS


def fetch_pib_feed() -> list[dict]:
    settings = get_settings()
    if settings.offline_mode:
        cached = load_pib_feed()
        if cached:
            return cached
        require_network("PIB feed fetch")
    response = httpx.get(settings.events.pib_feed_url, timeout=45, follow_redirects=True)
    response.raise_for_status()
    root = ET.fromstring(response.text)
    items: list[dict] = []
    for item in root.findall(".//item"):
        title = (item.findtext("title") or "").strip()
        link = (item.findtext("link") or "").strip()
        pub_date = (item.findtext("pubDate") or "").strip()
        description = (item.findtext("description") or "").strip()
        items.append(
            {
                "source": "pib.gov.in",
                "type": "pib_release",
                "title": title,
                "link": link,
                "pub_date": pub_date,
                "description": description,
                "fetched_at": datetime.now(timezone.utc).isoformat(),
            }
        )

    items = items[: settings.events.pib_cache_count]
    cache_path = sources_cache_dir() / "pib" / "recent.json"
    cache_path.parent.mkdir(parents=True, exist_ok=True)
    cache_path.write_text(json.dumps(items, indent=2), encoding="utf-8")

    output = events_pib_dir() / "recent.json"
    output.write_text(json.dumps(items, indent=2), encoding="utf-8")
    return items


def load_pib_feed() -> list[dict]:
    path = events_pib_dir() / "recent.json"
    if not path.exists():
        return []
    return json.loads(path.read_text(encoding="utf-8"))


def match_pib_for_symbol(symbol: str, items: list[dict] | None = None) -> list[dict]:
    items = items if items is not None else load_pib_feed()
    keywords_map = _load_sector_keywords()
    keywords = keywords_map.get(symbol, []) + keywords_map.get("DEFAULT", [])
    matches: list[dict] = []
    for item in items:
        haystack = f"{item.get('title', '')} {item.get('description', '')}".lower()
        hit = [keyword for keyword in keywords if keyword.lower() in haystack]
        if hit:
            enriched = dict(item)
            enriched["matched_keywords"] = hit
            enriched["symbol"] = symbol
            matches.append(enriched)
    return matches
