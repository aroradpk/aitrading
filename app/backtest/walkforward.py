from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

from app.backtest.engine import BacktestConfig, run_backtest
from app.backtest.metrics import by_regime, by_year, summarize_trades
from app.ml.dataset import chronological_folds, split_frame
from app.ml.models import save_model, train_select


def walk_forward(
    model_frame: pd.DataFrame,
    candidates: pd.DataFrame,
    bars: dict[str, pd.DataFrame],
    features_wide: pd.DataFrame,
    artifact_dir: Path,
    config: BacktestConfig,
) -> tuple[pd.DataFrame, dict, object | None]:
    dates = sorted(model_frame["asof_date"].unique())
    folds = chronological_folds(dates)
    if not folds:
        train_cut = dates[int(len(dates) * 0.6)]
        valid_cut = dates[int(len(dates) * 0.8)]
        end = dates[-1]
        from datetime import timedelta

        folds = [(dates[0], train_cut, valid_cut, end + timedelta(days=1))]
    all_trades = []
    fold_reports = []
    last_model = None
    merged_candidates = candidates.merge(
        model_frame[["candidate_id", "target_hit_before_stop"]],
        left_on="id",
        right_on="candidate_id",
        how="left",
    )
    for i, (train_start, train_end, valid_end, test_end) in enumerate(folds):
        train = split_frame(model_frame, train_start, train_end)
        valid = split_frame(model_frame, train_end, valid_end)
        test = split_frame(model_frame, valid_end, test_end)
        if len(train) < 40 or len(valid) < 8:
            continue
        model = train_select(train, valid)
        last_model = model
        path = artifact_dir / f"model_fold_{i}_{model.name}.joblib"
        save_model(model, path)
        test_scores = []
        if not test.empty:
            proba = model.predict_proba(test)
            test = test.copy()
            test["probability"] = proba
            scored = merged_candidates[merged_candidates["id"].isin(test["candidate_id"])].copy()
            scored = scored.merge(test[["candidate_id", "probability"]], left_on="id", right_on="candidate_id", how="left")
            trades = run_backtest(scored, bars, features_wide, config, fold=f"test_{i}")
            all_trades.append(trades)
            metrics = summarize_trades(trades, config.initial_capital)
            metrics.update(
                {
                    "fold": i,
                    "model": model.name,
                    "valid_logloss": model.valid_logloss,
                    "valid_auc": model.valid_auc,
                    "train_rows": int(len(train)),
                    "valid_rows": int(len(valid)),
                    "test_rows": int(len(test)),
                    "train_end": str(train_end),
                    "valid_end": str(valid_end),
                    "test_end": str(test_end),
                }
            )
            fold_reports.append(metrics)
            test_scores.append(test)
    trades_frame = pd.concat(all_trades, ignore_index=True) if all_trades else pd.DataFrame()
    report = {
        "created_at": datetime.now(timezone.utc).isoformat(),
        "oos_overall": summarize_trades(trades_frame, config.initial_capital),
        "oos_by_year": by_year(trades_frame, config.initial_capital),
        "oos_by_regime": by_regime(trades_frame, config.initial_capital),
        "folds": fold_reports,
        "note": "Out-of-sample test folds only. Positive metrics are not a claim of live edge.",
    }
    (artifact_dir / "walkforward_report.json").write_text(json.dumps(report, indent=2, default=str))
    return trades_frame, report, last_model
