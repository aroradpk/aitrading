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
    assert drive["already_printed"] is False
    late = classify_open_gap(2.1, 2.0)
    assert late["open_drive"] is False
    assert late["already_printed"] is True
    tiny = classify_open_gap(0.2, 2.0)
    assert tiny["open_drive"] is False


def test_payload_sets_expected_move_only_on_watch() -> None:
    watch = target_trade_payload({"uptrend": False, "setup_rattle": True, "late_bar": False}, rsi=50, target_pct=3.0)
    assert watch["target_watch"] is True
    assert watch["expected_move_pct"] == 3.0
    quiet = target_trade_payload({"uptrend": True, "setup_rattle": False, "late_bar": False}, rsi=60, target_pct=3.0)
    assert quiet["target_watch"] is False
    assert quiet["expected_move_pct"] == 0.0
