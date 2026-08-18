#!/usr/bin/env python3
"""Build active universe from the 5-scrip intraday book."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.engines.universe import build_active_universe


def main() -> None:
    payload = build_active_universe()
    print(f"Selected {len(payload['stocks'])} stocks and {len(payload['indices'])} indices")
    for row in [*payload["stocks"], *payload["indices"]]:
        yoy = row.get("yearly_return_pct")
        yoy_txt = f"{yoy}% YoY" if yoy is not None else row.get("role", "")
        print(f"  {row['symbol']}: {yoy_txt}")
    skipped = payload.get("skipped") or []
    for row in skipped:
        print(f"  SKIP {row['symbol']}: {row.get('error')}")


if __name__ == "__main__":
    main()
