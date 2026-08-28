"""Point-in-time kNN situation retrieval. Outcomes are historical, never the future of as_of."""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd
from sklearn.neighbors import NearestNeighbors
from sklearn.preprocessing import StandardScaler

from scrl.features import RETRIEVAL_COLS


@dataclass
class AnalogSet:
    n: int
    neighbors: pd.DataFrame
    fwd_10: dict[str, float]
    fwd_excess_10: dict[str, float]
    straddles_zero: bool
    same_sign: bool
    median_10: float
    horizon_days: int = 10


def _quantiles(s: pd.Series) -> dict[str, float]:
    s = s.dropna()
    if s.empty:
        return {"p25": float("nan"), "median": float("nan"), "p75": float("nan")}
    return {
        "p25": float(s.quantile(0.25)),
        "median": float(s.median()),
        "p75": float(s.quantile(0.75)),
    }


def retrieve(
    feat: pd.DataFrame,
    as_of: pd.Timestamp | None = None,
    k: int = 25,
    min_history: int = 252,
    horizon_days: int = 10,
) -> AnalogSet:
    fwd_col = f"fwd_{horizon_days}"
    excess_col = f"fwd_excess_{horizon_days}"
    needed = RETRIEVAL_COLS + [c for c in (fwd_col, excess_col) if c in feat.columns]
    work = feat[needed].replace([np.inf, -np.inf], np.nan)
    if as_of is not None:
        work = work.loc[: pd.Timestamp(as_of)]
    current = work.iloc[[-1]]
    # Using fwd at t requires t+horizon <= as_of, so drop the last horizon rows.
    cut = horizon_days + 1
    library = work.iloc[:-cut].dropna(subset=RETRIEVAL_COLS + [fwd_col])
    query = current[RETRIEVAL_COLS].dropna(axis=1)
    cols = [c for c in RETRIEVAL_COLS if c in query.columns and query[c].notna().all()]
    library = library.dropna(subset=cols)
    if len(library) < min(k, min_history // 4):
        empty = pd.DataFrame()
        return AnalogSet(
            n=0,
            neighbors=empty,
            fwd_10=_quantiles(pd.Series(dtype=float)),
            fwd_excess_10=_quantiles(pd.Series(dtype=float)),
            straddles_zero=True,
            same_sign=False,
            median_10=float("nan"),
            horizon_days=horizon_days,
        )

    scaler = StandardScaler()
    lib_x = scaler.fit_transform(library[cols])
    q_x = scaler.transform(current[cols])
    kk = min(k, len(library))
    nn = NearestNeighbors(n_neighbors=kk, metric="euclidean")
    nn.fit(lib_x)
    dist, idx = nn.kneighbors(q_x)
    neigh = library.iloc[idx[0]].copy()
    neigh["distance"] = dist[0]
    q10 = _quantiles(neigh[fwd_col])
    qex = _quantiles(neigh[excess_col]) if excess_col in neigh.columns else _quantiles(pd.Series(dtype=float))
    straddles = bool(q10["p25"] * q10["p75"] < 0)
    same = bool(q10["p25"] * q10["p75"] > 0)
    return AnalogSet(
        n=len(neigh),
        neighbors=neigh,
        fwd_10=q10,
        fwd_excess_10=qex,
        straddles_zero=straddles,
        same_sign=same,
        median_10=q10["median"],
        horizon_days=horizon_days,
    )
