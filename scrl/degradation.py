"""Rolling information-coefficient decay for a published signal."""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd


@dataclass
class Degradation:
    signal: str
    rolling_ic: float | None
    degraded: bool
    note: str


def rolling_ic(signal: pd.Series, fwd: pd.Series, window: int = 60) -> pd.Series:
    df = pd.concat({"s": signal, "f": fwd}, axis=1).dropna()
    return df["s"].rolling(window).corr(df["f"])


def check_fade_distance(feat: pd.DataFrame, window: int = 60, ic_floor: float = 0.02) -> Degradation:
    """Distance-from-52w-high as a long-the-dip signal: more negative → expect bounce."""
    sig = -feat["dist_52w_high"]
    ic = rolling_ic(sig, feat["fwd_10"], window=window)
    last = ic.dropna()
    if last.empty:
        return Degradation("fade_52w_high", None, True, "insufficient history")
    val = float(last.iloc[-1])
    degraded = val < ic_floor
    return Degradation(
        signal="fade_52w_high",
        rolling_ic=val,
        degraded=degraded,
        note=f"60d IC of (−dist_52w_high) vs fwd_10 = {val:.3f}",
    )
