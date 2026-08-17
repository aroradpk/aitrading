#!/usr/bin/env python3
"""Build today's conviction watchlist from technical pattern similarity."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.engines.conviction import build_daily_watchlist


def main() -> None:
    payload = build_daily_watchlist()
    print(f"Watchlist {payload['report_date']}: {payload['count']} symbols")
    for entry in payload["entries"][:10]:
        print(
            f"  {entry['symbol']}: conviction {entry['conviction']} "
            f"(matches={entry['match_count']})"
        )


if __name__ == "__main__":
    main()
