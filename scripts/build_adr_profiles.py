#!/usr/bin/env python3
"""Write per-scrip ADR20 and 1.25x targets to data/intraday/adr_profile.json."""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.engines.adr import build_adr_profiles


def main() -> None:
    payload = build_adr_profiles()
    print(payload["hit_definition"])
    print(f"{'symbol':12} {'ADR20%':7} {'pts':10} {'1.25x target%':14}")
    for row in payload["instruments"]:
        print(
            f"{row['symbol']:12} {row['adr20_pct']:7.2f} {row['adr20_pts']:10.2f} {row['target_range_pct']:14.2f}"
        )
    print(json.dumps(payload["expansion_factor"], indent=2))


if __name__ == "__main__":
    main()
