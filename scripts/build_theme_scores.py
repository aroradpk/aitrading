#!/usr/bin/env python3
"""Score thematic exposure for all stocks in active universe."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.engines.themes import build_all_theme_scores


def main() -> None:
    scores = build_all_theme_scores()
    print(f"Theme scores built for {len(scores)} symbols")
    for symbol, score in sorted(scores.items(), key=lambda item: item[1], reverse=True)[:10]:
        print(f"  {symbol}: {score}")


if __name__ == "__main__":
    main()
