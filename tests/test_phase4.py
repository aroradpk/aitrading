import json
from datetime import date
from pathlib import Path

import pandas as pd

from app.engines.backtest import _aggregate_summary, _evaluate_signal, _forward_return


def _make_frame(prices: list[float]) -> pd.DataFrame:
    dates = pd.date_range("2024-01-01", periods=len(prices), freq="B")
    return pd.DataFrame(
        {
            "open": prices,
            "high": [p + 1 for p in prices],
            "low": [p - 1 for p in prices],
            "close": prices,
            "volume": [1_000_000] * len(prices),
            "symbol": ["TEST"] * len(prices),
        },
        index=dates,
    )


def test_forward_return() -> None:
    frame = _make_frame([100.0] * 10)
    frame.iloc[5, frame.columns.get_loc("close")] = 100.0
    frame.iloc[6, frame.columns.get_loc("close")] = 106.0
    assert _forward_return(frame, 5, 1) == 6.0


def test_aggregate_summary_hit_rates() -> None:
    signals = [
        {"conviction": 8.5, "instrument_type": "stock", "hit_1d": True, "hit_1w": False, "fwd_1d_pct": 6.0, "fwd_1w_pct": 4.0},
        {"conviction": 7.2, "instrument_type": "stock", "hit_1d": False, "hit_1w": True, "fwd_1d_pct": 1.0, "fwd_1w_pct": 12.0},
    ]
    summary = _aggregate_summary(signals)
    assert summary["signals"] == 2
    assert summary["hit_1d_rate"] == 0.5
    assert summary["hit_1w_rate"] == 0.5
    assert "8-9" in summary["by_conviction_bucket"]


def test_evaluate_signal_respects_conviction_min(monkeypatch) -> None:
    from app.engines import backtest as backtest_module

    frame = _make_frame([100 + i * 0.5 for i in range(80)])
    monkeypatch.setattr(
        backtest_module,
        "scan_today_setup",
        lambda f, moves: {
            "technical_score": 3.0,
            "match_count": 0,
            "top_matches": [],
            "current_snapshot": {},
            "as_of": f.index[-1].date().isoformat(),
        },
    )
    signal = _evaluate_signal(
        frame,
        40,
        symbol="TEST",
        instrument_type="stock",
        historical_moves=[],
        conviction_min=7.0,
        layer_cache={},
    )
    assert signal is None


def test_run_backtest_writes_report(monkeypatch, tmp_path: Path) -> None:
    from app.engines import backtest as backtest_module

    reports_dir = tmp_path / "reports"
    reports_dir.mkdir()
    ohlcv_dir = tmp_path / "ohlcv"
    ohlcv_dir.mkdir()
    frame = _make_frame([100 + i for i in range(60)])
    frame.to_parquet(ohlcv_dir / "TEST.parquet")

    monkeypatch.setattr(backtest_module, "backtest_reports_dir", lambda: reports_dir)
    monkeypatch.setattr(backtest_module, "ohlcv_daily_dir", lambda: ohlcv_dir)
    monkeypatch.setattr(backtest_module, "load_moves", lambda symbol=None: [])
    monkeypatch.setattr(backtest_module, "load_ohlcv", lambda path: pd.read_parquet(path))
    monkeypatch.setattr(
        backtest_module,
        "all_instruments",
        lambda: [{"symbol": "TEST", "type": "stock", "name": "Test"}],
    )

    calls = {"n": 0}

    def fake_evaluate(*args, **kwargs):
        calls["n"] += 1
        if calls["n"] == 1:
            return {
                "symbol": "TEST",
                "date": "2024-02-15",
                "bar_idx": 40,
                "instrument_type": "stock",
                "conviction": 8.0,
                "scores": {"technical": 8.0, "fundamental": 0, "events": 0, "theme": 0, "final": 8.0},
                "match_count": 2,
                "entry_close": 120.0,
                "fwd_1d_pct": 6.0,
                "fwd_1w_pct": 11.0,
                "target_1d_pct": 5.0,
                "target_1w_pct": 10.0,
                "hit_1d": True,
                "hit_1w": True,
            }
        return None

    monkeypatch.setattr(backtest_module, "_evaluate_signal", fake_evaluate)

    payload = backtest_module.run_backtest()
    assert payload["summary"]["signals"] >= 1
    assert (reports_dir / "latest.json").exists()
