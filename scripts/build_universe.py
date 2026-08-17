#!/usr/bin/env python3
"""Build active universe: top 20 rising Nifty Next 50 stocks + indices."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.engines.universe import build_active_universe


def main() -> None:
    payload = build_active_universe()
    print(f"Selected {len(payload['stocks'])} stocks and {len(payload['indices'])} indices")
    for stock in payload["stocks"]:
        print(f"  {stock['symbol']}: {stock.get('yearly_return_pct')}% YoY")


if __name__ == "__main__":
    main()
