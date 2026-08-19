from __future__ import annotations

from datetime import date

import pandas as pd

from app.strategies.base import Candidate
from app.strategies.ema_rsi_expansion import detect_daily_setups, setups_to_candidates
from app.strategies.registry import get_strategies


def generate_candidates(
    feature_frames: dict[str, pd.DataFrame],
    asof: date | None = None,
    names: list[str] | None = None,
) -> list[Candidate]:
    strategies = get_strategies(names)
    found: list[Candidate] = []
    s1 = [item for item in strategies if item.name == "ema_rsi_expansion"]
    others = [item for item in strategies if item.name != "ema_rsi_expansion"]
    for frame in feature_frames.values():
        subset = frame if asof is None else frame[frame["date"] == asof]
        if s1:
            symbol = str(frame["symbol"].iloc[0]) if "symbol" in frame.columns else ""
            setups = detect_daily_setups(frame, symbol, getattr(s1[0], "cfg", None))
            if asof is not None:
                setups = [item for item in setups if item.asof_date == asof]
            found.extend(setups_to_candidates(setups, getattr(s1[0], "cfg", None)))
        for _, row in subset.iterrows():
            if pd.isna(row.get("sma_50")) or pd.isna(row.get("rsi_14")):
                continue
            for strategy in others:
                candidate = strategy.generate(row)
                if candidate is not None:
                    found.append(candidate)
    return found
