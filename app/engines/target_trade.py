"""Intraday movement screener: will tomorrow likely trend one way?

The trader picks direction the next morning. We only forecast *movement*:
next close vs today's close, and whether that session finishes one-way
(close in the top or bottom 30% of its range). Gaps are ignored.

Capture target is 0.5–1% of a larger day. Hit for the screener:

- movement_05: |next close / today close - 1| >= 0.5%
- trend_05: movement_05 and a one-way close

EOD setup (either direction): today's range >= 2.5% of prior close and the
close is not already a ±5% late bar (`setup_rattle`). Then 1 name/day, 4/week.

Holdout 2025-08-18 → 2026-08-14 (1/day, 4/week): ~77% |c2c|>=0.5%,
~58% one-way and |c2c|>=0.5%, vs ~60% / ~44% on every day.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

import pandas as pd

MAX_TRADES_PER_DAY = 1
MAX_TRADES_PER_WEEK = 4
CAPTURE_PCT = 0.5
ONE_WAY_EDGE = 0.30


def _as_date(value: str | None) -> datetime | None:
    if not value:
        return None
    return datetime.fromisoformat(str(value)[:10])


def is_move_setup(confirmations: dict[str, bool]) -> bool:
    """Today printed energy but not a finished ±5% close — next day may trend."""
    if confirmations.get("late_bar"):
        return False
    return bool(confirmations.get("setup_rattle"))


def move_setup_score(confirmations: dict[str, bool], *, range_pct: float | None = None) -> float:
    if not is_move_setup(confirmations):
        return 0.0
    score = float(range_pct or 2.5)
    if confirmations.get("live_rvol"):
        score += 1.0
    if confirmations.get("vol_expansion"):
        score += 1.0
    if confirmations.get("range_expansion"):
        score += 0.5
    return round(score, 3)


def next_day_outcome(today_close: float, nxt: pd.Series) -> dict[str, Any]:
    """Close-to-close and one-way flags. No gaps."""
    close = float(nxt["close"])
    high = float(nxt["high"])
    low = float(nxt["low"])
    c2c = (close / today_close - 1.0) * 100 if today_close else 0.0
    span = high - low
    loc = (close - low) / span if span > 0 else 0.5
    one_way = loc <= ONE_WAY_EDGE or loc >= (1.0 - ONE_WAY_EDGE)
    abs_c2c = abs(c2c)
    return {
        "close_pct": round(c2c, 3),
        "abs_close_pct": round(abs_c2c, 3),
        "one_way": bool(one_way),
        "close_loc": round(loc, 3),
        "movement_05": abs_c2c >= CAPTURE_PCT,
        "trend_05": bool(one_way and abs_c2c >= CAPTURE_PCT),
        "trend_10": bool(one_way and abs_c2c >= 1.0),
    }


def pick_move_setups(
    entries: list[dict],
    *,
    max_per_day: int = MAX_TRADES_PER_DAY,
    max_per_week: int = MAX_TRADES_PER_WEEK,
) -> list[dict]:
    scored = [dict(row) for row in entries]
    by_day: dict[str, list[dict]] = {}
    for row in scored:
        if not row.get("move_watch"):
            continue
        day = str(row.get("as_of") or row.get("date") or "")
        by_day.setdefault(day, []).append(row)
    daily: list[dict] = []
    for rows in by_day.values():
        rows = sorted(rows, key=lambda item: float(item.get("move_score") or 0.0), reverse=True)
        daily.extend(rows[:max_per_day])
    daily.sort(key=lambda item: float(item.get("move_score") or 0.0), reverse=True)
    week_count: dict[str, int] = {}
    winners: set[tuple[Any, str]] = set()
    for row in daily:
        stamp = _as_date(str(row.get("as_of") or row.get("date") or ""))
        week = stamp.strftime("%G-W%V") if stamp else "unknown"
        used = week_count.get(week, 0)
        if used >= max_per_week:
            continue
        week_count[week] = used + 1
        winners.add((row.get("symbol"), str(row.get("as_of") or row.get("date") or "")))
    out = []
    for row in scored:
        item = dict(row)
        key = (item.get("symbol"), str(item.get("as_of") or item.get("date") or ""))
        if item.get("move_watch") and key not in winners:
            item["move_watch"] = False
            item["target_watch"] = False
            item["rare_eod"] = False
            item["expected_move_pct"] = 0.0
            extra = list(item.get("reasons") or [])
            extra.append("Capped: max 1 movement name/day and 4/week")
            item["reasons"] = extra
        elif item.get("move_watch"):
            item["target_watch"] = True
            item["rare_eod"] = True
        out.append(item)
    return out


def target_trade_payload(
    confirmations: dict[str, bool],
    *,
    rsi: float | None = None,
    target_pct: float = 0.0,
    range_pct: float | None = None,
    **_ignored: Any,
) -> dict[str, Any]:
    watch = is_move_setup(confirmations)
    score = move_setup_score(confirmations, range_pct=range_pct)
    reasons: list[str] = []
    if watch:
        reasons.append(
            "Movement screener: today's range >= 2.5% and close not ±5% — "
            "next session often a one-way close of 0.5–1%+ either direction"
        )
        reasons.append("Direction is not predicted. Trader chooses side the next morning.")
        reasons.append("Capture 0.5–1% of that day. Caps: 1 name/day, 4/week.")
    return {
        "move_watch": watch,
        "move_score": score,
        "target_watch": watch,
        "rare_eod": watch,
        "rare_eod_score": score,
        "expected_move_pct": CAPTURE_PCT if watch else 0.0,
        "expected_horizon_days": 1,
        "reasons": reasons,
    }


# Back-compat names used by older tests/scripts
def is_eod_target_watch(confirmations: dict[str, bool], *, rsi: float | None = None) -> bool:
    return is_move_setup(confirmations)


def is_rare_eod_setup(confirmations: dict[str, bool], *, rsi: float | None = None) -> bool:
    return is_move_setup(confirmations)


def rare_eod_score(confirmations: dict[str, bool], *, rsi: float | None = None) -> float:
    return move_setup_score(confirmations)


def pick_rare_eod_trades(entries: list[dict], **kwargs: Any) -> list[dict]:
    mapped = []
    for row in entries:
        item = dict(row)
        if "move_watch" not in item:
            item["move_watch"] = bool(item.get("rare_eod") or item.get("target_watch"))
        if "move_score" not in item:
            item["move_score"] = float(item.get("rare_eod_score") or 0.0)
        mapped.append(item)
    return pick_move_setups(mapped, **kwargs)
