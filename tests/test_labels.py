from __future__ import annotations

import pandas as pd

from app.ml.labels import simulate_next_session


def test_adverse_first_when_both_levels_trade() -> None:
    bar = pd.Series({"open": 100.0, "high": 103.0, "low": 97.0, "close": 101.0})
    out = simulate_next_session("long", fill=100.0, stop=98.0, target=102.0, next_bar=bar)
    assert out.exit_reason == "stop"
    assert out.target_hit_before_stop == 0


def test_target_when_only_target_trades() -> None:
    bar = pd.Series({"open": 100.0, "high": 103.0, "low": 99.5, "close": 102.5})
    out = simulate_next_session("long", fill=100.0, stop=98.0, target=102.0, next_bar=bar)
    assert out.exit_reason == "target"
    assert out.target_hit_before_stop == 1
