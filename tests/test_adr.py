from app.core.paths import ohlcv_daily_dir
from app.engines.adr import attach_adr, build_adr_profiles, snapshot_adr, target_for
from app.engines.universe import load_trading_instruments
from app.ingest.yfinance_client import load_ohlcv


def test_fixed_targets_match_book() -> None:
    assert target_for("HDFCBANK") == 2.0
    assert target_for("BAJFINANCE") == 3.0
    assert target_for("M&M") == 3.0
    assert target_for("NIFTY_50") == 1.0
    assert target_for("NIFTY_BANK") == 1.2


def test_hdfc_snapshot_uses_two_percent() -> None:
    path = ohlcv_daily_dir() / "HDFCBANK.parquet"
    snap = snapshot_adr(attach_adr(load_ohlcv(path)), symbol="HDFCBANK")
    assert snap["adr20_pct"] < 5.0
    assert snap["target_range_pct"] == 2.0


def test_bajaj_adr_is_wider_than_hdfc() -> None:
    hdfc = snapshot_adr(load_ohlcv(ohlcv_daily_dir() / "HDFCBANK.parquet"), symbol="HDFCBANK")
    baj = snapshot_adr(load_ohlcv(ohlcv_daily_dir() / "BAJFINANCE.parquet"), symbol="BAJFINANCE")
    assert baj["adr20_pct"] > hdfc["adr20_pct"]
    assert baj["target_range_pct"] == 3.0


def test_adr_profiles_cover_five_scrips() -> None:
    payload = build_adr_profiles()
    symbols = [row["symbol"] for row in payload["instruments"]]
    expected = [row["symbol"] for row in load_trading_instruments()]
    assert symbols == expected
    by = {row["symbol"]: row["target_range_pct"] for row in payload["instruments"]}
    assert by["HDFCBANK"] == 2.0
    assert by["NIFTY_BANK"] == 1.2
