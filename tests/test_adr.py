import pandas as pd

from app.core.paths import ohlcv_daily_dir
from app.engines.adr import attach_adr, build_adr_profiles, snapshot_adr
from app.engines.universe import load_trading_instruments
from app.ingest.yfinance_client import load_ohlcv


def test_adr_is_not_five_percent() -> None:
    path = ohlcv_daily_dir() / "HDFCBANK.parquet"
    frame = attach_adr(load_ohlcv(path))
    snap = snapshot_adr(frame)
    assert snap["adr20_pct"] < 5.0
    assert snap["target_range_pct"] == round(snap["adr20_pct"] * snap["expansion_mult"], 2)
    assert snap["expansion_mult"] == 1.25


def test_bajaj_adr_is_wider_than_hdfc() -> None:
    hdfc = snapshot_adr(load_ohlcv(ohlcv_daily_dir() / "HDFCBANK.parquet"))
    baj = snapshot_adr(load_ohlcv(ohlcv_daily_dir() / "BAJFINANCE.parquet"))
    assert baj["adr20_pct"] > hdfc["adr20_pct"]


def test_adr_profiles_cover_five_scrips() -> None:
    payload = build_adr_profiles()
    symbols = [row["symbol"] for row in payload["instruments"]]
    expected = [row["symbol"] for row in load_trading_instruments()]
    assert symbols == expected
    for row in payload["instruments"]:
        assert row["adr20_pct"] > 0
        assert row["target_range_pct"] > row["adr20_pct"]
