from __future__ import annotations

import argparse
import json
import sys

from app.config import get_settings
from app.pipeline.prepare import prepare_all, run_ingest
from app.pipeline.s1 import run_s1_backtest
from app.pipeline.train import run_daily_report, run_train_and_backtest


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="NSE next-day setup engine")
    sub = parser.add_subparsers(dest="cmd", required=True)

    ingest = sub.add_parser("ingest")
    ingest.add_argument("--source", choices=["synthetic", "yahoo"], default="synthetic")
    ingest.add_argument("--skip-intraday", action="store_true")

    sub.add_parser("features")
    sub.add_parser("train")
    sub.add_parser("backtest")
    sub.add_parser("report")
    sub.add_parser("run-daily")
    sub.add_parser("s1-backtest")

    args = parser.parse_args(argv)
    settings = get_settings()

    if args.cmd == "ingest":
        run_ingest(settings, source=args.source)
        print(f"ingested {args.source} into {settings.db_path}")
        return 0
    if args.cmd == "s1-backtest":
        report = run_s1_backtest()
        print(json.dumps({"setup_quality": report["setup_quality"], "trade_quality": report["trade_quality"]}, indent=2))
        print(f"full report: {report.get('artifact')}")
        return 0
    if args.cmd == "features":
        prepare_all(settings)
        print("features, candidates, and labels written")
        return 0
    if args.cmd in {"train", "backtest"}:
        report = run_train_and_backtest()
        print(json.dumps(report["oos_overall"], indent=2))
        print(f"full report: {settings.artifact_dir / 'walkforward_report.json'}")
        return 0
    if args.cmd in {"report", "run-daily"}:
        text = run_daily_report()
        print(text)
        return 0
    return 1


if __name__ == "__main__":
    sys.exit(main())
