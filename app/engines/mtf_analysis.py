from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pandas as pd

from app.core.config import get_settings
from app.core.paths import ohlcv_intraday_dir
from app.engines.chart_patterns import detect_compressing_wedge, detect_rounding_bottom
from app.engines.pattern_confirmations import detect_ema20_support
from app.engines.technical import _ema
from app.ingest.yfinance_client import load_ohlcv, save_ohlcv, yahoo_ticker


def load_intraday(symbol: str, interval: str) -> pd.DataFrame | None:
    path = ohlcv_intraday_dir(interval) / f"{symbol}.parquet"
    if not path.exists():
        return None
    return load_ohlcv(path)


def fetch_intraday(symbol: str, interval: str, *, days: int = 60) -> pd.DataFrame:
    import yfinance as yf

    settings = get_settings()
    cached = ohlcv_intraday_dir(interval) / f"{symbol}.parquet"
    if settings.offline_mode and cached.exists():
        return load_ohlcv(cached)

    ticker = yahoo_ticker(symbol)
    end = datetime.now(timezone.utc)
    start = end - timedelta(days=days)
    frame = yf.download(
        ticker,
        start=start.date().isoformat(),
        end=end.date().isoformat(),
        interval=interval,
        auto_adjust=True,
        progress=False,
        threads=False,
    )
    if frame.empty:
        raise ValueError(f"No intraday data for {symbol} {interval}")

    if isinstance(frame.columns, pd.MultiIndex):
        frame.columns = [col[0].lower() for col in frame.columns]
    else:
        frame.columns = [col.lower() for col in frame.columns]
    frame.index = pd.to_datetime(frame.index).tz_localize(None)
    frame["symbol"] = symbol
    frame = frame[["open", "high", "low", "close", "volume", "symbol"]].dropna()
    save_ohlcv(frame, cached)
    return frame


def analyze_intraday_confirmations(
    symbol: str,
    as_of_date: str,
    *,
    side: str = "long",
) -> dict[str, bool]:
    """15m wedge + 1h rounding/EMA20 for the signal session."""
    out = {"mtf_15m_wedge": False, "mtf_1h_rounding_ema20": False}
    as_of = pd.Timestamp(as_of_date)
    if (pd.Timestamp.now().normalize() - as_of).days > 55:
        return out

    for interval, key, lookback in (("15m", "mtf_15m_wedge", 40), ("1h", "mtf_1h_rounding_ema20", 30)):
        try:
            frame = load_intraday(symbol, interval)
            if frame is None and not get_settings().offline_mode:
                try:
                    frame = fetch_intraday(symbol, interval)
                except Exception:
                    continue
            if frame is None:
                continue
        except Exception:
            continue

        if as_of.date() in {d.date() for d in frame.index}:
            day_slice = frame[frame.index.date == as_of.date()]
        else:
            day_slice = frame[frame.index <= as_of].tail(lookback)

        if len(day_slice) < 12:
            day_slice = frame[frame.index <= as_of].tail(lookback)
        if len(day_slice) < 12:
            continue

        window = day_slice.tail(lookback)
        if interval == "15m":
            out[key] = detect_compressing_wedge(window, side=side, lookback=min(lookback, len(window)))
        else:
            rounding = detect_rounding_bottom(window, lookback=min(lookback, len(window)))
            ema20 = _ema(window["close"], 20)
            at_ema = False
            if ema20 is not None:
                close = float(window["close"].iloc[-1])
                at_ema = abs(close - ema20) / ema20 <= 0.02 or detect_ema20_support(window, lookback=3)
            out["mtf_1h_rounding_ema20"] = rounding and at_ema

    return out
