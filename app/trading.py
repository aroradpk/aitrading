from datetime import UTC, datetime

from app.models import AnalysisResponse, Trade, TradeAction, TradeRequest

_positions: dict[str, int] = {}
_trades: list[Trade] = []
_next_trade_id = 1


def analyze_symbol(symbol: str) -> AnalysisResponse:
    symbol = symbol.upper()
    score = sum(ord(char) for char in symbol) % 100
    if score >= 60:
        recommendation = "buy"
        summary = f"Model sees positive momentum signals for {symbol}."
    elif score >= 40:
        recommendation = "hold"
        summary = f"Model suggests waiting for clearer signals on {symbol}."
    else:
        recommendation = "sell"
        summary = f"Model flags elevated downside risk for {symbol}."

    return AnalysisResponse(
        symbol=symbol,
        recommendation=recommendation,
        confidence=round(0.55 + (score / 200), 2),
        summary=summary,
    )


def create_trade(request: TradeRequest) -> Trade:
    global _next_trade_id

    symbol = request.symbol.upper()
    signed_quantity = request.quantity if request.action == TradeAction.BUY else -request.quantity
    current_position = _positions.get(symbol, 0)
    if request.action == TradeAction.SELL and current_position < request.quantity:
        raise ValueError(f"Insufficient position for {symbol}")

    trade = Trade(
        id=_next_trade_id,
        symbol=symbol,
        action=request.action,
        quantity=request.quantity,
        price=request.price,
        total=round(request.quantity * request.price, 2),
        created_at=datetime.now(UTC),
    )
    _next_trade_id += 1
    _positions[symbol] = current_position + signed_quantity
    _trades.append(trade)
    return trade


def list_trades() -> list[Trade]:
    return list(reversed(_trades))


def list_positions() -> dict[str, int]:
    return {symbol: qty for symbol, qty in sorted(_positions.items()) if qty != 0}
