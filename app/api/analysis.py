from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, File, HTTPException, Query, UploadFile

from app.core.config import get_settings

from app.core.paths import (
    backtest_reports_dir,
    data_dir,
    events_nse_dir,
    fundamentals_dir,
    fundamentals_import_dir,
    moves_dir,
    ohlcv_daily_dir,
    reports_dir,
    universe_dir,
)
from app.engines.backtest import load_latest_backtest, run_backtest
from app.engines.conviction import build_daily_watchlist, load_latest_watchlist
from app.engines.events import refresh_events_for_universe, score_events
from app.engines.fundamental import import_screener_csv, load_fundamentals, score_fundamentals
from app.engines.move_detector import load_moves
from app.engines.themes import (
    build_all_theme_scores,
    load_theme_graph,
    load_theme_score,
    score_themes,
)
from app.engines.universe import build_active_universe, load_active_universe
from app.schemas.analysis import (
    BacktestReport,
    DataStatus,
    MoveEvent,
    UniverseResponse,
    WatchlistReport,
)

router = APIRouter(prefix="/api/analysis", tags=["analysis"])


def _reject_if_offline(action: str) -> None:
    if get_settings().offline_mode:
        raise HTTPException(
            status_code=409,
            detail=(
                f"{action} is disabled while offline_mode=true. "
                "The app uses saved data/ only. Set offline_mode: false to refresh from the web."
            ),
        )


@router.get("/status", response_model=DataStatus)
def analysis_status() -> DataStatus:
    ohlcv_count = len(list(ohlcv_daily_dir().glob("*.parquet")))
    move_symbols = len([p for p in moves_dir().glob("*") if p.is_dir()])
    reports = sorted(reports_dir().glob("*.json"), reverse=True)
    backtests = sorted(backtest_reports_dir().glob("*.json"), reverse=True)
    latest_backtest = next((p.name for p in backtests if p.name == "latest.json"), None)
    if latest_backtest is None and backtests:
        latest_backtest = backtests[0].name
    return DataStatus(
        data_dir=str(data_dir()),
        universe_exists=(universe_dir() / "active.json").exists(),
        ohlcv_files=ohlcv_count,
        move_symbols=move_symbols,
        latest_report=reports[0].name if reports else None,
        latest_backtest=latest_backtest,
        offline_mode=get_settings().offline_mode,
    )


@router.get("/universe", response_model=UniverseResponse)
def get_universe() -> UniverseResponse:
    payload = load_active_universe()
    return UniverseResponse.model_validate(payload)


@router.post("/universe/refresh", response_model=UniverseResponse)
def refresh_universe() -> UniverseResponse:
    _reject_if_offline("Universe refresh")
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


@router.post("/events/refresh")
def refresh_events() -> dict:
    _reject_if_offline("Events refresh")
    return refresh_events_for_universe()


@router.get("/events/{symbol}")
def get_symbol_events(symbol: str) -> dict:
    event_score, reasons = score_events(symbol.upper())
    nse_path = events_nse_dir() / f"{symbol.upper()}.json"
    announcements = []
    if nse_path.exists():
        import json

        announcements = json.loads(nse_path.read_text(encoding="utf-8"))
    return {
        "symbol": symbol.upper(),
        "event_score": event_score,
        "reasons": reasons,
        "announcements": announcements[:20],
    }


@router.get("/fundamentals/{symbol}")
def get_symbol_fundamentals(symbol: str) -> dict:
    payload = load_fundamentals(symbol.upper())
    if payload is None:
        raise HTTPException(status_code=404, detail=f"No fundamentals for {symbol}")
    score, reasons = score_fundamentals(symbol.upper())
    return {"symbol": symbol.upper(), "data": payload, "score": score, "reasons": reasons}


@router.get("/themes/graph")
def get_theme_graph() -> dict:
    return load_theme_graph()


@router.get("/themes/{symbol}")
def get_symbol_themes(symbol: str) -> dict:
    symbol = symbol.upper()
    cached = load_theme_score(symbol)
    if cached is not None:
        return cached
    score_themes(symbol)
    payload = load_theme_score(symbol)
    if payload is None:
        raise HTTPException(status_code=404, detail=f"No theme data for {symbol}")
    return payload


@router.post("/backtest/run", response_model=BacktestReport)
def build_backtest() -> BacktestReport:
    payload = run_backtest()
    return BacktestReport.model_validate(payload)


@router.get("/backtest/latest", response_model=BacktestReport)
def latest_backtest() -> BacktestReport:
    payload = load_latest_backtest()
    if payload is None:
        raise HTTPException(
            status_code=404,
            detail="No backtest report found. Run scripts/run_backtest.py",
        )
    return BacktestReport.model_validate(payload)


@router.post("/themes/build")
def build_themes() -> dict:
    scores = build_all_theme_scores()
    return {"count": len(scores), "scores": scores}


@router.post("/fundamentals/import")
async def upload_screener_csv(file: UploadFile = File(...)) -> dict:
    if not file.filename or not file.filename.lower().endswith(".csv"):
        raise HTTPException(status_code=400, detail="Upload a .csv file exported from Screener")
    import_dir = fundamentals_import_dir()
    import_dir.mkdir(parents=True, exist_ok=True)
    dest = import_dir / file.filename
    content = await file.read()
    dest.write_bytes(content)
    imported = import_screener_csv(dest)
    return {"filename": file.filename, "imported_symbols": list(imported.keys())}

