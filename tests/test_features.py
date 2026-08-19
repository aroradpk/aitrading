from __future__ import annotations

from datetime import date

import pandas as pd

from app.features.technical import features_for_symbol


def _bars(n: int = 120) -> pd.DataFrame:
    idx = pd.Series(range(n)).astype(float)
    close = 100 + idx * 0.05 + (idx % 7 - 3) * 0.4
    return pd.DataFrame(
        {
            "date": pd.bdate_range("2023-01-02", periods=n).date,
            "open": close - 0.2,
            "high": close + 0.5,
            "low": close - 0.5,
            "close": close,
            "volume": 100_000.0,
        }
    )


def test_features_do_not_use_future_bars() -> None:
    frame = _bars()
    base = features_for_symbol(frame)
    asof = base.loc[60, "date"]
    snapshot = base.loc[60, ["rsi_14", "sma_20", "ret_5", "atr_14"]].to_dict()
    assert all(pd.notna(value) for value in snapshot.values())
    mutated = frame.copy()
    mutated.loc[61:, "close"] = mutated.loc[61:, "close"] * 1.5
    mutated.loc[61:, "high"] = mutated.loc[61:, "high"] * 1.5
    again = features_for_symbol(mutated)
    row = again[again["date"] == asof].iloc[0]
    for key, value in snapshot.items():
        assert abs(float(row[key]) - float(value)) < 1e-12
