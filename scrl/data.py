"""Market data fetch with optional on-disk cache. Prices are as-of close."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import pandas as pd

DEFAULT_TICKERS = {
    "equity": "RELIANCE.NS",
    "benchmark": "^NSEI",
    "brent": "BZ=F",
    "usd_inr": "INR=X",
}

CACHE_DIR = Path("data/cache")


@dataclass
class MarketBundle:
    equity: pd.Series
    benchmark: pd.Series
    brent: pd.Series
    usd_inr: pd.Series
    ticker: str

    def aligned_frame(self) -> pd.DataFrame:
        df = pd.concat(
            {
                "equity": self.equity,
                "benchmark": self.benchmark,
                "brent": self.brent,
                "usd_inr": self.usd_inr,
            },
            axis=1,
        )
        return df.dropna()


def _extract_close(raw: pd.DataFrame | pd.Series, ticker: str) -> pd.Series:
    if isinstance(raw, pd.Series):
        out = raw.copy()
        out.name = "close"
        return out.dropna()
    if isinstance(raw.columns, pd.MultiIndex):
        if "Close" in raw.columns.get_level_values(0):
            close = raw["Close"]
            if isinstance(close, pd.DataFrame):
                if ticker in close.columns:
                    close = close[ticker]
                else:
                    close = close.iloc[:, 0]
        else:
            close = raw.iloc[:, 0]
    elif "Close" in raw.columns:
        close = raw["Close"]
    elif "close" in raw.columns:
        close = raw["close"]
    else:
        close = raw.iloc[:, 0]
    close = close.copy()
    close.name = "close"
    if not isinstance(close.index, pd.DatetimeIndex):
        close.index = pd.to_datetime(close.index)
    close.index = close.index.tz_localize(None) if close.index.tz is not None else close.index
    return close.dropna().astype(float)


def fetch_yahoo(
    ticker: str,
    start: str = "2016-01-01",
    cache: bool = True,
) -> pd.Series:
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    cache_path = CACHE_DIR / f"{ticker.replace('^', '').replace('=', '_').replace('.', '_')}.csv"
    if cache and cache_path.exists():
        s = pd.read_csv(cache_path, index_col=0, parse_dates=True).iloc[:, 0]
        s.name = "close"
        return s.dropna()

    import yfinance as yf

    raw = yf.download(ticker, start=start, auto_adjust=True, progress=False, threads=False)
    if raw is None or raw.empty:
        raise RuntimeError(f"No data for {ticker}")
    close = _extract_close(raw, ticker)
    if cache:
        close.to_csv(cache_path)
    return close


def load_bundle(
    equity: str = DEFAULT_TICKERS["equity"],
    start: str = "2016-01-01",
    cache: bool = True,
    fallback_brent: str = "CL=F",
) -> MarketBundle:
    eq = fetch_yahoo(equity, start=start, cache=cache)
    bench = fetch_yahoo(DEFAULT_TICKERS["benchmark"], start=start, cache=cache)
    try:
        brent = fetch_yahoo(DEFAULT_TICKERS["brent"], start=start, cache=cache)
    except Exception:
        brent = fetch_yahoo(fallback_brent, start=start, cache=cache)
    fx = fetch_yahoo(DEFAULT_TICKERS["usd_inr"], start=start, cache=cache)
    return MarketBundle(equity=eq, benchmark=bench, brent=brent, usd_inr=fx, ticker=equity)
