from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path

import pandas as pd
import yfinance as yf

from app.core.config import get_settings
from app.core.paths import ohlcv_daily_dir


def yahoo_ticker(symbol: str, instrument_type: str = "stock") -> str:
    if instrument_type == "index":
        return symbol if symbol.startswith("^") else symbol
    return f"{symbol}.NS"


def fetch_ohlcv(
    symbol: str,
    *,
    instrument_type: str = "stock",
    yahoo: str | None = None,
    years: int | None = None,
) -> pd.DataFrame:
    settings = get_settings()
    cached = ohlcv_daily_dir() / f"{symbol}.parquet"
    if settings.offline_mode:
        if cached.exists():
            return load_ohlcv(cached)
        raise FileNotFoundError(
            f"No cached OHLCV for {symbol} at {cached} (offline_mode=true)"
        )

    years = years or int(settings.ohlcv.get("history_years", 5))
    ticker = yahoo or yahoo_ticker(symbol, instrument_type)
    end = datetime.now(timezone.utc)
    start = end - timedelta(days=365 * years + 30)

    frame = yf.download(
        ticker,
        start=start.date().isoformat(),
        end=end.date().isoformat(),
        interval="1d",
        auto_adjust=True,
        progress=False,
        threads=False,
    )
    if frame.empty:
        raise ValueError(f"No OHLCV data for {symbol} ({ticker})")

    if isinstance(frame.columns, pd.MultiIndex):
        frame.columns = [col[0].lower() for col in frame.columns]
    else:
        frame.columns = [col.lower() for col in frame.columns]

    frame = frame.rename(
        columns={
            "open": "open",
            "high": "high",
            "low": "low",
            "close": "close",
            "volume": "volume",
        }
    )
    frame.index = pd.to_datetime(frame.index).tz_localize(None)
    frame["symbol"] = symbol
    return frame[["open", "high", "low", "close", "volume", "symbol"]].dropna()


def save_ohlcv(frame: pd.DataFrame, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    frame.to_parquet(path, index=True)


def load_ohlcv(path: Path) -> pd.DataFrame:
    if not path.exists():
        raise FileNotFoundError(path)
    frame = pd.read_parquet(path)
    frame.index = pd.to_datetime(frame.index)
    return frame.sort_index()


def yearly_return_pct(frame: pd.DataFrame, lookback_days: int = 252) -> float | None:
    if len(frame) < 30:
        return None
    closes = frame["close"]
    if len(closes) <= lookback_days:
        start_price = closes.iloc[0]
    else:
        start_price = closes.iloc[-lookback_days - 1]
    end_price = closes.iloc[-1]
    if start_price <= 0:
        return None
    return round(((end_price / start_price) - 1) * 100, 2)
