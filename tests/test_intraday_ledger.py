import pandas as pd

from app.engines.intraday_ledger import (
    append_ledger,
    load_ledger,
    next_session_result,
    recompute_rule_stats,
    rewrite_ledger,
)
from app.engines.universe import load_trading_instruments


def test_trading_book_is_five_scrips() -> None:
    symbols = [row["symbol"] for row in load_trading_instruments()]
    assert symbols == ["HDFCBANK", "BAJFINANCE", "M&M", "NIFTY_50", "NIFTY_BANK"]


def test_next_session_mfe_from_setup_close() -> None:
    frame = pd.DataFrame(
        {
            "open": [100.0, 101.0],
            "high": [101.0, 104.0],
            "low": [99.0, 100.5],
            "close": [100.0, 102.0],
            "volume": [1_000_000, 1_200_000],
            "symbol": ["TEST", "TEST"],
        },
        index=pd.to_datetime(["2026-08-10", "2026-08-11"]),
    )
    result = next_session_result(frame, "2026-08-10")
    assert result is not None
    assert result["next_date"] == "2026-08-11"
    assert result["mfe_pct"] == 4.0
    assert next_session_result(frame, "2026-08-11") is None


def test_rule_stats_trust_only_at_n20(tmp_path, monkeypatch) -> None:
    import app.engines.intraday_ledger as ledger

    monkeypatch.setattr(ledger, "intraday_ledger_path", lambda: tmp_path / "ledger.jsonl")
    monkeypatch.setattr(ledger, "intraday_rule_stats_path", lambda: tmp_path / "rule_stats.json")
    rewrite_ledger([])
    append_ledger(
        {
            "symbol": "HDFCBANK",
            "setup_date": "2026-08-10",
            "side": "long",
            "session_seven": True,
            "rattle": True,
            "range_expansion": True,
            "live_rvol": True,
            "tight_range": False,
            "mfe_pct": 2.4,
        }
    )
    stats = recompute_rule_stats()
    assert stats["rules"]["session_seven"]["n"] == 1
    assert stats["rules"]["session_seven"]["trusted"] is False
    assert "n>=20" in stats["advice"]
    assert load_ledger()[0]["mfe_pct"] == 2.4
