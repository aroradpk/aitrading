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

    scores = conviction_from_scores(setup["technical_score"])
    assert scores["technical"] >= 7.0
    assert scores["final"] >= 7.0


def test_conviction_model_caps_technical_at_seven() -> None:
    scores = conviction_from_scores(technical=9.5, fundamental=10, events=10, theme=8)
    assert scores["technical"] == 7.0
    assert scores["research"] <= 3.0
    assert 1.0 <= scores["theme_bonus"] <= 5.0
    assert scores["final"] <= 10.0
