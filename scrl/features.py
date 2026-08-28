"""Point-in-time features. Every row uses only information available at that close."""

from __future__ import annotations

import numpy as np
import pandas as pd

from scrl.data import MarketBundle


def _rolling_vol(returns: pd.Series, window: int) -> pd.Series:
    return returns.rolling(window).std() * np.sqrt(252)


def build_features(bundle: MarketBundle, as_of: pd.Timestamp | None = None) -> pd.DataFrame:
    px = bundle.aligned_frame()
    if as_of is not None:
        px = px.loc[: pd.Timestamp(as_of)]

    eq = px["equity"].pct_change()
    bm = px["benchmark"].pct_change()
    br = px["brent"].pct_change()
    fx = px["usd_inr"].pct_change()

    feat = pd.DataFrame(index=px.index)
    feat["eq_ret_1"] = eq
    feat["eq_ret_5"] = px["equity"].pct_change(5)
    feat["eq_ret_20"] = px["equity"].pct_change(20)
    feat["bm_ret_5"] = px["benchmark"].pct_change(5)
    feat["bm_ret_20"] = px["benchmark"].pct_change(20)
    feat["brent_ret_20"] = px["brent"].pct_change(20)
    feat["fx_ret_20"] = px["usd_inr"].pct_change(20)
    feat["eq_vol_20"] = _rolling_vol(eq, 20)
    feat["bm_vol_20"] = _rolling_vol(bm, 20)
    feat["bm_vol_of_vol"] = feat["bm_vol_20"].rolling(20).std()
    feat["excess_20"] = feat["eq_ret_20"] - feat["bm_ret_20"]
    ma20 = px["equity"].rolling(20).mean()
    feat["dist_ma20"] = px["equity"] / ma20 - 1.0
    high_252 = px["equity"].rolling(252, min_periods=60).max()
    low_252 = px["equity"].rolling(252, min_periods=60).min()
    feat["dist_52w_high"] = px["equity"] / high_252 - 1.0
    feat["dist_52w_low"] = px["equity"] / low_252 - 1.0
    rng = px["equity"].rolling(20).max() - px["equity"].rolling(20).min()
    feat["range_20"] = rng / px["equity"]
    trend_strength = feat["bm_ret_20"].abs() / feat["bm_vol_20"].replace(0, np.nan) * np.sqrt(252)
    feat["trend_strength"] = trend_strength
    feat["close"] = px["equity"]
    feat["bm_close"] = px["benchmark"]
    feat["brent_close"] = px["brent"]
    feat["usd_inr"] = px["usd_inr"]

    # Forward returns used only for analog *outcomes of past episodes* and walk-forward.
    # They are shifted so they never enter the feature vector used at time t.
    feat["fwd_5"] = px["equity"].pct_change(5).shift(-5)
    feat["fwd_10"] = px["equity"].pct_change(10).shift(-10)
    feat["fwd_20"] = px["equity"].pct_change(20).shift(-20)
    feat["fwd_excess_10"] = (px["equity"].pct_change(10) - px["benchmark"].pct_change(10)).shift(-10)
    feat["fwd_bm_5"] = px["benchmark"].pct_change(5).shift(-5)
    return feat


REGIME_COLS = ["bm_ret_20", "bm_vol_20", "brent_ret_20", "trend_strength", "bm_vol_of_vol"]
RETRIEVAL_COLS = [
    "eq_ret_20",
    "bm_ret_20",
    "excess_20",
    "eq_vol_20",
    "bm_vol_20",
    "brent_ret_20",
    "dist_ma20",
    "dist_52w_high",
    "range_20",
    "trend_strength",
]
