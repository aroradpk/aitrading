from __future__ import annotations

from datetime import date

import pandas as pd

from app.config import Settings, get_settings
from app.data.ingest import ingest_synthetic, ingest_yahoo
from app.data.store import Store
from app.features.technical import attach_context, features_for_symbol, long_feature_table, wide_features
from app.ml.dataset import build_model_frame, encode_categoricals, label_candidates
from app.ml.models import FittedModel
from app.report.daily import render_daily_report
from app.strategies.scan import generate_candidates
from app.universe import UNIVERSE


def _bar_frames(store: Store) -> dict[str, pd.DataFrame]:
    frames = {}
    for item in UNIVERSE:
        frame = store.load_daily(item.symbol)
        if frame.empty:
            raise RuntimeError(f"No bars for {item.symbol}. Run ingest first.")
        frames[item.symbol] = frame
    return frames


def compute_feature_frames(store: Store) -> dict[str, pd.DataFrame]:
    raw = _bar_frames(store)
    computed = {symbol: features_for_symbol(frame) for symbol, frame in raw.items()}
    return attach_context(computed)


def persist_features(store: Store, feature_frames: dict[str, pd.DataFrame]) -> pd.DataFrame:
    long = long_feature_table(feature_frames)
    store.replace_features(long)
    return wide_features(long)


def persist_candidates(store: Store, feature_frames: dict[str, pd.DataFrame], asof: date | None = None) -> pd.DataFrame:
    candidates = generate_candidates(feature_frames, asof=asof)
    store.replace_candidates([item.to_row() for item in candidates])
    return store.load_candidates()


def persist_labels(store: Store, feature_frames: dict[str, pd.DataFrame]) -> pd.DataFrame:
    candidates = store.load_candidates()
    bars = {symbol: frame[["date", "open", "high", "low", "close", "volume"]] for symbol, frame in feature_frames.items()}
    labels = label_candidates(candidates, bars)
    if not labels.empty:
        store.replace_labels(labels)
    return store.load_labels()


def model_matrix(store: Store) -> pd.DataFrame:
    candidates = store.load_candidates()
    labels = store.load_labels()
    features = wide_features(store.load_features())
    return build_model_frame(candidates, labels, features)


def score_candidates(store: Store, model: FittedModel) -> pd.DataFrame:
    candidates = store.load_candidates()
    features = wide_features(store.load_features())
    merged = encode_categoricals(candidates.merge(features, on=["symbol", "asof_date"], how="inner"))
    if merged.empty:
        return merged
    merged["probability"] = model.predict_proba(merged)
    return merged


def run_ingest(settings: Settings | None = None, source: str = "synthetic") -> None:
    settings = settings or get_settings()
    store = Store(settings.db_path)
    try:
        if source == "yahoo":
            ingest_yahoo(store, settings.lookback_calendar_days)
        else:
            ingest_synthetic(store)
    finally:
        store.close()


def prepare_all(settings: Settings | None = None) -> dict[str, pd.DataFrame]:
    settings = settings or get_settings()
    store = Store(settings.db_path)
    try:
        feature_frames = compute_feature_frames(store)
        persist_features(store, feature_frames)
        persist_candidates(store, feature_frames)
        persist_labels(store, feature_frames)
        return feature_frames
    finally:
        store.close()


def latest_asof(feature_frames: dict[str, pd.DataFrame]) -> date:
    dates = []
    for frame in feature_frames.values():
        dates.extend(frame["date"].tolist())
    return max(dates)
