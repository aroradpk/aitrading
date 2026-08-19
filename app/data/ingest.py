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


def _normalize_yahoo_ohlcv(raw: pd.DataFrame) -> pd.DataFrame:
    if isinstance(raw.columns, pd.MultiIndex):
        raw.columns = raw.columns.get_level_values(0)
    raw = raw.rename(columns=str.lower).reset_index()
    ts_col = "datetime" if "datetime" in raw.columns else raw.columns[0]
    frame = pd.DataFrame(
        {
            "ts": pd.to_datetime(raw[ts_col], utc=True),
            "open": raw["open"].astype(float),
            "high": raw["high"].astype(float),
            "low": raw["low"].astype(float),
            "close": raw["close"].astype(float),
            "volume": raw.get("volume", pd.Series(0, index=raw.index)).fillna(0).astype(float),
        }
    )
    return frame.dropna(subset=["open", "high", "low", "close"])


def ingest_yahoo_intraday(store: Store, end: date | None = None) -> None:
    """Yahoo keeps ~60d of 15m and ~730d of 1h. Daily history is loaded separately."""
    import yfinance as yf

    last = end or (date.today() - timedelta(days=1))
    specs = (("15m", "60d"), ("1h", "730d"))
    for item in UNIVERSE:
        for interval, period in specs:
            raw = yf.download(
                item.yahoo_ticker,
                period=period,
                interval=interval,
                auto_adjust=True,
                progress=False,
                threads=False,
            )
            if raw.empty:
                continue
            frame = _normalize_yahoo_ohlcv(raw)
            frame = frame[frame["ts"].dt.tz_convert("Asia/Kolkata").dt.date <= last]
            if frame.empty:
                continue
            store.replace_tf_bars(item.symbol, interval, frame)


def ingest_synthetic(store: Store, n_days: int = 750, seed: int = 7) -> None:
    from app.data.synthetic import make_synthetic_bars

    frames = make_synthetic_bars(n_days=n_days, seed=seed)
    for item in UNIVERSE:
        store.upsert_instrument(item.symbol, item.name, item.kind.value, item.yahoo_ticker)
        store.replace_daily_bars(item.symbol, frames[item.symbol])
