import pandas as pd

from app.core.paths import ohlcv_daily_dir
from app.engines.conviction import conviction_from_scores
from app.engines.move_detector import load_moves, scan_today_setup
from app.engines.pattern_confirmations import detect_daily_confirmations
from app.ingest.yfinance_client import load_ohlcv


def test_motherson_aug5_coil_is_watch_not_seven() -> None:
    path = ohlcv_daily_dir() / "MOTHERSON.parquet"
    if not path.exists():
        return
    frame = load_ohlcv(path)
    signal_date = "2026-08-05"
    idx = frame.index.get_indexer([pd.Timestamp(signal_date)], method="nearest")[0]
    slice = frame.iloc[: idx + 1]
    conf = detect_daily_confirmations(slice, "long")
    assert conf["ema20_support"]
    assert conf["consolidation_anchor"]
    assert conf["sr_fib_confluence"]
    assert not conf["vol_expansion"]

    hist = [m for m in load_moves("MOTHERSON") if m["date"] < signal_date]
    setup = scan_today_setup(slice, hist, side="long", symbol="MOTHERSON")
    assert setup.get("breakout_base") is True


def test_setup_rattle_without_mtf_is_six_not_seven() -> None:
    from app.engines.pattern_scoring import score_technical_confirmations

    scored = score_technical_confirmations(
        {"setup_rattle": True, "vol_expansion": False, "range_expansion": False},
        side="long",
    )
    assert scored["technical_score"] == 6.0
    assert scored["expected_move_pct"] == 4.0
    assert scored["precision_energy"] is True
    assert scored["mtf_precision"] is False


def test_late_five_percent_bar_is_not_seven() -> None:
    from app.engines.pattern_scoring import score_technical_confirmations

    scored = score_technical_confirmations(
        {"range_expansion": True, "vol_expansion": True, "setup_rattle": False, "late_bar": True},
        side="long",
    )
    assert scored["technical_score"] < 7.0
    assert scored["expected_move_pct"] == 0.0
    assert scored["precision_energy"] is False


def test_hourly_fib_is_not_a_seven_gate() -> None:
    from app.engines.pattern_scoring import score_technical_confirmations

    scored = score_technical_confirmations(
        {"setup_rattle": True, "mtf_1h_fib_sr": True},
        side="long",
    )
    assert scored["technical_score"] == 6.0
    assert scored["expected_move_pct"] == 4.0
    assert scored["mtf_precision"] is False


def test_seven_requires_15m_and_1h() -> None:
    from app.engines.pattern_scoring import score_technical_confirmations

    only_15m = score_technical_confirmations(
        {"setup_rattle": True, "mtf_15m_coil_ema": True},
        side="long",
    )
    assert only_15m["technical_score"] == 6.0
    assert only_15m["expected_move_pct"] == 4.0
    assert only_15m["mtf_precision"] is False

    only_1h = score_technical_confirmations(
        {"setup_rattle": True, "mtf_1h_coil_ema": True},
        side="long",
    )
    assert only_1h["technical_score"] == 6.0
    assert only_1h["mtf_precision"] is False

    both = score_technical_confirmations(
        {"setup_rattle": True, "mtf_15m_coil_ema": True, "mtf_1h_coil_ema": True},
        side="long",
    )
    assert both["technical_score"] == 7.0
    assert both["expected_move_pct"] == 5.0
    assert both["mtf_precision"] is True

    wedge_round = score_technical_confirmations(
        {"setup_rattle": True, "mtf_15m_wedge": True, "mtf_1h_rounding_ema20": True},
        side="long",
    )
    assert wedge_round["technical_score"] == 7.0
    assert wedge_round["expected_move_pct"] == 5.0
    assert wedge_round["confirmation_labels"][-1] == "Expect next move ~5%"


def test_two_piece_family_with_energy_is_six_without_mtf() -> None:
    from app.engines.pattern_scoring import score_technical_confirmations

    scored = score_technical_confirmations(
        {
            "ema20_support": True,
            "uptrend": True,
            "vol_expansion": True,
            "setup_rattle": True,
        },
        side="long",
    )
    assert scored["technical_score"] == 6.0
    assert scored["expected_move_pct"] == 4.0
    assert "ema_pullback" in scored["pattern_families"]
    assert scored["score_layers"]["energy"] == 2.0


def test_coil_at_ema_and_fib_is_five_expect_three() -> None:
    from app.engines.pattern_scoring import score_technical_confirmations

    scored = score_technical_confirmations(
        {
            "ema20_support": True,
            "uptrend": True,
            "sr_level": True,
            "sr_fib_confluence": True,
            "tight_range": True,
            "consolidation_anchor": True,
            "ema_momentum_expanding": True,
            "dead_volume": True,
            "vol_expansion": False,
            "range_expansion": False,
        },
        side="long",
    )
    assert scored["technical_score"] == 5.0
    assert scored["expected_move_pct"] == 3.0
    assert scored["score_layers"]["sr_fib"] == 2.5
    assert scored["score_layers"]["coil"] == 0.5
    assert scored["score_layers"]["energy"] == 0.0
    assert any("coil" in label.lower() for label in scored["confirmation_labels"])


def test_ema_fib_energy_without_mtf_is_six() -> None:
    from app.engines.pattern_scoring import score_technical_confirmations

    scored = score_technical_confirmations(
        {
            "ema20_support": True,
            "uptrend": True,
            "sr_level": True,
            "sr_fib_confluence": True,
            "vol_expansion": True,
            "setup_rattle": True,
        },
        side="long",
    )
    assert scored["technical_score"] == 6.0
    assert scored["expected_move_pct"] == 4.0
    assert scored["score_layers"]["energy"] == 2.0
    assert scored["score_layers"]["sr_fib"] == 2.5


def test_elliott_formation_candle_are_cherries() -> None:
    from app.engines.pattern_scoring import score_technical_confirmations

    scored = score_technical_confirmations(
        {
            "ema20_support": True,
            "uptrend": True,
            "sr_fib_confluence": True,
            "tight_range": True,
            "elliott_aligned": True,
            "bullish_formation": True,
            "vol_expansion": True,
            "setup_rattle": True,
        },
        side="long",
        snapshot={
            "tags": ["elliott_impulse_up", "fib_0.618_retrace", "near_support", "candle_hammer"],
            "formations": [{"id": "falling_wedge"}],
        },
    )
    assert scored["technical_score"] == 6.0
    assert scored["score_layers"]["elliott"] == 0.5
    assert scored["score_layers"]["formation"] == 0.5
    assert scored["score_layers"]["candle"] == 0.5
    assert any("cherry" in label.lower() for label in scored["confirmation_labels"])


def test_energy_seven_does_not_require_sr_fib() -> None:
    from app.engines.pattern_scoring import score_technical_confirmations

    scored = score_technical_confirmations(
        {
            "ema20_support": True,
            "uptrend": True,
            "elliott_aligned": True,
            "bullish_formation": True,
            "vol_expansion": True,
            "setup_rattle": True,
        },
        side="long",
        snapshot={"tags": ["elliott_impulse_up", "candle_hammer"], "formations": [{"id": "falling_wedge"}]},
    )
    assert scored["score_layers"]["sr_fib"] == 0.0
    assert scored["technical_score"] == 6.0


def test_elliott_conflict_zeros_cherry_not_whole_score() -> None:
    from app.engines.pattern_scoring import score_technical_confirmations

    scored = score_technical_confirmations(
        {
            "ema20_support": True,
            "uptrend": True,
            "sr_fib_confluence": True,
            "consolidation_anchor": True,
            "bullish_formation": True,
            "elliott_conflict": True,
            "vol_expansion": True,
            "setup_rattle": True,
        },
        side="long",
        snapshot={"tags": ["elliott_impulse_down"], "formations": [{"id": "falling_wedge"}]},
    )
    assert scored["score_layers"]["elliott"] == 0.0
    assert scored["technical_score"] == 6.0


def test_candle_cherry_requires_context() -> None:
    from app.engines.pattern_scoring import score_technical_confirmations

    scored = score_technical_confirmations(
        {"vol_expansion": True, "range_expansion": True, "setup_rattle": False},
        side="long",
        snapshot={"tags": ["candle_morning_star"], "formations": []},
    )
    assert scored["score_layers"]["candle"] == 0.0
    assert scored["technical_score"] < 7.0
    assert scored["precision_energy"] is False


def test_family_without_coil_and_fib_is_not_high_conviction() -> None:
    from app.engines.pattern_scoring import score_technical_confirmations

    scored = score_technical_confirmations(
        {"ema20_support": True, "uptrend": True, "vol_expansion": False, "range_expansion": False},
        side="long",
    )
    assert scored["technical_score"] < 7.0


def test_energy_prints_seven_even_if_extended() -> None:
    from app.engines.pattern_scoring import score_technical_confirmations

    scored = score_technical_confirmations(
        {
            "ema20_support": True,
            "uptrend": True,
            "sr_fib_confluence": True,
            "tight_range": True,
            "vol_expansion": True,
            "setup_rattle": True,
        },
        side="long",
        snapshot={"tags": ["ema20_extended_long", "near_resistance", "rsi_overbought"], "formations": []},
    )
    assert scored["technical_score"] == 6.0


def test_adanipower_sep18_coil_is_not_seven() -> None:
    path = ohlcv_daily_dir() / "ADANIPOWER.parquet"
    if not path.exists():
        return
    frame = load_ohlcv(path)
    signal_date = "2025-09-18"
    idx = frame.index.get_indexer([pd.Timestamp(signal_date)], method="nearest")[0]
    slice = frame.iloc[: idx + 1]
    conf = detect_daily_confirmations(slice, "long")
    assert conf["ema20_support"]
    assert conf["sr_fib_confluence"]
    assert conf["tight_range"] or conf["consolidation_anchor"]
    assert not conf["vol_expansion"]

    hist = [m for m in load_moves("ADANIPOWER") if m["date"] < signal_date]
    setup = scan_today_setup(slice, hist, side="long", symbol="ADANIPOWER")
    assert setup["technical_score"] <= 5.0

    gap_idx = frame.index.get_indexer([pd.Timestamp("2025-09-19")], method="nearest")[0]
    gap = scan_today_setup(frame.iloc[: gap_idx + 1], hist, side="long", symbol="ADANIPOWER")
    assert gap["technical_score"] < 7.0


def test_empty_confirmations_not_seven() -> None:
    from app.engines.pattern_scoring import score_technical_confirmations

    scored = score_technical_confirmations({}, side="long")
    assert scored["technical_score"] < 7.0
    scores = conviction_from_scores(technical=9.5, fundamental=10, events=10, theme=8)
    assert scores["technical"] == 7.0
    assert scores["research"] <= 3.0
    assert 1.0 <= scores["theme_bonus"] <= 5.0
    assert scores["final"] <= 10.0
