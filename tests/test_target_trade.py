from datetime import date, timedelta

from app.engines.target_trade import (
    is_eod_target_watch,
    is_move_setup,
    is_rare_eod_setup,
    next_day_outcome,
    pick_move_setups,
    pick_rare_eod_trades,
    target_trade_payload,
)
import pandas as pd


def test_late_bar_is_not_a_move_setup() -> None:
    assert is_move_setup({"late_bar": True, "setup_rattle": True}) is False
    assert is_rare_eod_setup({"late_bar": True, "setup_rattle": True}, rsi=20) is False


def test_rattle_is_direction_agnostic() -> None:
    uptrend = {"late_bar": False, "setup_rattle": True, "uptrend": True}
    assert is_move_setup(uptrend) is True
    assert is_eod_target_watch(uptrend, rsi=70) is True
    assert is_rare_eod_setup(uptrend, rsi=70) is True


def test_coil_without_rattle_is_not_a_setup() -> None:
    coil = {"late_bar": False, "setup_rattle": False, "tight_range": True, "ema20_support": True}
    assert is_move_setup(coil) is False
    assert is_eod_target_watch(coil, rsi=35) is False


def test_strong_close_alone_is_not_enough() -> None:
    quiet = {"late_bar": False, "setup_rattle": False, "strong_close": True, "uptrend": False}
    assert is_move_setup(quiet) is False


def test_payload_expects_half_percent_capture() -> None:
    payload = target_trade_payload(
        {"late_bar": False, "setup_rattle": True},
        rsi=55,
        target_pct=3.0,
        range_pct=3.2,
    )
    assert payload["move_watch"] is True
    assert payload["target_watch"] is True
    assert payload["expected_move_pct"] == 0.5
    assert payload["expected_horizon_days"] == 1
    quiet = target_trade_payload({"late_bar": False, "setup_rattle": False}, rsi=18, target_pct=3.0)
    assert quiet["move_watch"] is False
    assert quiet["expected_move_pct"] == 0.0


def test_next_day_outcome_is_close_to_close_not_gap() -> None:
    nxt = pd.Series({"open": 110.0, "high": 101.2, "low": 99.4, "close": 101.0})
    out = next_day_outcome(100.0, nxt)
    assert out["abs_close_pct"] == 1.0
    assert out["movement_05"] is True
    assert out["one_way"] is True
    assert out["trend_05"] is True
    inside = pd.Series({"open": 100.0, "high": 101.0, "low": 99.0, "close": 100.2})
    mid = next_day_outcome(100.0, inside)
    assert mid["movement_05"] is False
    assert mid["one_way"] is False


def test_pick_keeps_one_per_day_and_four_per_week() -> None:
    monday = date(2026, 3, 9)
    rows = []
    for offset in range(6):
        day = (monday + timedelta(days=offset)).isoformat()
        rows.append(
            {
                "symbol": "HDFCBANK",
                "as_of": day,
                "move_watch": True,
                "move_score": 3.0 + offset,
                "reasons": [],
            }
        )
        rows.append(
            {
                "symbol": "M&M",
                "as_of": day,
                "move_watch": True,
                "move_score": 1.0,
                "reasons": [],
            }
        )
    out = pick_move_setups(rows)
    kept = [row for row in out if row["move_watch"]]
    assert all(row["symbol"] == "HDFCBANK" for row in kept)
    assert len(kept) == 4
    assert len({row["as_of"] for row in kept}) == 4
    compat = pick_rare_eod_trades(
        [
            {"symbol": "NIFTY_50", "as_of": monday.isoformat(), "rare_eod": True, "rare_eod_score": 4.0, "reasons": []},
            {"symbol": "NIFTY_BANK", "as_of": monday.isoformat(), "rare_eod": True, "rare_eod_score": 1.0, "reasons": []},
        ]
    )
    assert [row["symbol"] for row in compat if row["move_watch"]] == ["NIFTY_50"]
