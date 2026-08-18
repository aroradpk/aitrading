from __future__ import annotations

import json
from datetime import datetime, timezone

from app.core.config import trading_universe_path
from app.core.paths import ohlcv_daily_dir, universe_dir
from app.ingest.yfinance_client import fetch_ohlcv, load_ohlcv, save_ohlcv, yahoo_ticker, yearly_return_pct


def load_trading_instruments() -> list[dict]:
    payload = json.loads(trading_universe_path().read_text(encoding="utf-8"))
    return list(payload.get("instruments") or [])


def build_active_universe() -> dict:
    """Trading book is the 5-scrip intraday set, not Nifty Next 50."""
    instruments = load_trading_instruments()
    stocks: list[dict] = []
    indices: list[dict] = []
    skipped: list[dict] = []

    for entry in instruments:
        symbol = entry["symbol"]
        instrument_type = entry.get("type", "stock")
        row = {
            "symbol": symbol,
            "name": entry.get("name", symbol),
            "type": instrument_type,
            "yahoo": entry.get("yahoo"),
            "role": entry.get("role"),
        }
        cached = ohlcv_daily_dir() / f"{symbol}.parquet"
        try:
            from app.core.config import get_settings

            settings = get_settings()
            if settings.offline_mode and cached.exists():
                frame = load_ohlcv(cached)
            else:
                frame = fetch_ohlcv(
                    symbol,
                    instrument_type=instrument_type,
                    yahoo=entry.get("yahoo"),
                )
            row["last_close"] = float(frame["close"].iloc[-1])
            row["as_of"] = frame.index[-1].date().isoformat()
            save_ohlcv(frame, cached)
            if instrument_type == "stock":
                yearly = yearly_return_pct(frame)
                if yearly is not None:
                    row["yearly_return_pct"] = yearly
        except Exception as exc:  # noqa: BLE001
            skipped.append({**row, "error": str(exc)})
            continue
        if instrument_type == "index":
            indices.append(row)
        else:
            stocks.append(row)

    payload = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "selection_rule": json.loads(trading_universe_path().read_text(encoding="utf-8")).get(
            "selection_rule", "intraday 5"
        ),
        "stocks": stocks,
        "indices": indices,
        "skipped": skipped,
    }
    output_path = universe_dir() / "active.json"
    output_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return payload


def load_active_universe() -> dict:
    path = universe_dir() / "active.json"
    if path.exists():
        return json.loads(path.read_text(encoding="utf-8"))
    from app.core.config import get_settings

    if get_settings().offline_mode:
        raise FileNotFoundError(
            f"Missing {path}. Commit data/universe/active.json or set offline_mode false."
        )
    return build_active_universe()


def all_instruments() -> list[dict]:
    universe = load_active_universe()
    return [*universe.get("stocks", []), *universe.get("indices", [])]


def instrument_yahoo(symbol: str, instrument_type: str = "stock") -> str | None:
    for entry in load_trading_instruments():
        if entry.get("symbol") == symbol:
            return entry.get("yahoo") or yahoo_ticker(symbol, entry.get("type", instrument_type))
    return yahoo_ticker(symbol, instrument_type)
