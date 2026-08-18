from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pandas as pd

from app.core.config import get_settings
from app.core.paths import ohlcv_intraday_dir
from app.engines.chart_patterns import detect_compressing_wedge, detect_rounding_bottom, detect_sr_fib_confluence
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


def _session_or_tail(frame: pd.DataFrame, as_of: pd.Timestamp, lookback: int) -> pd.DataFrame:
    if as_of.date() in {d.date() for d in frame.index}:
        day_slice = frame[frame.index.date == as_of.date()]
    else:
        day_slice = frame[frame.index <= as_of].tail(lookback)
    if len(day_slice) < 12:
        day_slice = frame[frame.index <= as_of].tail(lookback)
    return day_slice.tail(lookback)


def _recent_coil(frame: pd.DataFrame, *, bars: int, max_atr: float) -> bool:
    if len(frame) < bars + 8:
        return False
    recent = frame.tail(bars)
    span = float(recent["high"].max() - recent["low"].min())
    atr = float((frame["high"] - frame["low"]).tail(20).mean())
    return atr > 0 and span / atr <= max_atr


def _near_ema20(frame: pd.DataFrame, *, tolerance_pct: float = 0.012) -> bool:
    ema20 = _ema(frame["close"], 20)
    if ema20 is None:
        return False
    close = float(frame["close"].iloc[-1])
    low = float(frame["low"].iloc[-1])
    high = float(frame["high"].iloc[-1])
    if abs(close - ema20) / ema20 <= tolerance_pct:
        return True
    if low <= ema20 <= high:
        return True
    return detect_ema20_support(frame, lookback=4, tolerance_pct=tolerance_pct)


def analyze_intraday_confirmations(
    symbol: str,
    as_of_date: str,
    *,
    side: str = "long",
) -> dict[str, bool]:
    """15m wedge/coil and 1h coil/rounding at EMA20. Hourly Fib is a cherry, not a 7-gate."""
    out = {
        "mtf_15m_wedge": False,
        "mtf_15m_coil_ema": False,
        "mtf_1h_rounding_ema20": False,
        "mtf_1h_coil_ema": False,
        "mtf_1h_fib_sr": False,
    }
    as_of = pd.Timestamp(as_of_date)
    settings = get_settings()
    age_days = (pd.Timestamp.now().normalize() - as_of.normalize()).days

    for interval, lookback in (("15m", 40), ("1h", 30)):
        frame = load_intraday(symbol, interval)
        if frame is None and not settings.offline_mode and age_days <= 55:
            try:
                frame = fetch_intraday(symbol, interval)
            except Exception:
                continue
        if frame is None:
            continue
        window = _session_or_tail(frame[frame.index <= as_of + pd.Timedelta(hours=16)], as_of, lookback)
        if len(window) < 12:
            continue
        if interval == "15m":
            out["mtf_15m_wedge"] = detect_compressing_wedge(window, side=side, lookback=min(lookback, len(window)))
            out["mtf_15m_coil_ema"] = _recent_coil(window, bars=12, max_atr=2.0) and _near_ema20(window, tolerance_pct=0.008)
        else:
            rounding = detect_rounding_bottom(window, lookback=min(lookback, len(window)))
            at_ema = _near_ema20(window, tolerance_pct=0.008)
            out["mtf_1h_rounding_ema20"] = bool(rounding and at_ema)
            out["mtf_1h_coil_ema"] = _recent_coil(window, bars=8, max_atr=1.8) and at_ema
            ema20 = _ema(window["close"], 20)
            sr_prices = [p for p in ([ema20] if ema20 else [])]
            out["mtf_1h_fib_sr"] = bool(ema20) and detect_sr_fib_confluence(
                window, side=side, sr_prices=sr_prices
            )

    return out


def has_mtf_precision(confirmations: dict[str, bool]) -> bool:
    """7 needs the user's 15m wedge + 1h rounding pair. Coils and hourly Fib are not this gate."""
    return bool(confirmations.get("mtf_15m_wedge") and confirmations.get("mtf_1h_rounding_ema20"))
