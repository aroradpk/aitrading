from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

from app.core.config import get_settings, nifty_next_50_path
from app.core.paths import ohlcv_daily_dir, universe_dir
from app.ingest.yfinance_client import fetch_ohlcv, load_ohlcv, yearly_return_pct


def load_nifty_next_50_symbols() -> list[dict[str, str]]:
    with nifty_next_50_path().open(encoding="utf-8") as handle:
        payload = json.load(handle)
    return payload["symbols"]


def build_active_universe() -> dict:
    settings = get_settings()
    candidates: list[dict] = []

    for entry in load_nifty_next_50_symbols():
        symbol = entry["symbol"]
        try:
            cached = ohlcv_daily_dir() / f"{symbol}.parquet"
            if settings.offline_mode and cached.exists():
                frame = load_ohlcv(cached)
            else:
                frame = fetch_ohlcv(symbol, instrument_type="stock")
            yearly_return = yearly_return_pct(frame)
            if yearly_return is None:
                continue
            if yearly_return < settings.universe.yearly_trend_min_return_pct:
                continue
            candidates.append(
                {
                    "symbol": symbol,
                    "name": entry.get("name", symbol),
                    "type": "stock",
                    "yahoo": f"{symbol}.NS",
                    "yearly_return_pct": yearly_return,
                    "last_close": float(frame["close"].iloc[-1]),
                    "as_of": frame.index[-1].date().isoformat(),
                }
            )
        except Exception as exc:  # noqa: BLE001 - collect per-symbol failures
            candidates.append(
                {
                    "symbol": symbol,
                    "name": entry.get("name", symbol),
                    "type": "stock",
                    "error": str(exc),
                }
            )

    rising = [item for item in candidates if "yearly_return_pct" in item]
    rising.sort(key=lambda item: item["yearly_return_pct"], reverse=True)
    top_stocks = rising[: settings.universe.active_count]

    indices = [
        {
            "symbol": index.symbol,
            "name": index.symbol.replace("_", " "),
            "type": "index",
            "yahoo": index.yahoo,
        }
        for index in settings.indices
    ]

    payload = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "selection_rule": (
            f"Top {settings.universe.active_count} Nifty Next 50 stocks with "
            f"positive 1-year return (min {settings.universe.yearly_trend_min_return_pct}%)"
        ),
        "stocks": top_stocks,
        "indices": indices,
        "skipped": [item for item in candidates if "error" in item],
    }

    output_path = universe_dir() / "active.json"
    output_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return payload


def load_active_universe() -> dict:
    path = universe_dir() / "active.json"
    if path.exists():
        return json.loads(path.read_text(encoding="utf-8"))
    if get_settings().offline_mode:
        raise FileNotFoundError(
            f"Missing {path}. Commit or copy data/universe/active.json, "
            "or run with offline_mode: false to build from the network."
        )
    return build_active_universe()


def all_instruments() -> list[dict]:
    universe = load_active_universe()
    return [*universe.get("stocks", []), *universe.get("indices", [])]
