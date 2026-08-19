from __future__ import annotations

from dataclasses import dataclass
from datetime import date

import pandas as pd


@dataclass(frozen=True)
class Bar:
    symbol: str
    date: date
    open: float
    high: float
    low: float
    close: float
    volume: float


def bars_to_frame(rows: list[Bar]) -> pd.DataFrame:
    if not rows:
        return pd.DataFrame(columns=["symbol", "date", "open", "high", "low", "close", "volume"])
    frame = pd.DataFrame([row.__dict__ for row in rows])
    frame["date"] = pd.to_datetime(frame["date"]).dt.date
    return frame.sort_values(["symbol", "date"]).reset_index(drop=True)
