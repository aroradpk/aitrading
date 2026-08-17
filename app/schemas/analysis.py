from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class WatchlistEntry(BaseModel):
    symbol: str
    name: str
    type: str
    as_of: str
    horizon: str
    target_move_pct: float
    conviction: float
    scores: dict[str, float]
    match_count: int
    reasons: list[dict[str, Any]] = Field(default_factory=list)
    top_matches: list[dict[str, Any]] = Field(default_factory=list)
    current_snapshot: dict[str, Any] = Field(default_factory=dict)


class WatchlistReport(BaseModel):
    report_date: str
    generated_at: str
    count: int
    entries: list[WatchlistEntry]


class MoveEvent(BaseModel):
    symbol: str
    date: str
    instrument_type: str
    trigger_type: str
    threshold_pct: float
    move_1d_pct: float
    move_1w_pct: float | None
    direction: str
    close: float
    volume_ratio_vs_20d: float | None = None
    technical_snapshot: dict[str, Any] = Field(default_factory=dict)
    chart_file: str | None = None


class UniverseResponse(BaseModel):
    generated_at: str
    selection_rule: str
    stocks: list[dict[str, Any]]
    indices: list[dict[str, Any]]


class DataStatus(BaseModel):
    data_dir: str
    universe_exists: bool
    ohlcv_files: int
    move_symbols: int
    latest_report: str | None
    latest_backtest: str | None = None
    offline_mode: bool = False


class BacktestSignal(BaseModel):
    symbol: str
    date: str
    instrument_type: str
    conviction: float
    scores: dict[str, float]
    match_count: int
    entry_close: float
    fwd_1d_pct: float | None = None
    fwd_1w_pct: float | None = None
    target_1d_pct: float | None = None
    target_1w_pct: float | None = None
    hit_1d: bool | None = None
    hit_1w: bool | None = None


class BacktestReport(BaseModel):
    run_id: str
    generated_at: str
    config: dict[str, Any]
    summary: dict[str, Any]
    signals: list[BacktestSignal]


class BacktestTuningRow(BaseModel):
    conviction_min: float
    signal_cooldown_days: int
    summary: dict[str, Any]


class BacktestTuningReport(BaseModel):
    run_id: str
    generated_at: str
    config: dict[str, Any]
    grid: list[BacktestTuningRow]
    recommended: dict[str, Any] | None = None
