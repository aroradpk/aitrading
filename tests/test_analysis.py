import pandas as pd

from app.engines.move_detector import detect_moves
from app.engines.technical import build_snapshot, snapshot_similarity


def _sample_frame() -> pd.DataFrame:
    dates = pd.date_range("2024-01-01", periods=120, freq="B")
    prices = [100 + (i * 0.1) for i in range(120)]
    frame = pd.DataFrame(
        {
            "open": prices,
            "high": [p + 1 for p in prices],
            "low": [p - 1 for p in prices],
            "close": prices,
            "volume": [1_000_000] * 120,
            "symbol": ["TEST"] * 120,
        },
        index=dates,
    )
    # Inject a large up day
    frame.iloc[-1, frame.columns.get_loc("close")] = frame.iloc[-2]["close"] * 1.06
    frame.iloc[-1, frame.columns.get_loc("high")] = frame.iloc[-1]["close"] + 1
    return frame


def test_build_snapshot_has_tags() -> None:
    snapshot = build_snapshot(_sample_frame())
    assert "date" in snapshot
    assert isinstance(snapshot.get("tags"), list)


def test_snapshot_similarity_increases_with_shared_tags() -> None:
    a = {"tags": ["hammer", "near_support"], "weekly": {"tags": []}, "rsi_14": 32}
    b = {"tags": ["hammer", "near_support", "rsi_oversold"], "weekly": {"tags": []}, "rsi_14": 34}
    c = {"tags": ["near_resistance"], "weekly": {"tags": []}, "rsi_14": 70}
    assert snapshot_similarity(a, b) > snapshot_similarity(a, c)


def test_detect_moves_finds_large_day() -> None:
    frame = _sample_frame()
    moves = detect_moves(frame, instrument_type="stock")
    assert any(move["move_1d_pct"] >= 5 for move in moves)
