"""Gaussian-mixture regime model with named states and entropy."""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd
from sklearn.mixture import GaussianMixture
from sklearn.preprocessing import StandardScaler

from scrl.features import REGIME_COLS


@dataclass
class RegimeSnapshot:
    date: pd.Timestamp
    state: str
    probabilities: dict[str, float]
    entropy: float
    high_entropy: bool


class RegimeModel:
    def __init__(self, n_states: int = 3, entropy_cutoff: float = 0.90, random_state: int = 42):
        self.n_states = n_states
        self.entropy_cutoff = entropy_cutoff
        self.random_state = random_state
        self.scaler = StandardScaler()
        self.gmm = GaussianMixture(
            n_components=n_states,
            covariance_type="full",
            n_init=8,
            random_state=random_state,
        )
        self.state_names: dict[int, str] = {}
        self.fitted = False

    def _prepare(self, feat: pd.DataFrame) -> pd.DataFrame:
        x = feat[REGIME_COLS].replace([np.inf, -np.inf], np.nan).dropna()
        return x

    def fit(self, feat: pd.DataFrame) -> "RegimeModel":
        x = self._prepare(feat)
        if len(x) < 80:
            raise ValueError("Need at least 80 complete regime rows to fit")
        xs = self.scaler.fit_transform(x)
        self.gmm.fit(xs)
        means = pd.DataFrame(self.scaler.inverse_transform(self.gmm.means_), columns=REGIME_COLS)
        self.state_names = _name_states(means)
        self.fitted = True
        return self

    def predict_frame(self, feat: pd.DataFrame) -> pd.DataFrame:
        if not self.fitted:
            raise RuntimeError("RegimeModel.fit first")
        x = self._prepare(feat)
        xs = self.scaler.transform(x)
        proba = self.gmm.predict_proba(xs)
        named = pd.DataFrame(0.0, index=x.index, columns=sorted(set(self.state_names.values())))
        for i, name in self.state_names.items():
            named[name] = named[name] + proba[:, i]
        named = named.div(named.sum(axis=1), axis=0)
        named["entropy"] = -(named.clip(lower=1e-12) * np.log(named.clip(lower=1e-12))).sum(axis=1)
        named["state"] = named.drop(columns=["entropy"]).idxmax(axis=1)
        named["high_entropy"] = named["entropy"] >= self.entropy_cutoff
        return named

    def snapshot(self, feat: pd.DataFrame, as_of: pd.Timestamp | None = None) -> RegimeSnapshot:
        frame = self.predict_frame(feat)
        if as_of is not None:
            frame = frame.loc[: pd.Timestamp(as_of)]
        row = frame.iloc[-1]
        probs = {c: float(row[c]) for c in frame.columns if c not in {"entropy", "state", "high_entropy"}}
        return RegimeSnapshot(
            date=frame.index[-1],
            state=str(row["state"]),
            probabilities=probs,
            entropy=float(row["entropy"]),
            high_entropy=bool(row["high_entropy"]),
        )


def _name_states(means: pd.DataFrame) -> dict[int, str]:
    """Label mixture components from their centers, not from a story."""
    names: dict[int, str] = {}
    vol_idx = int(means["bm_vol_20"].idxmax())
    names[vol_idx] = "risk_off"
    remaining = [int(i) for i in means.index if int(i) != vol_idx]
    if remaining:
        trend_idx = int(means.loc[remaining, "trend_strength"].idxmax())
        names[trend_idx] = "trend"
    for i in means.index:
        i = int(i)
        if i not in names:
            names[i] = "chop"
    return names


def shannon_entropy(probs: dict[str, float]) -> float:
    arr = np.array(list(probs.values()), dtype=float)
    arr = arr[arr > 0]
    return float(-(arr * np.log(arr)).sum())
