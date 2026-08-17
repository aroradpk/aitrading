#!/usr/bin/env python3
"""Fetch NSE announcements and PIB releases for active universe."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.core.config import get_settings
from app.engines.events import refresh_events_for_universe


def main() -> None:
    if get_settings().offline_mode:
        print("offline_mode=true — skipping event fetch (use saved data/events/)")
        return
    counts = refresh_events_for_universe()
    print(f"PIB items cached: {counts.get('pib', 0)}")
    stock_counts = {k: v for k, v in counts.items() if k != "pib"}
    print(f"NSE announcements fetched for {len(stock_counts)} symbols")
    for symbol, count in sorted(stock_counts.items(), key=lambda item: item[1], reverse=True)[:10]:
        print(f"  {symbol}: {count}")


if __name__ == "__main__":
    main()
