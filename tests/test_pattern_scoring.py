import pandas as pd

from app.core.paths import ohlcv_daily_dir
from app.engines.conviction import conviction_from_scores
from app.engines.move_detector import load_moves, scan_today_setup
from app.engines.pattern_confirmations import detect_daily_confirmations
from app.ingest.yfinance_client import load_ohlcv


def test_motherson_aug6_breakout_base_scores_seven() -> None:
    path = ohlcv_daily_dir() / "MOTHERSON.parquet"
    if not path.exists():
        return
    frame = load_ohlcv(path)
    signal_date = "2026-08-06"
    idx = frame.index.get_indexer([pd.Timestamp(signal_date)], method="nearest")[0]
    slice = frame.iloc[: idx + 1]
    conf = detect_daily_confirmations(slice, "long")
    assert conf["ema20_support"]
    assert conf["consolidation_anchor"]
    assert conf["ema_momentum_expanding"]

    hist = [m for m in load_moves("MOTHERSON") if m["date"] < signal_date]
    setup = scan_today_setup(slice, hist, side="long", symbol="MOTHERSON")
    assert setup["technical_score"] >= 7.0
    assert setup.get("breakout_base") is True
    assert setup.get("pattern_families")

    scores = conviction_from_scores(setup["technical_score"])
    assert scores["technical"] >= 7.0
    assert scores["final"] >= 7.0


def test_two_piece_family_with_energy_is_not_seven() -> None:
    from app.engines.pattern_scoring import score_technical_confirmations

    scored = score_technical_confirmations(
        {
            "ema20_support": True,
            "uptrend": True,
            "vol_expansion": True,
            "range_expansion": True,
        },
        side="long",
    )
    assert scored["technical_score"] < 7.0
    assert "ema_pullback" in scored["pattern_families"]
    assert scored["score_layers"]["ema_structure"] == 1.5
    assert scored["score_layers"]["energy"] == 1.0


def test_weighted_layers_reach_seven() -> None:
    from app.engines.pattern_scoring import score_technical_confirmations

    scored = score_technical_confirmations(
        {
            "ema20_support": True,
            "uptrend": True,
            "sr_level": True,
            "fib_level": True,
            "sr_fib_confluence": True,
            "elliott_aligned": True,
            "bullish_formation": True,
            "vol_expansion": True,
            "range_expansion": True,
        },
        side="long",
        snapshot={
            "tags": ["elliott_impulse_up", "fib_0.618_retrace", "near_support", "candle_hammer"],
            "formations": [{"id": "falling_wedge"}],
        },
    )
    assert scored["technical_score"] == 7.0
    assert scored["score_layers"]["sr_fib"] == 1.5
    assert scored["score_layers"]["elliott"] == 1.5
    assert scored["score_layers"]["formation"] == 1.5
    assert scored["score_layers"]["candle"] == 0.5
    assert any("S/R with Fibonacci" in label for label in scored["confirmation_labels"])
    assert any("Elliott wave" in label for label in scored["confirmation_labels"])


def test_elliott_conflict_zeros_layer_not_whole_score() -> None:
    from app.engines.pattern_scoring import score_technical_confirmations

    scored = score_technical_confirmations(
        {
            "ema20_support": True,
            "uptrend": True,
            "sr_level": True,
            "bullish_formation": True,
            "elliott_conflict": True,
            "vol_expansion": True,
            "range_expansion": True,
        },
        side="long",
        snapshot={"tags": ["elliott_impulse_down"], "formations": [{"id": "falling_wedge"}]},
    )
    assert scored["score_layers"]["elliott"] == 0.0
    assert scored["technical_score"] >= 4.0
    assert scored["technical_score"] < 7.0


def test_candle_cherry_requires_context() -> None:
    from app.engines.pattern_scoring import score_technical_confirmations

    scored = score_technical_confirmations(
        {"vol_expansion": True, "range_expansion": True},
        side="long",
        snapshot={"tags": ["candle_morning_star"], "formations": []},
    )
    assert scored["score_layers"]["candle"] == 0.0
    assert scored["technical_score"] < 7.0


def test_family_without_energy_is_not_high_conviction() -> None:
    from app.engines.pattern_scoring import score_technical_confirmations

    scored = score_technical_confirmations(
        {"ema20_support": True, "uptrend": True, "vol_expansion": False, "range_expansion": False},
        side="long",
    )
    assert scored["technical_score"] < 7.0


def test_empty_confirmations_not_seven() -> None:
    from app.engines.pattern_scoring import score_technical_confirmations

    scored = score_technical_confirmations({}, side="long")
    assert scored["technical_score"] < 7.0
    scores = conviction_from_scores(technical=9.5, fundamental=10, events=10, theme=8)
    assert scores["technical"] == 7.0
    assert scores["research"] <= 3.0
    assert 1.0 <= scores["theme_bonus"] <= 5.0
    assert scores["final"] <= 10.0
