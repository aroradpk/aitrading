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
