from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, File, HTTPException, Query, UploadFile
from fastapi.responses import FileResponse

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
    technical_charts_dir,
    universe_dir,
)
from app.engines.backtest import (
    load_latest_backtest,
    load_latest_tuning,
    run_backtest,
    tune_backtest,
)
from app.engines.chart_render import chart_path_for_move
from app.engines.conviction import build_daily_watchlist, load_latest_watchlist
from app.engines.events import refresh_events_for_universe, score_events
from app.engines.event_transcripts import (
    fetch_transcripts_for_symbol,
    fetch_transcripts_for_universe,
    list_transcript_candidates,
)
from app.engines.fundamental import import_screener_csv, load_fundamentals, score_fundamentals
from app.engines.move_detector import load_moves
from app.engines.themes import (
    build_all_theme_scores,
    delete_theme_override,
    list_active_stock_symbols,
    load_rubric_guide,
    load_theme_graph,
    load_theme_override,
    load_theme_score,
    save_theme_graph,
    save_theme_override,
    score_themes,
    update_theme_symbols,
)
from app.engines.adr import build_adr_profiles
from app.engines.intraday_ledger import load_ledger, recompute_rule_stats
from app.engines.universe import build_active_universe, load_active_universe
from app.schemas.analysis import (
    BacktestReport,
    BacktestTuningReport,
    DataStatus,
    MoveEvent,
    ThemeGraphUpdate,
    ThemeOverrideUpdate,
    ThemeSymbolAssignment,
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


@router.get("/charts/{symbol}/{move_date}")
def get_move_chart(symbol: str, move_date: str) -> FileResponse:
    path = chart_path_for_move(symbol.upper(), move_date)
    if not path.exists():
        raise HTTPException(status_code=404, detail=f"No chart for {symbol} on {move_date}")
    return FileResponse(path, media_type="image/png", filename=path.name)


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


@router.get("/intraday/adr")
def get_adr_profiles() -> dict:
    from app.core.paths import adr_profile_path
    import json

    path = adr_profile_path()
    if path.exists():
        return json.loads(path.read_text(encoding="utf-8"))
    return build_adr_profiles()


@router.get("/intraday/stats")
def get_intraday_stats() -> dict:
    stats = recompute_rule_stats()
    ledger = load_ledger()
    stats["ledger_rows"] = len(ledger)
    stats["open_rows"] = sum(1 for row in ledger if row.get("mfe_pct") is None)
    return stats


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


@router.post("/events/transcripts/fetch")
def fetch_event_transcripts(
    symbol: str | None = Query(default=None),
    limit_per_symbol: int | None = Query(default=None, ge=1, le=50),
) -> dict:
    _reject_if_offline("Transcript fetch")
    if symbol:
        return fetch_transcripts_for_symbol(symbol.upper(), limit=limit_per_symbol)
    return fetch_transcripts_for_universe(limit_per_symbol=limit_per_symbol)


@router.get("/events/{symbol}/transcripts")
def get_symbol_transcript_candidates(symbol: str) -> dict:
    return {
        "symbol": symbol.upper(),
        "candidates": list_transcript_candidates(symbol.upper()),
    }


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


@router.put("/themes/graph")
def put_theme_graph(payload: ThemeGraphUpdate) -> dict:
    try:
        return save_theme_graph(payload.model_dump())
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/themes/rubric-guide")
def get_rubric_guide() -> dict:
    return load_rubric_guide()


@router.get("/themes/symbols")
def get_theme_symbols() -> dict:
    return {"symbols": list_active_stock_symbols()}


@router.get("/themes/overrides/{symbol}")
def get_theme_override(symbol: str) -> dict:
    override = load_theme_override(symbol.upper())
    return {"symbol": symbol.upper(), "override": override or {"rubric": {}}}


@router.put("/themes/overrides/{symbol}")
def put_theme_override(symbol: str, payload: ThemeOverrideUpdate) -> dict:
    saved = save_theme_override(symbol.upper(), payload.rubric, notes=payload.notes)
    score_themes(symbol.upper())
    return {"symbol": symbol.upper(), "override": saved, "score": load_theme_score(symbol.upper())}


@router.delete("/themes/overrides/{symbol}")
def remove_theme_override(symbol: str) -> dict:
    deleted = delete_theme_override(symbol.upper())
    if deleted:
        score_themes(symbol.upper())
    return {"symbol": symbol.upper(), "deleted": deleted}


@router.patch("/themes/{theme_id}/symbols")
def patch_theme_symbols(theme_id: str, payload: ThemeSymbolAssignment) -> dict:
    try:
        graph = update_theme_symbols(theme_id, payload.symbol, assign=payload.assign)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return graph


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


@router.post("/backtest/tune", response_model=BacktestTuningReport)
def build_backtest_tuning() -> BacktestTuningReport:
    payload = tune_backtest()
    return BacktestTuningReport.model_validate(payload)


@router.get("/backtest/tuning/latest", response_model=BacktestTuningReport)
def latest_backtest_tuning() -> BacktestTuningReport:
    payload = load_latest_tuning()
    if payload is None:
        raise HTTPException(
            status_code=404,
            detail="No tuning report found. Run scripts/tune_backtest.py",
        )
    return BacktestTuningReport.model_validate(payload)


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

