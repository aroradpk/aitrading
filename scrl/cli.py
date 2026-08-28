"""CLI: scrl analyze RELIANCE.NS --horizon 20 --last-earnings 2026-07-17"""

from __future__ import annotations

import argparse
from pathlib import Path

from scrl.pipeline import analyze
from scrl.report import render_text


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="SCRL high-conviction research loop")
    sub = p.add_subparsers(dest="cmd", required=True)
    a = sub.add_parser("analyze", help="Run the research loop on one ticker")
    a.add_argument("ticker", nargs="?", default="RELIANCE.NS")
    a.add_argument("--horizon", type=int, default=20)
    a.add_argument("--as-of", dest="as_of", default=None)
    a.add_argument("--last-earnings", dest="last_earnings", default=None)
    a.add_argument("--k", type=int, default=25)
    a.add_argument("-o", "--output", default=None, help="Write ticket to this path")
    args = p.parse_args(argv)

    if args.cmd == "analyze":
        result = analyze(
            ticker=args.ticker,
            as_of=args.as_of,
            horizon_days=args.horizon,
            last_earnings=args.last_earnings,
            k_analogs=args.k,
        )
        text = render_text(result)
        print(text)
        if args.output:
            path = Path(args.output)
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
