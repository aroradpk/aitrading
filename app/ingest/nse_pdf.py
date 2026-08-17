from __future__ import annotations

import io
from urllib.parse import urlparse

import httpx
from pypdf import PdfReader

from app.core.offline import require_network
from app.ingest.nse_client import NSE_HOME, _nse_headers


def download_pdf(url: str) -> bytes:
    require_network(f"NSE PDF download ({url})")
    with httpx.Client(headers=_nse_headers(), timeout=90, follow_redirects=True) as client:
        client.get(NSE_HOME)
        response = client.get(url)
        response.raise_for_status()
        content_type = response.headers.get("content-type", "").lower()
        if "pdf" not in content_type and not url.lower().endswith(".pdf"):
            raise ValueError(f"Expected PDF from {url}, got {content_type or 'unknown'}")
        return response.content


def extract_text_from_pdf(pdf_bytes: bytes, max_chars: int = 120_000) -> str:
    reader = PdfReader(io.BytesIO(pdf_bytes))
    parts: list[str] = []
    for page in reader.pages:
        text = page.extract_text() or ""
        if text.strip():
            parts.append(text)
        if sum(len(part) for part in parts) >= max_chars:
            break
    combined = "\n".join(parts).strip()
    if len(combined) > max_chars:
        combined = combined[:max_chars]
    return combined


def pdf_filename_from_url(url: str) -> str:
    path = urlparse(url).path
    return path.rsplit("/", 1)[-1] if path else "document.pdf"
