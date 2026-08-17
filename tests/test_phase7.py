from app.engines.backtest import (
    _pick_recommended_combo,
    collect_backtest_signals,
    filter_backtest_signals,
    tune_backtest,
)


def test_filter_backtest_signals_applies_cooldown() -> None:
    signals = [
        {"symbol": "A", "bar_idx": 10, "conviction": 8.0, "date": "2024-01-10", "instrument_type": "stock", "hit_1d": True, "hit_1w": True},
        {"symbol": "A", "bar_idx": 12, "conviction": 8.5, "date": "2024-01-12", "instrument_type": "stock", "hit_1d": False, "hit_1w": False},
        {"symbol": "A", "bar_idx": 20, "conviction": 7.5, "date": "2024-01-20", "instrument_type": "stock", "hit_1d": True, "hit_1w": False},
        {"symbol": "B", "bar_idx": 15, "conviction": 6.5, "date": "2024-01-15", "instrument_type": "stock", "hit_1d": True, "hit_1w": True},
    ]
    filtered = filter_backtest_signals(signals, conviction_min=7.0, signal_cooldown_days=5)
    assert len(filtered) == 2
    assert {item["bar_idx"] for item in filtered} == {10, 20}


def test_pick_recommended_combo_prefers_hit_1w() -> None:
    rows = [
        {"conviction_min": 7.0, "signal_cooldown_days": 5, "summary": {"signals": 10, "hit_1w_rate": 0.4, "hit_1d_rate": 0.5}},
        {"conviction_min": 8.0, "signal_cooldown_days": 5, "summary": {"signals": 8, "hit_1w_rate": 0.6, "hit_1d_rate": 0.3}},
        {"conviction_min": 6.0, "signal_cooldown_days": 3, "summary": {"signals": 2, "hit_1w_rate": 0.9, "hit_1d_rate": 0.9}},
    ]
    recommended = _pick_recommended_combo(rows, min_signals=5)
    assert recommended["conviction_min"] == 8.0


def test_tune_backtest_writes_report(monkeypatch, tmp_path) -> None:
    from app.engines import backtest as backtest_module

    reports_dir = tmp_path / "reports"
    reports_dir.mkdir()
    monkeypatch.setattr(backtest_module, "backtest_reports_dir", lambda: reports_dir)
    monkeypatch.setattr(
        backtest_module,
        "collect_backtest_signals",
        lambda conviction_floor=None: [
            {
                "symbol": "TEST",
                "bar_idx": 40,
                "conviction": 8.0,
                "date": "2024-02-15",
                "instrument_type": "stock",
                "hit_1d": True,
                "hit_1w": True,
                "fwd_1d_pct": 6.0,
                "fwd_1w_pct": 11.0,
            },
            {
                "symbol": "TEST",
                "bar_idx": 50,
                "conviction": 7.2,
                "date": "2024-02-25",
                "instrument_type": "stock",
                "hit_1d": False,
                "hit_1w": False,
                "fwd_1d_pct": 1.0,
                "fwd_1w_pct": 2.0,
            },
        ],
    )

    payload = backtest_module.tune_backtest()
    assert len(payload["grid"]) > 0
    assert (reports_dir / "tuning_latest.json").exists()
