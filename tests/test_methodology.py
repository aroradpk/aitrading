import pandas as pd

from app.engines.event_content import analyze_event_content, score_analyzed_event
from app.engines.technical import build_snapshot, position_bias


def _uptrend_frame() -> pd.DataFrame:
    dates = pd.date_range("2024-01-01", periods=120, freq="B")
    prices = [100 + (i * 0.35) for i in range(120)]
    return pd.DataFrame(
        {
            "open": prices,
            "high": [p + 1.2 for p in prices],
            "low": [p - 1.0 for p in prices],
            "close": prices,
            "volume": [1_000_000] * 120,
            "symbol": ["TEST"] * 120,
        },
        index=dates,
    )


def test_snapshot_uses_ema_not_sma_fields() -> None:
    snap = build_snapshot(_uptrend_frame())
    assert "ema_20" in snap
    assert "sma_20" not in snap
    assert "long_term_uptrend" in snap["tags"] or "short_term_uptrend" in snap["tags"]


def test_position_bias_long_on_uptrend() -> None:
    snap = build_snapshot(_uptrend_frame())
    assert position_bias(snap, focus="long") == "long"


def test_candle_only_with_context() -> None:
    snap = build_snapshot(_uptrend_frame())
    if snap.get("raw_candle_patterns"):
        if snap["raw_candle_patterns"]:
            assert any(tag.startswith("candle_") for tag in snap["tags"]) or not snap["raw_candle_patterns"]


def test_concall_positive_content_scores() -> None:
    item = {
        "type": "concall",
        "title": "Transcript of earnings conference call — record revenue and margin expansion",
    }
    analysis = analyze_event_content(item)
    assert analysis["alignment"] == "positive"
    assert score_analyzed_event(item, analysis) > 0


def test_concall_without_signals_requires_transcript() -> None:
    item = {"type": "concall", "title": "Schedule of analyst meet"}
    analysis = analyze_event_content(item)
    assert analysis.get("requires_transcript") is True
    assert score_analyzed_event(item, analysis) == 0.0
