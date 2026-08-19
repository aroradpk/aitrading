from __future__ import annotations

from datetime import date

import pandas as pd

from app.ai.analyst import critique_setup
from app.strategies.base import Candidate, rr_prices
from app.strategies.exhaustion import ExhaustionReversal
from app.strategies.index_aligned import IndexAlignedMomentum


def _row(**kwargs) -> pd.Series:
    base = {
        "date": date(2024, 6, 3),
        "symbol": "NIFTY",
        "close": 18000.0,
        "rsi_14": 25.0,
        "range_pos": 0.1,
        "atr_pct": 0.01,
        "down_days_3": 3,
        "up_days_3": 0,
        "nifty_sma_20_dist": 0.0,
    }
    base.update(kwargs)
    return pd.Series(base)


def test_exhaustion_fires_long() -> None:
    cand = ExhaustionReversal().generate(_row())
    assert cand is not None
    assert cand.side == "long"
    assert cand.reward_risk > 1


def test_index_aligned_only_bajaj() -> None:
    row = _row(
        symbol="NIFTY",
        ret_5=0.04,
        rs_vs_nifty_5=0.02,
        nifty_sma_20_dist=0.01,
        banknifty_ret_5=0.02,
        rsi_14=60.0,
    )
    assert IndexAlignedMomentum().generate(row) is None


def test_rr_prices_long() -> None:
    stop, target, rr = rr_prices(100, "long", 0.01, 0.02)
    assert stop == 99
    assert target == 102
    assert rr == 2


def test_critic_can_reject_stretched_index() -> None:
    cand = Candidate(
        asof_date=date(2024, 6, 3),
        symbol="NIFTY",
        strategy="exhaustion_reversal",
        side="short",
        entry_price=18000,
        stop_price=18180,
        target_price=17712,
        reward_risk=1.6,
        supporting=["overbought"],
        risks=["Nifty is extended above its 20-day average."],
    )
    out = critique_setup(cand, 0.82, news=[])
    assert out.accept is False
