#!/usr/bin/env python3
"""Download NSE concall / earnings-call transcript PDFs and cache extracted text."""

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.core.config import get_settings
from app.engines.event_transcripts import (
    fetch_transcripts_for_symbol,
    fetch_transcripts_for_universe,
    list_transcript_candidates,
)


def main() -> None:
    parser = argparse.ArgumentParser(description="Fetch and cache NSE event transcript PDFs")
    parser.add_argument("--symbol", help="Fetch transcripts for one symbol only")
    parser.add_argument("--limit", type=int, default=None, help="Max new PDFs per symbol")
    parser.add_argument("--list", action="store_true", help="List transcript candidates only")
    args = parser.parse_args()

    if get_settings().offline_mode:
        print("offline_mode=true — skipping PDF download (use saved data/events/transcripts/)")
        if args.symbol and args.list:
            for item in list_transcript_candidates(args.symbol.upper()):
                status = "cached" if item["cached"] else "missing"
                print(f"  [{status}] {item.get('date')} — {item.get('title')}")
        return

    if args.symbol:
        symbol = args.symbol.upper()
        if args.list:
            for item in list_transcript_candidates(symbol):
                status = "cached" if item["cached"] else "missing"
                print(f"  [{status}] {item.get('date')} — {item.get('title')}")
            return
        result = fetch_transcripts_for_symbol(symbol, limit=args.limit)
        print(result)
        return

    summary = fetch_transcripts_for_universe(limit_per_symbol=args.limit)
    total_fetched = sum(item["fetched"] for item in summary.values())
    total_failed = sum(item["failed"] for item in summary.values())
    print(f"Transcripts fetched: {total_fetched}, failed: {total_failed}")


if __name__ == "__main__":
    main()
