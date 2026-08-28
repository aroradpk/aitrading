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


def nonoverlapping_ic(signal: pd.Series, fwd: pd.Series, step: int = 10, lookback: int = 252) -> float | None:
    """IC on 10-session strides so overlapping 10d forwards do not inflate correlation."""
    df = pd.concat({"s": signal, "f": fwd}, axis=1).dropna()
    if lookback:
        df = df.iloc[-lookback:]
    sampled = df.iloc[::step]
    if len(sampled) < 12:
        return None
    return float(sampled["s"].corr(sampled["f"]))


def check_fade_distance(feat: pd.DataFrame, ic_floor: float = 0.05) -> Degradation:
    """Distance-from-52w-high as a long-the-dip signal: more negative → expect bounce."""
    sig = -feat["dist_52w_high"]
    val = nonoverlapping_ic(sig, feat["fwd_10"], step=10, lookback=252)
    if val is None:
        return Degradation("fade_52w_high", None, True, "insufficient non-overlapping history")
    degraded = val < ic_floor
    return Degradation(
        signal="fade_52w_high",
        rolling_ic=val,
        degraded=degraded,
        note=f"252d non-overlapping IC of (−dist_52w_high) vs fwd_10 = {val:.3f}",
    )
