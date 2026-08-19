from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from app.backtest.engine import BacktestConfig
from app.backtest.walkforward import walk_forward
from app.config import get_settings
from app.data.store import Store
from app.features.technical import wide_features
from app.ml.models import load_model, save_model, train_select
from app.pipeline.prepare import compute_feature_frames, latest_asof, model_matrix, prepare_all, score_candidates
from app.report.daily import render_daily_report
from app.universe import UNIVERSE


def run_train_and_backtest() -> dict:
    settings = get_settings()
    feature_frames = prepare_all(settings)
    store = Store(settings.db_path)
    try:
        matrix = model_matrix(store)
        candidates = store.load_candidates()
        features_wide = wide_features(store.load_features())
        bars = {
            item.symbol: feature_frames[item.symbol][["date", "open", "high", "low", "close", "volume"]]
            for item in UNIVERSE
        }
        config = BacktestConfig(
            initial_capital=settings.initial_capital,
            risk_fraction=settings.risk_fraction,
            max_concurrent=settings.max_concurrent,
            min_probability=0.0,
        )
        trades, report, model = walk_forward(
            matrix, candidates, bars, features_wide, settings.artifact_dir, config
        )
        store.replace_backtest_trades(trades)
        prod_model = model
        dates = sorted(matrix["asof_date"].unique()) if not matrix.empty else []
        if len(dates) >= 50:
            cut = dates[int(len(dates) * 0.8)]
            prod_train = matrix[matrix["asof_date"] < cut]
            prod_valid = matrix[matrix["asof_date"] >= cut]
            if len(prod_train) >= 40 and len(prod_valid) >= 8:
                prod_model = train_select(prod_train, prod_valid)
                report["production_model"] = {
                    "name": prod_model.name,
                    "valid_logloss": prod_model.valid_logloss,
                    "valid_auc": prod_model.valid_auc,
                    "note": "Production scorer is fit on labeled history with a held-out recent validation slice. OOS trade metrics remain walk-forward test folds only.",
                }
        if prod_model is not None:
            artifact = settings.artifact_dir / f"latest_{prod_model.name}.joblib"
            save_model(prod_model, artifact)
            fold = report["folds"][-1] if report["folds"] else {}
            run_id = store.insert_model_run(
                created_at=datetime.now(timezone.utc).isoformat(),
                model_type=prod_model.name,
                train_end=str(fold.get("train_end", "")),
                valid_end=str(fold.get("valid_end", "")),
                test_end=str(fold.get("test_end", "")),
                metrics_json=json.dumps(report["oos_overall"]),
                feature_names_json=json.dumps(prod_model.feature_names),
                artifact_path=str(artifact),
            )
            scored = score_candidates(store, prod_model)
            if not scored.empty and "id" in scored.columns:
                store.replace_predictions(
                    run_id,
                    list(zip(scored["id"].astype(int), scored["probability"].astype(float), strict=False)),
                )
        return report
    finally:
        store.close()


def run_daily_report(asof=None) -> str:
    settings = get_settings()
    store = Store(settings.db_path)
    try:
        feature_frames = compute_feature_frames(store)
        run = store.latest_model_run()
        if run is None:
            raise RuntimeError("Train a model before writing the daily report.")
        model = load_model(Path(run["artifact_path"]))
        scored = score_candidates(store, model)
        if scored.empty:
            asof = asof or latest_asof(feature_frames)
            day = scored
        else:
            asof = asof or scored["asof_date"].max()
            day = scored[scored["asof_date"] == asof]
        path = settings.artifact_dir / f"daily_report_{asof.isoformat()}.md"
        return render_daily_report(day, asof, path, top_n=settings.top_n)
    finally:
        store.close()
