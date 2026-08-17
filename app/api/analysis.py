from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, HTTPException, Query

from app.core.paths import data_dir, moves_dir, ohlcv_daily_dir, reports_dir, universe_dir
from app.engines.conviction import build_daily_watchlist, load_latest_watchlist
from app.engines.move_detector import load_moves
from app.engines.universe import build_active_universe, load_active_universe
from app.schemas.analysis import DataStatus, MoveEvent, UniverseResponse, WatchlistReport

router = APIRouter(prefix="/api/analysis", tags=["analysis"])


@router.get("/status", response_model=DataStatus)
def analysis_status() -> DataStatus:
    ohlcv_count = len(list(ohlcv_daily_dir().glob("*.parquet")))
    move_symbols = len([p for p in moves_dir().glob("*") if p.is_dir()])
    reports = sorted(reports_dir().glob("*.json"), reverse=True)
    return DataStatus(
        data_dir=str(data_dir()),
        universe_exists=(universe_dir() / "active.json").exists(),
        ohlcv_files=ohlcv_count,
        move_symbols=move_symbols,
        latest_report=reports[0].name if reports else None,
    )


@router.get("/universe", response_model=UniverseResponse)
def get_universe() -> UniverseResponse:
    payload = load_active_universe()
    return UniverseResponse.model_validate(payload)


@router.post("/universe/refresh", response_model=UniverseResponse)
def refresh_universe() -> UniverseResponse:
    payload = build_active_universe()
    return UniverseResponse.model_validate(payload)


@router.get("/moves", response_model=list[MoveEvent])
def get_moves(
    symbol: str | None = Query(default=None),
    direction: str | None = Query(default=None),
    limit: int = Query(default=100, ge=1, le=500),
) -> list[MoveEvent]:
    moves = load_moves(symbol)
    if direction:
        moves = [move for move in moves if move.get("direction") == direction]
    return [MoveEvent.model_validate(move) for move in moves[:limit]]


@router.get("/watchlist/latest", response_model=WatchlistReport)
def latest_watchlist() -> WatchlistReport:
    payload = load_latest_watchlist()
    if payload is None:
        raise HTTPException(status_code=404, detail="No watchlist report found. Run scripts/build_watchlist.py")
    return WatchlistReport.model_validate(payload)


@router.post("/watchlist/build", response_model=WatchlistReport)
def build_watchlist() -> WatchlistReport:
    payload = build_daily_watchlist()
    return WatchlistReport.model_validate(payload)
