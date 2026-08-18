from app.engines.target_trade import classify_open_gap, is_eod_target_watch, target_trade_payload


def test_late_bar_is_not_a_watch() -> None:
    assert is_eod_target_watch({"late_bar": True, "setup_rattle": True, "uptrend": False}, rsi=30) is False


def test_uptrend_coil_is_not_a_watch() -> None:
    assert is_eod_target_watch({"uptrend": True, "setup_rattle": False, "late_bar": False}, rsi=55) is False
    assert is_eod_target_watch({"uptrend": True, "tight_range": True, "ema20_support": True}, rsi=35) is False


def test_washout_rsi_or_rattle_is_a_watch() -> None:
    assert is_eod_target_watch({"uptrend": False, "late_bar": False, "setup_rattle": False}, rsi=32) is True
    assert is_eod_target_watch({"uptrend": False, "late_bar": False, "setup_rattle": True}, rsi=55) is True
    assert is_eod_target_watch({"uptrend": False, "late_bar": False, "setup_rattle": False}, rsi=55) is False
    assert is_eod_target_watch({"uptrend": False, "late_bar": False, "setup_rattle": False}, rsi=None) is False


def test_open_gap_drive_and_late() -> None:
    drive = classify_open_gap(0.9, 2.0)
    assert drive["open_drive"] is True
    assert drive["rare_take"] is False
    assert drive["already_printed"] is False
    take = classify_open_gap(1.6, 2.0)
    assert take["rare_take"] is True
    assert take["take_conviction"] >= 7.0
    assert take["remaining_pct"] == 0.4
    late = classify_open_gap(2.1, 2.0)
    assert late["open_drive"] is False
    assert late["rare_take"] is False
    assert late["already_printed"] is True
    tiny = classify_open_gap(0.2, 2.0)
    assert tiny["open_drive"] is False
    assert tiny["rare_take"] is False


def test_payload_sets_expected_move_only_on_watch() -> None:
    watch = target_trade_payload({"uptrend": False, "setup_rattle": True, "late_bar": False}, rsi=50, target_pct=3.0)
    assert watch["target_watch"] is True
    assert watch["expected_move_pct"] == 3.0
    assert watch["rare_take"] is False
    quiet = target_trade_payload({"uptrend": True, "setup_rattle": False, "late_bar": False}, rsi=60, target_pct=3.0)
    assert quiet["target_watch"] is False
    assert quiet["expected_move_pct"] == 0.0


def test_payload_rare_take_uses_remaining() -> None:
    take = target_trade_payload(
        {"uptrend": False, "setup_rattle": True, "late_bar": False},
        rsi=50,
        target_pct=2.0,
        gap_pct=1.6,
    )
    assert take["rare_take"] is True
    assert take["expected_move_pct"] == 0.4


def test_pick_daily_takes_keeps_largest_gap() -> None:
    from app.engines.target_trade import pick_daily_takes

    rows = [
        {"symbol": "HDFCBANK", "as_of": "2026-08-03", "rare_take": True, "gap_frac": 0.78, "reasons": []},
        {"symbol": "NIFTY_50", "as_of": "2026-08-03", "rare_take": True, "gap_frac": 0.91, "reasons": []},
        {"symbol": "M&M", "as_of": "2026-08-03", "rare_take": False, "gap_frac": 0.2, "reasons": []},
    ]
    out = pick_daily_takes(rows)
    by = {row["symbol"]: row for row in out}
    assert by["NIFTY_50"]["rare_take"] is True
    assert by["HDFCBANK"]["rare_take"] is False
    assert by["M&M"]["rare_take"] is False
