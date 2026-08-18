from datetime import date, timedelta

from app.engines.target_trade import (
    is_eod_target_watch,
    is_rare_eod_setup,
    pick_rare_eod_trades,
    rare_eod_score,
    target_trade_payload,
)


def test_late_and_uptrend_are_not_rare() -> None:
    assert is_rare_eod_setup({"late_bar": True, "setup_rattle": True, "uptrend": False, "strong_close": True}, rsi=20) is False
    assert is_rare_eod_setup({"late_bar": False, "setup_rattle": True, "uptrend": True, "strong_close": True}, rsi=20) is False
    assert is_eod_target_watch({"uptrend": True, "tight_range": True, "ema20_support": True}, rsi=35) is False


def test_wide_watch_is_not_the_rare_trade() -> None:
    conf = {"uptrend": False, "late_bar": False, "setup_rattle": True, "strong_close": False}
    assert is_eod_target_watch(conf, rsi=55) is True
    assert is_rare_eod_setup(conf, rsi=55) is False
    assert is_rare_eod_setup(conf, rsi=32) is False
    assert is_rare_eod_setup(conf, rsi=29) is True


def test_rare_needs_energy_and_low_rsi() -> None:
    quiet = {"uptrend": False, "late_bar": False, "setup_rattle": False, "strong_close": False}
    assert is_rare_eod_setup(quiet, rsi=18) is False
    assert is_rare_eod_setup({**quiet, "strong_close": True}, rsi=18) is True
    assert rare_eod_score({**quiet, "setup_rattle": True, "strong_close": True}, rsi=18) > rare_eod_score(
        {**quiet, "setup_rattle": True}, rsi=29
    )


def test_payload_only_expects_move_on_rare() -> None:
    rare = target_trade_payload(
        {"uptrend": False, "late_bar": False, "setup_rattle": True, "strong_close": True},
        rsi=22,
        target_pct=2.0,
    )
    assert rare["rare_eod"] is True
    assert rare["expected_move_pct"] == 2.0
    watch = target_trade_payload(
        {"uptrend": False, "late_bar": False, "setup_rattle": True, "strong_close": False},
        rsi=50,
        target_pct=2.0,
    )
    assert watch["target_watch"] is True
    assert watch["rare_eod"] is False
    assert watch["expected_move_pct"] == 0.0


def test_pick_keeps_one_per_day_and_four_per_week() -> None:
    monday = date(2026, 3, 9)
    rows = []
    for offset in range(6):
        day = (monday + timedelta(days=offset)).isoformat()
        rows.append(
            {
                "symbol": "HDFCBANK",
                "as_of": day,
                "rare_eod": True,
                "rare_eod_score": 3.0 + offset,
                "reasons": [],
            }
        )
        rows.append(
            {
                "symbol": "M&M",
                "as_of": day,
                "rare_eod": True,
                "rare_eod_score": 1.0,
                "reasons": [],
            }
        )
    out = pick_rare_eod_trades(rows)
    kept = [row for row in out if row["rare_eod"]]
    assert all(row["symbol"] == "HDFCBANK" for row in kept)
    assert len(kept) == 4
    assert len({row["as_of"] for row in kept}) == 4
