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


def test_morning_star_and_hammer_raw_tags() -> None:
    from app.engines.technical import _raw_candle_tags

    prev2 = pd.Series({"open": 110.0, "high": 111.0, "low": 100.0, "close": 101.0})
    prev = pd.Series({"open": 102.0, "high": 103.0, "low": 100.5, "close": 101.5})
    row = pd.Series({"open": 102.0, "high": 108.0, "low": 101.8, "close": 107.0})
    tags = _raw_candle_tags(row, prev, prev2)
    assert "morning_star" in tags

    hammer = pd.Series({"open": 10.2, "high": 10.21, "low": 9.0, "close": 10.15})
    assert "hammer" in _raw_candle_tags(hammer, None, None)


def test_reasons_include_elliott_fib_formation() -> None:
    snap = {
        "tags": ["elliott_impulse_up", "fib_0.618_retrace", "formation_falling_wedge", "candle_hammer"],
        "weekly": {"tags": []},
    }
    texts = [r["text"] for r in technical_reasons_for_side(snap, "long")]
    assert any("elliott" in t for t in texts)
    assert any("fib" in t for t in texts)
    assert any("formation" in t for t in texts)
    assert any("candle" in t for t in texts)


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


def test_motherson_aug5_coil_still_scans() -> None:
    path = ohlcv_daily_dir() / "MOTHERSON.parquet"
    if not path.exists():
        return
    frame = load_ohlcv(path)
    signal_idx = frame.index.get_indexer([pd.Timestamp("2026-08-05")], method="nearest")[0]
    setup_base = scan_today_setup(
        frame.iloc[: signal_idx + 1],
        load_moves("MOTHERSON"),
        side="long",
        symbol="MOTHERSON",
    )
    assert "technical_score" in setup_base
    assert setup_base["technical_score"] >= 0
