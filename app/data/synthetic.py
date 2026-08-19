from __future__ import annotations

from datetime import date, timedelta

import numpy as np
import pandas as pd

from app.data.types import Bar
from app.universe import UNIVERSE


def _session_dates(n: int, end: date) -> list[date]:
    days: list[date] = []
    cursor = end
    while len(days) < n:
        if cursor.weekday() < 5:
            days.append(cursor)
        cursor -= timedelta(days=1)
    return list(reversed(days))


def make_synthetic_bars(
    n_days: int = 750,
    end: date | None = None,
    seed: int = 7,
) -> dict[str, pd.DataFrame]:
    """Generate weekday OHLCV with correlated index/stock paths. No real market data."""
    rng = np.random.default_rng(seed)
    end = end or date(2024, 12, 31)
    dates = _session_dates(n_days, end)
    n = len(dates)
    nifty_ret = rng.normal(0.0004, 0.009, n)
    bank_ret = 0.85 * nifty_ret + rng.normal(0.0001, 0.006, n)
    bajaj_ret = 0.55 * nifty_ret + 0.25 * bank_ret + rng.normal(0.0002, 0.014, n)

    def path(start: float, rets: np.ndarray, vol: float) -> pd.DataFrame:
        close = start * np.exp(np.cumsum(rets))
        open_ = np.concatenate([[start], close[:-1] * (1 + rng.normal(0, 0.002, n - 1))])
        high = np.maximum(open_, close) * (1 + rng.uniform(0.002, vol * 1.8, n))
        low = np.minimum(open_, close) * (1 - rng.uniform(0.002, vol * 1.8, n))
        # Occasional wide wicks so both stop and target can print on the same day.
        wide = rng.random(n) < 0.12
        high = np.where(wide, np.maximum(open_, close) * (1 + rng.uniform(0.012, 0.03, n)), high)
        low = np.where(wide, np.minimum(open_, close) * (1 - rng.uniform(0.012, 0.03, n)), low)
        volume = rng.integers(80_000, 400_000, n).astype(float)
        return pd.DataFrame(
            {
                "date": dates,
                "open": open_,
                "high": high,
                "low": low,
                "close": close,
                "volume": volume,
            }
        )

    starts = {"NIFTY": 18000.0, "BANKNIFTY": 42000.0, "BAJFINANCE": 6500.0}
    vols = {"NIFTY": 0.011, "BANKNIFTY": 0.014, "BAJFINANCE": 0.02}
    rets = {"NIFTY": nifty_ret, "BANKNIFTY": bank_ret, "BAJFINANCE": bajaj_ret}
    return {symbol: path(starts[symbol], rets[symbol], vols[symbol]) for symbol in starts}


def synthetic_bar_list(n_days: int = 750, end: date | None = None, seed: int = 7) -> list[Bar]:
    frames = make_synthetic_bars(n_days=n_days, end=end, seed=seed)
    bars: list[Bar] = []
    for symbol, frame in frames.items():
        for row in frame.itertuples(index=False):
            bars.append(
                Bar(
                    symbol=symbol,
                    date=row.date,
                    open=float(row.open),
                    high=float(row.high),
                    low=float(row.low),
                    close=float(row.close),
                    volume=float(row.volume),
                )
            )
    return bars


def known_universe_tickers() -> dict[str, str]:
    return {item.symbol: item.yahoo_ticker for item in UNIVERSE}
