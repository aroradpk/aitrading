#!/usr/bin/env python3
"""Fill next-session outcomes and refresh 7-rule hit rates. Not a trained model."""

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.engines.adr import build_adr_profiles
from app.engines.intraday_ledger import (
    backfill_ledger,
    load_ledger,
    recompute_rule_stats,
    resolve_open_rows,
)


def main() -> None:
    parser = argparse.ArgumentParser(description="Learn from next-session outcomes on the 5-scrip book")
    parser.add_argument("--backfill", type=int, default=0, help="Replay N recent daily bars into the ledger")
    args = parser.parse_args()

    if args.backfill:
        added = backfill_ledger(lookback_bars=args.backfill)
        print(f"Backfilled {added} ledger rows")
    elif not load_ledger():
        added = backfill_ledger(lookback_bars=60)
        print(f"Empty ledger — backfilled {added} rows")

    filled = resolve_open_rows()
    stats = recompute_rule_stats()
    profiles = build_adr_profiles()
    print(f"Resolved {filled} open rows")
    print("ADR profiles:")
    for row in profiles.get("instruments", []):
        print(f"  {row['symbol']}: ADR20 {row['adr20_pct']}% / {row['adr20_pts']} pts → 1.25x {row['target_range_pct']}%")
    print(json.dumps(stats, indent=2))


if __name__ == "__main__":
    main()
