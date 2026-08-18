import pandas as pd

from app.engines.move_detector import scan_setups_for_symbol, scan_today_setup
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


def _downtrend_frame() -> pd.DataFrame:
    dates = pd.date_range("2024-01-01", periods=120, freq="B")
    prices = [200 - (i * 0.35) for i in range(120)]
    return pd.DataFrame(
        {
            "open": prices,
            "high": [p + 1.0 for p in prices],
            "low": [p - 1.2 for p in prices],
            "close": prices,
            "volume": [1_000_000] * 120,
            "symbol": ["TEST"] * 120,
        },
        index=dates,
    )


def test_position_bias_short_on_downtrend() -> None:
    snap = build_snapshot(_downtrend_frame(), focus="short")
    assert position_bias(snap, focus="short") == "short"
    assert snap["position_bias_short"] == "short"


def test_scan_short_matches_down_moves(monkeypatch) -> None:
    frame = _downtrend_frame()
    moves = [
        {
            "date": "2024-03-01",
            "direction": "down",
            "move_1d_pct": -6.0,
            "technical_snapshot": build_snapshot(frame.loc[: "2024-03-01"], focus="short"),
        },
        {
            "date": "2024-03-15",
            "direction": "up",
            "move_1d_pct": 5.0,
            "technical_snapshot": build_snapshot(frame.loc[: "2024-03-15"], focus="long"),
        },
    ]
    setup = scan_today_setup(frame, moves, side="short", intraday=False)
    assert setup["position_side"] == "short"
    assert setup["match_count"] >= 0
    if setup["top_matches"]:
        assert all(m["move_1d_pct"] < 0 for m in setup["top_matches"])


def test_scan_setups_returns_long_and_short(monkeypatch) -> None:
    from app.core.config import get_settings

    settings = get_settings()
    monkeypatch.setattr(settings.technical, "position_focus", "both")
    monkeypatch.setattr(settings.technical.intraday, "enabled", False)

    frame = _uptrend_frame()
    setups = scan_setups_for_symbol(frame, [])
    sides = {setup["position_side"] for setup in setups}
    assert "long" in sides
    assert "short" in sides


def test_intraday_setup_tags_horizon(monkeypatch) -> None:
    from app.core.config import get_settings

    settings = get_settings()
    monkeypatch.setattr(settings.technical.intraday, "enabled", True)
    monkeypatch.setattr(settings.technical.intraday, "position_side", "short")
    monkeypatch.setattr(settings.technical, "position_focus", "short")

    frame = _downtrend_frame()
    moves = [
        {
            "date": "2024-03-01",
            "direction": "down",
            "move_1d_pct": -3.0,
            "technical_snapshot": build_snapshot(frame.loc[: "2024-03-01"], focus="short"),
        }
    ]
    setup = scan_today_setup(frame, moves, side="short", intraday=True)
    assert setup["horizon"] == "next_session"
    assert setup["intraday"] is True
    assert "adr20_pct" in setup["adr"]
