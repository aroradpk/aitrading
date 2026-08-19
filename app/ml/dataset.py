from __future__ import annotations

import pandas as pd

from app.features.technical import FEATURE_COLUMNS
from app.strategies.registry import STRATEGIES

CAT_COLUMNS = ["side_long", *[f"strategy_{item.name}" for item in STRATEGIES]]
MODEL_COLUMNS = FEATURE_COLUMNS + CAT_COLUMNS


def encode_categoricals(frame: pd.DataFrame) -> pd.DataFrame:
    out = frame.copy()
    out["side_long"] = (out["side"].astype(str) == "long").astype(float)
    for item in STRATEGIES:
        out[f"strategy_{item.name}"] = (out["strategy"].astype(str) == item.name).astype(float)
    return out


def next_session_map(bars: dict[str, pd.DataFrame]) -> dict[tuple[str, object], pd.Series]:
    mapping: dict[tuple[str, object], pd.Series] = {}
    for symbol, frame in bars.items():
        ordered = frame.sort_values("date").reset_index(drop=True)
        for i in range(len(ordered) - 1):
            today = ordered.loc[i, "date"]
            mapping[(symbol, today)] = ordered.loc[i + 1]
    return mapping


def label_candidates(candidates: pd.DataFrame, bars: dict[str, pd.DataFrame]) -> pd.DataFrame:
    from app.ml.labels import rebase_levels, simulate_next_session

    nxt = next_session_map(bars)
    rows = []
    for row in candidates.itertuples(index=False):
        key = (row.symbol, row.asof_date)
        if key not in nxt:
            continue
        session = nxt[key]
        fill = float(session["open"])
        stop, target = rebase_levels(
            float(row.entry_price),
            float(row.stop_price),
            float(row.target_price),
            fill,
            row.side,
        )
        outcome = simulate_next_session(row.side, fill, stop, target, session)
        rows.append(
            {
                "candidate_id": int(row.id),
                "asof_date": row.asof_date,
                "symbol": row.symbol,
                "target_hit_before_stop": outcome.target_hit_before_stop,
                "exit_reason": outcome.exit_reason,
                "pnl_pct": outcome.pnl_pct,
                "mfe_pct": outcome.mfe_pct,
                "mae_pct": outcome.mae_pct,
            }
        )
    return pd.DataFrame(rows)


def build_model_frame(candidates: pd.DataFrame, labels: pd.DataFrame, features_wide: pd.DataFrame) -> pd.DataFrame:
    cand = candidates.copy()
    if "id" in cand.columns and "candidate_id" not in cand.columns:
        cand = cand.rename(columns={"id": "candidate_id"})
    merged = cand.merge(labels, on="candidate_id", how="inner", suffixes=("", "_y"))
    out = merged.merge(features_wide, on=["symbol", "asof_date"], how="inner")
    out = encode_categoricals(out)
    keep = [col for col in MODEL_COLUMNS if col in out.columns]
    cols = ["candidate_id", "asof_date", "symbol", "strategy", "side", "target_hit_before_stop", *keep]
    return out[cols].dropna(subset=["target_hit_before_stop", *keep])


def chronological_folds(
    dates: list,
    train_days: int | None = None,
    valid_days: int | None = None,
    test_days: int | None = None,
    step_days: int | None = None,
) -> list[tuple]:
    from datetime import timedelta

    unique = sorted(set(dates))
    n = len(unique)
    if n < 70:
        return []
    if train_days is None:
        if n >= 378:
            train_days, valid_days, test_days, step_days = 252, 63, 63, 63
        else:
            train_days = max(40, int(n * 0.5))
            valid_days = max(15, int(n * 0.2))
            test_days = max(15, n - train_days - valid_days)
            step_days = max(10, test_days)
    assert valid_days is not None and test_days is not None and step_days is not None
    folds = []
    i = 0
    while True:
        train_end_i = i + train_days
        valid_end_i = train_end_i + valid_days
        test_end_i = valid_end_i + test_days
        if test_end_i > len(unique):
            break
        folds.append(
            (
                unique[i],
                unique[train_end_i],
                unique[valid_end_i],
                unique[test_end_i - 1] + timedelta(days=1),
            )
        )
        i += step_days
    return folds


def split_frame(frame: pd.DataFrame, start, end) -> pd.DataFrame:
    return frame[(frame["asof_date"] >= start) & (frame["asof_date"] < end)].copy()
