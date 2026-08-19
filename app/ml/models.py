from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
from sklearn.ensemble import HistGradientBoostingClassifier
from sklearn.metrics import log_loss, roc_auc_score

from app.ml.dataset import MODEL_COLUMNS


@dataclass
class FittedModel:
    name: str
    estimator: object
    feature_names: list[str]
    valid_logloss: float
    valid_auc: float

    def predict_proba(self, frame: pd.DataFrame) -> np.ndarray:
        matrix = frame[self.feature_names].to_numpy(dtype=float)
        if self.name == "constant_prior":
            p = float(self.estimator)
            return np.full(len(frame), p, dtype=float)
        raw = self.estimator.predict_proba(matrix)
        if raw.ndim == 1:
            return raw
        return raw[:, 1]


def _fit_lgbm(x, y):
    import lightgbm as lgb

    model = lgb.LGBMClassifier(
        n_estimators=200,
        learning_rate=0.05,
        num_leaves=15,
        min_child_samples=20,
        subsample=0.8,
        colsample_bytree=0.8,
        random_state=7,
        verbose=-1,
    )
    model.fit(x, y)
    return model


def _fit_xgb(x, y):
    from xgboost import XGBClassifier

    model = XGBClassifier(
        n_estimators=200,
        max_depth=3,
        learning_rate=0.05,
        subsample=0.8,
        colsample_bytree=0.8,
        eval_metric="logloss",
        n_jobs=1,
        random_state=7,
    )
    model.fit(x, y)
    return model


def _fit_hgb(x, y):
    model = HistGradientBoostingClassifier(max_depth=3, learning_rate=0.06, max_iter=200, random_state=7)
    model.fit(x, y)
    return model


FITTERS = {
    "lightgbm": _fit_lgbm,
    "xgboost": _fit_xgb,
    "hist_gbm": _fit_hgb,
}


def available_feature_names(frame: pd.DataFrame) -> list[str]:
    return [name for name in MODEL_COLUMNS if name in frame.columns]


def train_select(train: pd.DataFrame, valid: pd.DataFrame) -> FittedModel:
    names = available_feature_names(train)
    x_train = train[names].to_numpy(dtype=float)
    y_train = train["target_hit_before_stop"].to_numpy(dtype=int)
    x_valid = valid[names].to_numpy(dtype=float)
    y_valid = valid["target_hit_before_stop"].to_numpy(dtype=int)
    if len(np.unique(y_train)) < 2:
        prior = float(np.clip(y_train.mean() if len(y_train) else 0.5, 1e-6, 1 - 1e-6))
        proba = np.full(len(y_valid), prior)
        loss = float(log_loss(y_valid, proba, labels=[0, 1])) if len(y_valid) else 0.0
        return FittedModel("constant_prior", prior, names, loss, float("nan"))
    best: FittedModel | None = None
    for name, fitter in FITTERS.items():
        try:
            estimator = fitter(x_train, y_train)
        except Exception:
            continue
        proba = estimator.predict_proba(x_valid)
        proba = proba[:, 1] if proba.ndim > 1 else proba
        proba = np.clip(proba, 1e-6, 1 - 1e-6)
        loss = float(log_loss(y_valid, proba, labels=[0, 1]))
        try:
            auc = float(roc_auc_score(y_valid, proba))
        except ValueError:
            auc = float("nan")
        candidate = FittedModel(name, estimator, names, loss, auc)
        if best is None or candidate.valid_logloss < best.valid_logloss:
            best = candidate
    if best is None:
        raise RuntimeError("No model backend could be fitted.")
    return best


def save_model(model: FittedModel, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    joblib.dump(model, path)


def load_model(path: Path) -> FittedModel:
    return joblib.load(path)
