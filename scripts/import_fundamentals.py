#!/usr/bin/env python3
"""Import Screener CSV exports from data/fundamentals/import/*.csv."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.engines.fundamental import import_all_screener_files
from app.core.paths import fundamentals_import_dir


def main() -> None:
    import_dir = fundamentals_import_dir()
    print(f"Import directory: {import_dir}")
    print("Drop Screener CSV exports here, then re-run this script.")
    imported = import_all_screener_files()
    print(f"Imported fundamentals for {len(imported)} symbols")
    for symbol in sorted(imported):
        metrics = imported[symbol].get("metrics", {})
        print(f"  {symbol}: {len(metrics)} metrics")


if __name__ == "__main__":
    main()
