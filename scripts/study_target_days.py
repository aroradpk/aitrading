#!/usr/bin/env python3
"""List days each book name rose at least its fixed %, newest first, with technical flags."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.engines.target_day import format_report, scan_book


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--limit", type=int, default=25, help="Hit days to print per symbol")
    parser.add_argument("--json-out", type=Path, default=None)
    args = parser.parse_args()
    book = scan_book(side="long")
    text = format_report(book, per_symbol_limit=args.limit)
    print(text)
    if args.json_out:
        args.json_out.parent.mkdir(parents=True, exist_ok=True)
        args.json_out.write_text(json.dumps(book, indent=2, default=str), encoding="utf-8")


if __name__ == "__main__":
    main()
