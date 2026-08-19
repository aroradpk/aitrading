from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import date
from typing import Protocol

import pandas as pd


@dataclass
class Candidate:
    asof_date: date
    symbol: str
    strategy: str
    side: str
    entry_price: float
    stop_price: float
    target_price: float
    reward_risk: float
    supporting: list[str] = field(default_factory=list)
    risks: list[str] = field(default_factory=list)
    invalidation: str = "Invalid if next session opens through the stop or the structure breaks at the open."
    entry_condition: str = "Enter at next session open."

    def to_row(self) -> dict:
        return {
            "asof_date": self.asof_date.isoformat(),
            "symbol": self.symbol,
            "strategy": self.strategy,
            "side": self.side,
            "entry_price": self.entry_price,
            "stop_price": self.stop_price,
            "target_price": self.target_price,
            "reward_risk": self.reward_risk,
            "supporting_json": json.dumps(self.supporting),
            "risk_json": json.dumps(self.risks),
            "invalidation": self.invalidation,
            "entry_condition": self.entry_condition,
        }


class Strategy(Protocol):
    name: str

    def generate(self, row: pd.Series) -> Candidate | None:
        ...


def rr_prices(close: float, side: str, stop_pct: float, target_pct: float) -> tuple[float, float, float]:
    if side == "long":
        stop = close * (1 - stop_pct)
        target = close * (1 + target_pct)
    else:
        stop = close * (1 + stop_pct)
        target = close * (1 - target_pct)
    rr = target_pct / stop_pct if stop_pct else 0.0
    return stop, target, rr
