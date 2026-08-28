"""CLI: analyze one mandate, or run the personal desk (all mandates)."""

from __future__ import annotations

import argparse
from pathlib import Path

from scrl.journal import JournalEntry, append as journal_append, load as journal_load
from scrl.pipeline import analyze, analyze_desk
from scrl.report import render_desk, render_text


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="SCRL personal research desk")
    sub = p.add_subparsers(dest="cmd", required=True)

    a = sub.add_parser("analyze", help="One ticker, one mandate")
    a.add_argument("ticker", nargs="?", default="RELIANCE.NS")
    a.add_argument("--mandate", default="swing", help="swing | position | longterm")
    a.add_argument("--horizon", type=int, default=None, help="ignored; mandate sets horizon")
    a.add_argument("--as-of", dest="as_of", default=None)
    a.add_argument("--last-earnings", dest="last_earnings", default=None)
    a.add_argument("--k", type=int, default=25)
    a.add_argument("-o", "--output", default=None)
    a.add_argument("--journal", action="store_true", help="append TODAY to the paper journal")

    d = sub.add_parser("desk", help="Swing + position + long-term on one name (daily habit)")
    d.add_argument("ticker", nargs="?", default="RELIANCE.NS")
    d.add_argument("--as-of", dest="as_of", default=None)
    d.add_argument("--last-earnings", dest="last_earnings", default=None)
    d.add_argument("--k", type=int, default=25)
    d.add_argument("-o", "--output", default=None)
    d.add_argument("--journal", action="store_true")

    j = sub.add_parser("journal", help="Show paper journal")
    j.add_argument("--path", default="data/journal/paper.csv")

    args = p.parse_args(argv)

    if args.cmd == "analyze":
        result = analyze(
            ticker=args.ticker,
            as_of=args.as_of,
            last_earnings=args.last_earnings,
            k_analogs=args.k,
            mandate=args.mandate,
        )
        text = render_text(result)
        print(text)
        if args.output:
            path = Path(args.output)
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(text)
        if args.journal:
            journal_append(
                JournalEntry(
                    as_of=result.as_of.date(),
                    ticker=result.ticker,
                    mandate=result.mandate.name,
                    decision=result.permission.decision,
                    today=result.permission.today,
                    close=result.close,
                )
            )
        return 0

    if args.cmd == "desk":
        desk = analyze_desk(
            ticker=args.ticker,
            as_of=args.as_of,
            last_earnings=args.last_earnings,
            k_analogs=args.k,
        )
        text = render_desk(desk["swing"], desk["position"], desk["longterm"])
        print(text)
        if args.output:
            path = Path(args.output)
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(text)
        if args.journal:
            for name, result in desk.items():
                journal_append(
                    JournalEntry(
                        as_of=result.as_of.date(),
                        ticker=result.ticker,
                        mandate=name,
                        decision=result.permission.decision,
                        today=result.permission.today,
                        close=result.close,
                    )
                )
        return 0

    if args.cmd == "journal":
        rows = journal_load(Path(args.path))
        if not rows:
            print("journal empty")
            return 0
        for row in rows[-20:]:
            print(f"{row['as_of']}  {row['ticker']}  {row['mandate']:9}  {row['decision']:12}  {row['close']}")
        return 0

    return 1


if __name__ == "__main__":
    raise SystemExit(main())
