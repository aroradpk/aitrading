"""Learn from outcomes: log every setup, fill next-session result, refresh hit rates.

This is not a neural net. After each session we record what we saw and what price
did next. Flags are descriptive — nothing here assigns a 5/6/7 trade setup.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any

import pandas as pd

from app.core.paths import intraday_ledger_path, intraday_rule_stats_path, ohlcv_daily_dir
from app.engines.adr import next_session_range_hit
from app.engines.target_trade import next_day_outcome
from app.engines.universe import all_instruments
from app.ingest.yfinance_client import load_ohlcv

TRAIT_COLUMNS = (
    "move_watch",
    "target_watch",
    "rare_eod",
    "session_seven",
    "rattle",
    "range_expansion",
    "live_rvol",
    "tight_range",
)

HIT_BARS = (2.0, 3.0, 5.0)
MIN_N_TO_TRUST = 20


def append_ledger(row: dict[str, Any]) -> None:
    path = intraday_ledger_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(row, default=str) + "\n")


def load_ledger() -> list[dict]:
    path = intraday_ledger_path()
    if not path.exists():
        return []
    rows = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line:
            rows.append(json.loads(line))
    return rows


def rewrite_ledger(rows: list[dict]) -> None:
    path = intraday_ledger_path()
    with path.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, default=str) + "\n")


def _index_for_setup_date(frame: pd.DataFrame, setup_date: str) -> int | None:
    target = pd.Timestamp(setup_date).normalize()
    for i, stamp in enumerate(frame.index):
        if pd.Timestamp(stamp).normalize() == target:
            return i
    return None


def next_session_result(frame: pd.DataFrame, setup_date: str) -> dict | None:
    idx = _index_for_setup_date(frame, setup_date)
    if idx is None or idx + 1 >= len(frame):
        return None
    setup_close = float(frame["close"].iloc[idx])
    nxt = frame.iloc[idx + 1]
    mfe = max(
        abs(float(nxt["high"]) / setup_close - 1) * 100,
        abs(float(nxt["low"]) / setup_close - 1) * 100,
    )
    close_pct = abs(float(nxt["close"]) / setup_close - 1) * 100
    move = next_day_outcome(setup_close, nxt)
    result = {
        "next_date": frame.index[idx + 1].date().isoformat(),
        "mfe_pct": round(mfe, 3),
        "close_abs_pct": round(close_pct, 3),
        "close_pct": round(float(nxt["close"] / setup_close - 1) * 100, 3),
        "one_way": move["one_way"],
        "hit_move_05": move["movement_05"],
        "hit_trend_05": move["trend_05"],
        "hit_trend_10": move["trend_10"],
    }
    extra = next_session_range_hit(frame, setup_date)
    if extra:
        result.update(extra)
    return result


def resolve_open_rows() -> int:
    rows = load_ledger()
    filled = 0
    by_symbol: dict[str, pd.DataFrame] = {}
    for row in rows:
        symbol = row["symbol"]
        if symbol not in by_symbol:
            path = ohlcv_daily_dir() / f"{symbol}.parquet"
            if not path.exists():
                continue
            by_symbol[symbol] = load_ohlcv(path)
        outcome = next_session_result(by_symbol[symbol], row["setup_date"])
        if not outcome:
            continue
        before = (row.get("hit_adr"), row.get("target_range_pct"), row.get("mfe_pct"))
        row.update(outcome)
        if before != (row.get("hit_adr"), row.get("target_range_pct"), row.get("mfe_pct")):
            filled += 1
    rewrite_ledger(rows)
    return filled


def recompute_rule_stats() -> dict:
    rows = [r for r in load_ledger() if r.get("mfe_pct") is not None]
    stats: dict[str, Any] = {
        "updated_at": datetime.now(timezone.utc).isoformat(),
        "resolved_rows": len(rows),
        "min_n_to_trust": MIN_N_TO_TRUST,
        "note": (
            "Logged flags vs next close-to-close. Movement screener hit = |c2c|>=0.5%. "
            "Direction is not predicted. Trusted only at n>=20. No 7-gate."
        ),
        "rules": {},
    }
    if not rows:
        intraday_rule_stats_path().write_text(json.dumps(stats, indent=2), encoding="utf-8")
        return stats

    frame = pd.DataFrame(rows)

    def pack(mask: pd.Series, name: str) -> dict:
        sub = frame[mask]
        n = int(len(sub))
        out = {"n": n, "trusted": n >= MIN_N_TO_TRUST}
        if n == 0:
            out["hit_adr"] = None
            for bar in HIT_BARS:
                out[f"hit_mfe_{bar:.0f}"] = None
            return out
        if "hit_adr" in sub.columns:
            hits = int(sub["hit_adr"].fillna(False).astype(bool).sum())
            out["hit_adr"] = round(100 * hits / n, 1)
            out["false_alarm_adr"] = round(100 * (n - hits) / n, 1)
        if "hit_move_05" in sub.columns:
            hits = int(sub["hit_move_05"].fillna(False).astype(bool).sum())
            out["hit_move_05"] = round(100 * hits / n, 1)
            out["false_move_05"] = round(100 * (n - hits) / n, 1)
        if "hit_trend_05" in sub.columns:
            hits = int(sub["hit_trend_05"].fillna(False).astype(bool).sum())
            out["hit_trend_05"] = round(100 * hits / n, 1)
            out["false_trend_05"] = round(100 * (n - hits) / n, 1)
        for bar in HIT_BARS:
            hits = int((sub["mfe_pct"] >= bar).sum())
            out[f"hit_mfe_{bar:.0f}"] = round(100 * hits / n, 1)
            out[f"false_alarm_mfe_{bar:.0f}"] = round(100 * (n - hits) / n, 1)
        return out

    stats["rules"]["all_logged"] = pack(pd.Series([True] * len(frame)), "all")
    for col in TRAIT_COLUMNS:
        if col in frame.columns:
            stats["rules"][col] = pack(frame[col].fillna(False).astype(bool), col)

    move = stats["rules"].get("move_watch") or stats["rules"].get("target_watch") or {}
    stats["advice"] = (
        "Movement screener = today's rumble (range>=2.5%, close not ±5%); 1 name/day and 4/week. "
        "Hit = |next close vs today close| >= 0.5%. Direction is the trader's next morning. "
        f"move_watch n={move.get('n', 0)} hit_c2c_0.5={move.get('hit_move_05')}. "
        "90% hit / 10% false is not available from yesterday's close."
    )
    stats_path = intraday_rule_stats_path()
    stats_path.write_text(json.dumps(stats, indent=2), encoding="utf-8")
    return stats


def log_today_setups(setups: list[dict]) -> int:
    """Write one ledger row per setup that does not already exist for that symbol+date."""
    existing = {(r.get("symbol"), r.get("setup_date"), r.get("side")) for r in load_ledger()}
    n = 0
    for setup in setups:
        key = (setup.get("symbol"), setup.get("as_of") or setup.get("setup_date"), setup.get("position_side"))
        if key in existing:
            continue
        conf = setup.get("pattern_confirmations") or {}
        row = {
            "symbol": setup.get("symbol"),
            "setup_date": setup.get("as_of"),
            "side": setup.get("position_side"),
            "technical_score": setup.get("technical_score"),
            "expected_move_pct": setup.get("expected_move_pct"),
            "session_seven": False,
            "move_watch": bool(setup.get("move_watch") or setup.get("target_watch")),
            "target_watch": bool(setup.get("target_watch") or setup.get("move_watch")),
            "rare_eod": bool(setup.get("move_watch") or setup.get("rare_eod")),
            "adr20_pct": (setup.get("adr") or {}).get("adr20_pct") or setup.get("adr20_pct"),
            "target_range_pct": (setup.get("adr") or {}).get("target_range_pct") or setup.get("target_range_pct"),
            "rattle": bool(conf.get("setup_rattle")),
            "range_expansion": bool(conf.get("range_expansion")),
            "live_rvol": bool(conf.get("live_rvol")),
            "tight_range": bool(conf.get("tight_range")),
            "logged_at": datetime.now(timezone.utc).isoformat(),
            "mfe_pct": None,
        }
        append_ledger(row)
        existing.add(key)
        n += 1
    return n


def backfill_ledger(*, lookback_bars: int = 60) -> int:
    """Replay recent daily bars into the ledger so hit rates can start before live days pile up."""
    from app.engines.pattern_confirmations import detect_daily_confirmations
    from app.engines.target_trade import is_move_setup

    existing = {(r.get("symbol"), r.get("setup_date"), r.get("side")) for r in load_ledger()}
    n = 0
    for instrument in all_instruments():
        symbol = instrument["symbol"]
        path = ohlcv_daily_dir() / f"{symbol}.parquet"
        if not path.exists():
            continue
        frame = load_ohlcv(path)
        start = max(40, len(frame) - lookback_bars - 1)
        for i in range(start, len(frame) - 1):
            slice_frame = frame.iloc[: i + 1]
            setup_date = slice_frame.index[-1].date().isoformat()
            for side in ("long", "short"):
                key = (symbol, setup_date, side)
                if key in existing:
                    continue
                conf = detect_daily_confirmations(slice_frame, side)
                watch = is_move_setup(conf) if side == "long" else False
                row = {
                    "symbol": symbol,
                    "setup_date": setup_date,
                    "side": side,
                    "technical_score": None,
                    "expected_move_pct": 0.5 if watch else None,
                    "session_seven": False,
                    "move_watch": watch,
                    "target_watch": watch,
                    "rare_eod": watch,
                    "rattle": bool(conf.get("setup_rattle")),
                    "range_expansion": bool(conf.get("range_expansion")),
                    "live_rvol": bool(conf.get("live_rvol")),
                    "tight_range": bool(conf.get("tight_range")),
                    "logged_at": datetime.now(timezone.utc).isoformat(),
                    "source": "backfill",
                    "mfe_pct": None,
                }
                append_ledger(row)
                existing.add(key)
                n += 1
    return n
