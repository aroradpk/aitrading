from __future__ import annotations

from datetime import date, timedelta
from pathlib import Path

import pytest

from app.data.ingest import ingest_yahoo
from app.data.store import Store
from app.universe import UNIVERSE


@pytest.fixture()
def yahoo_store(tmp_path: Path) -> Store:
    return Store(tmp_path / "yahoo.db")


def test_yahoo_history_through_yesterday(yahoo_store: Store) -> None:
    yesterday = date.today() - timedelta(days=1)
    ingest_yahoo(yahoo_store, lookback_days=1500, end=yesterday)
    for item in UNIVERSE:
        frame = yahoo_store.load_daily(item.symbol)
        assert not frame.empty, f"missing bars for {item.symbol}"
        assert frame["date"].min() < date(2023, 1, 1), f"{item.symbol} history is too short"
        assert frame["date"].max() <= yesterday
        assert (frame["high"] >= frame["low"]).all()
        assert (frame["high"] >= frame["close"]).all()
        assert (frame["low"] <= frame["close"]).all()
    yahoo_store.close()
