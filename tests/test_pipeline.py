from __future__ import annotations

import os
from pathlib import Path

import pytest

from app.config import Settings
from app.data.ingest import ingest_synthetic
from app.data.store import Store
from app.pipeline.prepare import persist_candidates, persist_features, persist_labels, compute_feature_frames, model_matrix
from app.pipeline.train import run_train_and_backtest
from app.report.daily import render_daily_report


@pytest.fixture()
def isolated_settings(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Settings:
    db = tmp_path / "engine.db"
    art = tmp_path / "artifacts"
    monkeypatch.setenv("NSE_DB_PATH", str(db))
    monkeypatch.setenv("NSE_ARTIFACT_DIR", str(art))
    settings = Settings(db_path=db, artifact_dir=art)
    settings.ensure_dirs()
    return settings


def test_synthetic_pipeline_produces_oos_report(isolated_settings: Settings) -> None:
    store = Store(isolated_settings.db_path)
    ingest_synthetic(store, n_days=650, seed=11)
    frames = compute_feature_frames(store)
    persist_features(store, frames)
    candidates = persist_candidates(store, frames)
    assert not candidates.empty
    labels = persist_labels(store, frames)
    assert not labels.empty
    matrix = model_matrix(store)
    assert "target_hit_before_stop" in matrix.columns
    assert matrix["asof_date"].max() >= candidates["asof_date"].min()
    store.close()

    report = run_train_and_backtest()
    assert "oos_overall" in report
    assert "folds" in report
    overall = report["oos_overall"]
    assert "win_rate" in overall
    assert "expectancy" in overall
    assert "profit_factor" in overall
    assert "cagr" in overall
    assert "max_drawdown" in overall
    assert "sharpe" in overall
    assert "avg_trade" in overall
    assert "max_losing_streak" in overall
    assert "trades" in overall
    path = isolated_settings.artifact_dir / "walkforward_report.json"
    assert path.exists()


def test_daily_report_format(tmp_path: Path) -> None:
    import pandas as pd
    from datetime import date

    scored = pd.DataFrame(
        [
            {
                "asof_date": date(2024, 6, 3),
                "symbol": "BAJFINANCE",
                "strategy": "trend_pullback",
                "side": "long",
                "entry_price": 7000.0,
                "stop_price": 6900.0,
                "target_price": 7180.0,
                "reward_risk": 1.8,
                "probability": 0.61,
                "supporting_json": '["Pullback into EMA"]',
                "risk_json": '["Failed bounce"]',
                "invalidation": "Invalid if open through stop.",
            }
        ]
    )
    text = render_daily_report(scored, date(2024, 6, 3), tmp_path / "r.md")
    assert "Top 5 Next-Day Setups" in text
    assert "BAJFINANCE" in text
    assert "0.61" in text
    assert "Invalidation" in text
