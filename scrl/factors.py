"""Rolling OLS factor residual: equity ~ benchmark + brent + fx."""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

from scrl.data import MarketBundle


@dataclass
class FactorSnapshot:
    date: pd.Timestamp
    residual_20: float
    beta_benchmark: float
    beta_brent: float
    beta_fx: float
    r_squared: float
    brent_20: float
    equity_20: float
    benchmark_20: float


def rolling_factor_residual(bundle: MarketBundle, window: int = 60) -> pd.DataFrame:
    px = bundle.aligned_frame()
    y = px["equity"].pct_change()
    x = pd.DataFrame(
        {
            "benchmark": px["benchmark"].pct_change(),
            "brent": px["brent"].pct_change(),
            "usd_inr": px["usd_inr"].pct_change(),
        }
    )
    rows = []
    idx = []
    for i in range(window, len(px)):
        sl = slice(i - window, i)
        yy = y.iloc[sl].to_numpy()
        xx = x.iloc[sl].to_numpy()
        mask = np.isfinite(yy) & np.isfinite(xx).all(axis=1)
        yy, xx = yy[mask], xx[mask]
        if len(yy) < window * 0.8:
            continue
        xx = np.column_stack([np.ones(len(yy)), xx])
        try:
            coef, *_ = np.linalg.lstsq(xx, yy, rcond=None)
        except np.linalg.LinAlgError:
            continue
        fitted = xx @ coef
        ss_res = float(((yy - fitted) ** 2).sum())
        ss_tot = float(((yy - yy.mean()) ** 2).sum())
        r2 = 1.0 - ss_res / ss_tot if ss_tot > 0 else 0.0
        last_x = np.array([1.0, x.iloc[i - 1]["benchmark"], x.iloc[i - 1]["brent"], x.iloc[i - 1]["usd_inr"]])
        pred = float(last_x @ coef)
        resid = float(y.iloc[i - 1] - pred) if np.isfinite(y.iloc[i - 1]) else np.nan
        rows.append(
            {
                "beta_benchmark": float(coef[1]),
                "beta_brent": float(coef[2]),
                "beta_fx": float(coef[3]),
                "r_squared": r2,
                "resid_1": resid,
            }
        )
        idx.append(px.index[i - 1])
    out = pd.DataFrame(rows, index=pd.DatetimeIndex(idx))
    out["resid_20"] = out["resid_1"].rolling(20).sum()
    out["brent_20"] = px["brent"].pct_change(20).reindex(out.index)
    out["equity_20"] = px["equity"].pct_change(20).reindex(out.index)
    out["benchmark_20"] = px["benchmark"].pct_change(20).reindex(out.index)
    return out


def snapshot(factors: pd.DataFrame, as_of: pd.Timestamp | None = None) -> FactorSnapshot:
    frame = factors.dropna(subset=["resid_20"])
    if as_of is not None:
        frame = frame.loc[: pd.Timestamp(as_of)]
    row = frame.iloc[-1]
    return FactorSnapshot(
        date=frame.index[-1],
        residual_20=float(row["resid_20"]),
        beta_benchmark=float(row["beta_benchmark"]),
        beta_brent=float(row["beta_brent"]),
        beta_fx=float(row["beta_fx"]),
        r_squared=float(row["r_squared"]),
        brent_20=float(row["brent_20"]),
        equity_20=float(row["equity_20"]),
        benchmark_20=float(row["benchmark_20"]),
    )
