from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from app.models import AnalysisRequest, AnalysisResponse, Trade, TradeRequest
from app.trading import analyze_symbol, create_trade, list_positions, list_trades

STATIC_DIR = Path(__file__).resolve().parent.parent / "static"

app = FastAPI(title="AI Trading", version="0.1.0")
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")


@app.get("/")
def index() -> FileResponse:
    return FileResponse(STATIC_DIR / "index.html")


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/api/analyze", response_model=AnalysisResponse)
def analyze(request: AnalysisRequest) -> AnalysisResponse:
    return analyze_symbol(request.symbol)


@app.get("/api/trades", response_model=list[Trade])
def get_trades() -> list[Trade]:
    return list_trades()


@app.get("/api/positions")
def get_positions() -> dict[str, int]:
    return list_positions()


@app.post("/api/trades", response_model=Trade)
def post_trade(request: TradeRequest) -> Trade:
    try:
        return create_trade(request)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
