from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_health() -> None:
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_analyze_and_trade_flow() -> None:
    analysis = client.post("/api/analyze", json={"symbol": "AAPL"})
    assert analysis.status_code == 200
    body = analysis.json()
    assert body["symbol"] == "AAPL"
    assert body["recommendation"] in {"buy", "sell", "hold"}

    trade = client.post(
        "/api/trades",
        json={"symbol": "AAPL", "action": "buy", "quantity": 5, "price": 180.0},
    )
    assert trade.status_code == 200
    trade_body = trade.json()
    assert trade_body["total"] == 900.0

    trades = client.get("/api/trades")
    assert trades.status_code == 200
    assert len(trades.json()) >= 1
