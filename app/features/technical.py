from __future__ import annotations

import numpy as np
import pandas as pd

from app.universe import BANKNIFTY, NIFTY


def _rsi(close: pd.Series, length: int = 14) -> pd.Series:
    delta = close.diff()
    gain = delta.clip(lower=0.0)
    loss = -delta.clip(upper=0.0)
    avg_gain = gain.ewm(alpha=1 / length, min_periods=length, adjust=False).mean()
    avg_loss = loss.ewm(alpha=1 / length, min_periods=length, adjust=False).mean()
    rs = avg_gain / avg_loss.replace(0.0, np.nan)
    rsi = 100 - (100 / (1 + rs))
    rsi = rsi.mask((avg_loss == 0) & (avg_gain > 0), 100.0)
    rsi = rsi.mask((avg_gain == 0) & (avg_loss > 0), 0.0)
    return rsi


def _true_range(frame: pd.DataFrame) -> pd.Series:
    prev_close = frame["close"].shift(1)
    ranges = pd.concat(
        [
            frame["high"] - frame["low"],
            (frame["high"] - prev_close).abs(),
            (frame["low"] - prev_close).abs(),
        ],
        axis=1,
    )
    return ranges.max(axis=1)


def features_for_symbol(frame: pd.DataFrame) -> pd.DataFrame:
    """Compute as-of-close features. All rolling windows end at the current row."""
    out = frame.copy().sort_values("date").reset_index(drop=True)
    close = out["close"]
    out["ret_1"] = close.pct_change(1)
    out["ret_5"] = close.pct_change(5)
    out["ret_10"] = close.pct_change(10)
    out["ret_20"] = close.pct_change(20)
    out["atr_14"] = _true_range(out).rolling(14, min_periods=14).mean()
    out["atr_pct"] = out["atr_14"] / close
    out["atr_percentile_60"] = out["atr_pct"].rolling(60, min_periods=30).rank(pct=True)
    out["rsi_14"] = _rsi(close, 14)
    typical = (out["high"] + out["low"] + close) / 3.0
    vwap_num = (typical * out["volume"]).rolling(20, min_periods=20).sum()
    vwap_den = out["volume"].rolling(20, min_periods=20).sum().replace(0.0, np.nan)
    out["vwap_20"] = vwap_num / vwap_den
    out["vwap_dev"] = close / out["vwap_20"] - 1.0
    out["sma_20"] = close.rolling(20, min_periods=20).mean()
    out["sma_50"] = close.rolling(50, min_periods=50).mean()
    out["ema_20"] = close.ewm(span=20, adjust=False).mean()
    out["sma_20_dist"] = close / out["sma_20"] - 1.0
    out["sma_50_dist"] = close / out["sma_50"] - 1.0
    out["ema_20_dist"] = close / out["ema_20"] - 1.0
    out["vol_20"] = out["ret_1"].rolling(20, min_periods=20).std()
    out["volume_sma_20"] = out["volume"].rolling(20, min_periods=20).mean()
    out["volume_ratio"] = out["volume"] / out["volume_sma_20"].replace(0.0, np.nan)
    prev_close = close.shift(1)
    out["gap"] = out["open"] / prev_close - 1.0
    rng = (out["high"] - out["low"]).replace(0.0, np.nan)
    out["range_pos"] = (close - out["low"]) / rng
    out["high_20"] = out["high"].rolling(20, min_periods=20).max()
    out["low_20"] = out["low"].rolling(20, min_periods=20).min()
    out["dist_20d_high"] = close / out["high_20"] - 1.0
    out["dist_20d_low"] = close / out["low_20"] - 1.0
    out["up_days_3"] = (out["ret_1"] > 0).rolling(3, min_periods=3).sum()
    out["down_days_3"] = (out["ret_1"] < 0).rolling(3, min_periods=3).sum()
    out["weekday"] = pd.to_datetime(out["date"]).dt.weekday.astype(float)
    out["month"] = pd.to_datetime(out["date"]).dt.month.astype(float)
    return out


FEATURE_COLUMNS = [
    "ret_1",
    "ret_5",
    "ret_10",
    "ret_20",
    "atr_pct",
    "atr_percentile_60",
    "rsi_14",
    "vwap_dev",
    "sma_20_dist",
    "sma_50_dist",
    "ema_20_dist",
    "vol_20",
    "volume_ratio",
    "gap",
    "range_pos",
    "dist_20d_high",
    "dist_20d_low",
    "up_days_3",
    "down_days_3",
    "weekday",
    "month",
    "nifty_ret_1",
    "nifty_ret_5",
    "nifty_sma_20_dist",
    "banknifty_ret_1",
    "banknifty_ret_5",
    "rs_vs_nifty_5",
    "rs_vs_nifty_20",
]


def attach_context(frames: dict[str, pd.DataFrame]) -> dict[str, pd.DataFrame]:
    nifty = frames[NIFTY.symbol][["date", "ret_1", "ret_5", "sma_20_dist"]].rename(
        columns={
            "ret_1": "nifty_ret_1",
            "ret_5": "nifty_ret_5",
            "sma_20_dist": "nifty_sma_20_dist",
        }
    )
    bank = frames[BANKNIFTY.symbol][["date", "ret_1", "ret_5"]].rename(
        columns={"ret_1": "banknifty_ret_1", "ret_5": "banknifty_ret_5"}
    )
    enriched: dict[str, pd.DataFrame] = {}
    for symbol, frame in frames.items():
        merged = frame.merge(nifty, on="date", how="left").merge(bank, on="date", how="left")
        nifty_ret20 = frames[NIFTY.symbol][["date", "ret_20"]].rename(columns={"ret_20": "nifty_ret_20"})
        merged = merged.merge(nifty_ret20, on="date", how="left")
        merged["rs_vs_nifty_5"] = merged["ret_5"] - merged["nifty_ret_5"]
        merged["rs_vs_nifty_20"] = merged["ret_20"] - merged["nifty_ret_20"]
        merged["symbol"] = symbol
        enriched[symbol] = merged
    return enriched


def long_feature_table(frames: dict[str, pd.DataFrame]) -> pd.DataFrame:
    rows = []
    for symbol, frame in frames.items():
        usable = frame.dropna(subset=["sma_50", "atr_14", "rsi_14", "vwap_20"]).copy()
        for _, row in usable.iterrows():
            for name in FEATURE_COLUMNS:
                if name not in row:
                    continue
                value = row[name]
                if pd.isna(value):
                    continue
                rows.append(
                    {
                        "symbol": symbol,
                        "asof_date": row["date"],
                        "name": name,
                        "value": float(value),
                    }
                )
    return pd.DataFrame(rows)


def wide_features(long_frame: pd.DataFrame) -> pd.DataFrame:
    if long_frame.empty:
        return long_frame
    wide = long_frame.pivot_table(
        index=["symbol", "asof_date"], columns="name", values="value", aggfunc="first"
    ).reset_index()
    wide.columns.name = None
    return wide


def regime_label(nifty_row: pd.Series) -> str:
    ret = float(nifty_row.get("nifty_ret_5", nifty_row.get("ret_5", 0.0)))
    vol = float(nifty_row.get("vol_20", 0.01))
    trend = "bull" if ret > 0.008 else "bear" if ret < -0.008 else "sideways"
    vol_bucket = "highvol" if vol > 0.012 else "lowvol"
    return f"{trend}_{vol_bucket}"
