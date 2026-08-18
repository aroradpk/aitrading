import pandas as pd

from app.engines.target_day import attach_upside, format_report, scan_symbol_up_days


def test_upside_hit_is_high_vs_prior_close() -> None:
    frame = pd.DataFrame(
        {
            "open": [100.0] * 45 + [100.5],
            "high": [101.0] * 45 + [103.5],
            "low": [99.0] * 45 + [100.2],
            "close": [100.0] * 45 + [102.0],
            "volume": [1_000_000] * 46,
            "symbol": ["HDFCBANK"] * 46,
        },
        index=pd.bdate_range("2025-01-02", periods=46),
    )
    result = scan_symbol_up_days(frame, symbol="HDFCBANK")
    assert result["lookback"]["target_range_pct"] == 2.0
    dates = [day["date"] for day in result["days"]]
    assert dates[0] == frame.index[-1].date().isoformat()
    assert result["days"][0]["upside_pct"] == 3.5
    assert result["n_hit_days"] >= 1


def test_report_starts_with_lookback() -> None:
    book = {
        "hit_definition": "test",
        "coverage": {
            "symbols": ["HDFCBANK"],
            "sessions_sum": 10,
            "oldest_bar": "2021-01-01",
            "newest_bar": "2026-08-14",
        },
        "instruments": [
            {
                "lookback": {
                    "symbol": "HDFCBANK",
                    "target_range_pct": 2.0,
                    "first": "2021-01-01",
                    "last": "2026-08-14",
                    "sessions": 10,
                },
                "n_hit_days": 0,
                "n_scored_sessions": 10,
                "base_hit_pct": 0.0,
                "flag_rates": [],
                "days": [],
            }
        ],
    }
    text = format_report(book)
    assert "2021-01-01 → 2026-08-14" in text


def test_attach_upside_columns() -> None:
    frame = pd.DataFrame(
        {
            "open": [100.0, 101.0],
            "high": [101.0, 104.0],
            "low": [99.0, 100.0],
            "close": [100.0, 102.0],
            "volume": [1, 1],
        },
        index=pd.to_datetime(["2026-08-10", "2026-08-11"]),
    )
    out = attach_upside(frame)
    assert round(float(out["upside_pct"].iloc[1]), 2) == 4.0
    assert round(float(out["close_pct"].iloc[1]), 2) == 2.0
