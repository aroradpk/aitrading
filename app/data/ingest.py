from __future__ import annotations

from datetime import date, timedelta

import pandas as pd

from app.data.store import Store
from app.universe import UNIVERSE


def ingest_yahoo(store: Store, lookback_days: int = 1500, end: date | None = None) -> None:
    import yfinance as yf

    # yfinance `end` is exclusive. Default through yesterday so we never use a partial today bar.
    last = end or (date.today() - timedelta(days=1))
    start = last - timedelta(days=lookback_days)
    fetch_end = last + timedelta(days=1)
    for item in UNIVERSE:
        store.upsert_instrument(item.symbol, item.name, item.kind.value, item.yahoo_ticker)
        raw = yf.download(
            item.yahoo_ticker,
            start=start.isoformat(),
            end=fetch_end.isoformat(),
            auto_adjust=True,
            progress=False,
            threads=False,
        )
        if raw.empty:
            raise RuntimeError(f"No Yahoo data for {item.yahoo_ticker}")
        if isinstance(raw.columns, pd.MultiIndex):
            raw.columns = raw.columns.get_level_values(0)
        raw = raw.rename(columns=str.lower).reset_index()
        date_col = "date" if "date" in raw.columns else "Date"
        frame = pd.DataFrame(
            {
                "date": pd.to_datetime(raw[date_col]).dt.date,
                "open": raw["open"].astype(float),
                "high": raw["high"].astype(float),
                "low": raw["low"].astype(float),
                "close": raw["close"].astype(float),
                "volume": raw.get("volume", pd.Series(0, index=raw.index)).fillna(0).astype(float),
            }
        )
        frame = frame[frame["date"] <= last].reset_index(drop=True)
        if frame.empty:
            raise RuntimeError(f"No Yahoo bars on or before {last.isoformat()} for {item.yahoo_ticker}")
        store.replace_daily_bars(item.symbol, frame)


def ingest_synthetic(store: Store, n_days: int = 750, seed: int = 7) -> None:
    from app.data.synthetic import make_synthetic_bars

    frames = make_synthetic_bars(n_days=n_days, seed=seed)
    for item in UNIVERSE:
        store.upsert_instrument(item.symbol, item.name, item.kind.value, item.yahoo_ticker)
        store.replace_daily_bars(item.symbol, frames[item.symbol])
