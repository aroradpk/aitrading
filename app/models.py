from datetime import datetime
from enum import Enum

from pydantic import BaseModel, Field


class TradeAction(str, Enum):
    BUY = "buy"
    SELL = "sell"


class TradeRequest(BaseModel):
    symbol: str = Field(..., min_length=1, max_length=10, examples=["AAPL"])
    action: TradeAction
    quantity: int = Field(..., gt=0, le=10000)
    price: float = Field(..., gt=0)


class Trade(BaseModel):
    id: int
    symbol: str
    action: TradeAction
    quantity: int
    price: float
    total: float
    created_at: datetime


class AnalysisRequest(BaseModel):
    symbol: str = Field(..., min_length=1, max_length=10, examples=["AAPL"])


class AnalysisResponse(BaseModel):
    symbol: str
    recommendation: str
    confidence: float
    summary: str
