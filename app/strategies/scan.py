from __future__ import annotations

from datetime import date

import pandas as pd

from app.strategies.base import Candidate
from app.strategies.registry import get_strategies


def generate_candidates(feature_frames: dict[str, pd.DataFrame], asof: date | None = None) -> list[Candidate]:
    strategies = get_strategies()
    found: list[Candidate] = []
    for frame in feature_frames.values():
        subset = frame
        if asof is not None:
            subset = frame[frame["date"] == asof]
        for _, row in subset.iterrows():
            if pd.isna(row.get("sma_50")) or pd.isna(row.get("rsi_14")):
                continue
            for strategy in strategies:
                candidate = strategy.generate(row)
                if candidate is not None:
                    found.append(candidate)
    return found
