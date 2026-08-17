from pathlib import Path

import pandas as pd
import pytest

from app.core.config import get_settings
from app.ingest.yfinance_client import fetch_ohlcv


def test_fetch_ohlcv_uses_cache_when_offline(monkeypatch, tmp_path: Path) -> None:
    from app.core import paths
    from app.ingest import yfinance_client

    ohlcv_dir = tmp_path / "ohlcv"
    ohlcv_dir.mkdir()
    frame = pd.DataFrame(
        {
            "open": [100.0],
            "high": [101.0],
            "low": [99.0],
            "close": [100.5],
            "volume": [1_000_000],
            "symbol": ["TEST"],
        },
        index=pd.to_datetime(["2024-01-02"]),
    )
    parquet = ohlcv_dir / "TEST.parquet"
    frame.to_parquet(parquet)

    monkeypatch.setattr(paths, "ohlcv_daily_dir", lambda: ohlcv_dir)
    monkeypatch.setattr(yfinance_client, "ohlcv_daily_dir", lambda: ohlcv_dir)

    settings = get_settings()
    monkeypatch.setattr(settings, "offline_mode", True)

    def fake_get_settings():
        return settings

    monkeypatch.setattr(yfinance_client, "get_settings", fake_get_settings)

    loaded = fetch_ohlcv("TEST")
    assert len(loaded) == 1
    assert float(loaded["close"].iloc[0]) == 100.5


def test_fetch_ohlcv_offline_missing_cache_raises(monkeypatch, tmp_path: Path) -> None:
    from app.core import paths
    from app.ingest import yfinance_client

    ohlcv_dir = tmp_path / "ohlcv"
    ohlcv_dir.mkdir()
    monkeypatch.setattr(paths, "ohlcv_daily_dir", lambda: ohlcv_dir)
    monkeypatch.setattr(yfinance_client, "ohlcv_daily_dir", lambda: ohlcv_dir)

    settings = get_settings()
    monkeypatch.setattr(settings, "offline_mode", True)
    monkeypatch.setattr(yfinance_client, "get_settings", lambda: settings)

    with pytest.raises(FileNotFoundError, match="offline_mode"):
        fetch_ohlcv("MISSING")
