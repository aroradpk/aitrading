import pandas as pd

from app.engines.event_content import analyze_event_content, score_analyzed_event
from app.engines.move_detector import load_moves, scan_today_setup
from app.engines.technical import (
    build_snapshot,
    exhaustion_fade_side,
    position_bias,
    technical_reasons_for_side,
)
from app.ingest.yfinance_client import load_ohlcv
from app.core.paths import ohlcv_daily_dir


def _uptrend_frame(*, periods: int = 220) -> pd.DataFrame:
    dates = pd.date_range("2024-01-01", periods=periods, freq="B")
    prices = [100 + (i * 0.35) for i in range(periods)]
    return pd.DataFrame(
        {
            "open": prices,
            "high": [p + 1.2 for p in prices],
            "low": [p - 1.0 for p in prices],
            "close": prices,
            "volume": [1_000_000] * periods,
            "symbol": ["TEST"] * periods,
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
    assert position_bias(snap, focus="long") in {"long", "neutral"}
    if "ema_momentum_expanding" in snap["tags"] or "ema20_support_touch" in snap["tags"]:
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


def test_ema_structure_tags_not_generic_above_ema20() -> None:
    snap = build_snapshot(_uptrend_frame())
    assert "above_ema20" not in snap["tags"]
    assert "below_ema20" not in snap["tags"]


def test_exhaustion_fade_short_at_resistance() -> None:
    snap = {
        "tags": ["rsi_overbought", "near_resistance", "short_term_uptrend"],
        "weekly": {"tags": ["weekly_rsi_overbought"]},
    }
    assert exhaustion_fade_side(snap) == "short"
    assert position_bias(snap, focus="long") == "neutral"
    assert position_bias(snap, focus="short") == "short"


def test_long_reasons_flag_headwinds() -> None:
    snap = {
        "tags": ["rsi_overbought", "near_resistance", "ema20_extended_long"],
        "weekly": {"tags": []},
    }
    reasons = technical_reasons_for_side(snap, "long")
    headwinds = [r for r in reasons if r.get("headwind")]
    assert any("rsi overbought" in r["text"] for r in headwinds)
    assert any("near resistance" in r["text"] for r in headwinds)


def test_motherson_long_capped_when_overbought_at_resistance() -> None:
    path = ohlcv_daily_dir() / "MOTHERSON.parquet"
    if not path.exists():
        return
    frame = load_ohlcv(path)
    # Extended chase day (Aug 14) should not score like breakout base (Aug 6)
    snap_extended = build_snapshot(frame)
    setup_long_extended = scan_today_setup(frame, [], side="long", symbol="MOTHERSON")
    assert setup_long_extended["technical_score"] < 7.0

    signal_idx = frame.index.get_indexer([pd.Timestamp("2026-08-06")], method="nearest")[0]
    setup_base = scan_today_setup(
        frame.iloc[: signal_idx + 1],
        load_moves("MOTHERSON"),
        side="long",
        symbol="MOTHERSON",
    )
    assert setup_base["technical_score"] >= 7.0
