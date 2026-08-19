from __future__ import annotations

from datetime import date

import pandas as pd

from app.backtest.costs import CostModel, round_trip_cost
from app.ml.dataset import chronological_folds, split_frame


def test_equity_round_trip_cost_is_positive() -> None:
    cost = round_trip_cost(100_000, 101_000, "BAJFINANCE", CostModel(slippage_bps=3.0))
    assert cost > 0


def test_index_cost_profile_differs_from_equity() -> None:
    model = CostModel()
    equity = round_trip_cost(100_000, 100_000, "BAJFINANCE", model)
    index = round_trip_cost(100_000, 100_000, "NIFTY", model)
    assert equity != index


def test_walk_forward_folds_do_not_overlap() -> None:
    dates = pd.bdate_range("2022-01-03", periods=500).date.tolist()
    folds = chronological_folds(dates, train_days=252, valid_days=63, test_days=63, step_days=63)
    assert folds
    for train_start, train_end, valid_end, test_end in folds:
        assert train_start < train_end <= valid_end <= test_end
        frame = pd.DataFrame({"asof_date": dates})
        train = split_frame(frame, train_start, train_end)
        valid = split_frame(frame, train_end, valid_end)
        test = split_frame(frame, valid_end, test_end)
        train_set = set(train["asof_date"])
        valid_set = set(valid["asof_date"])
        test_set = set(test["asof_date"])
        assert not train_set & valid_set
        assert not valid_set & test_set
        assert not train_set & test_set
