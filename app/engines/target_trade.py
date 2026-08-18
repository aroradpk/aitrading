"""1-day-ahead rare setups for the next session's book-target rise.

Goal the data cannot meet: ~90% hit / 10% false at 3–4 trades a week, decided
at yesterday's close. On this 5-scrip book (2021-09-17 → 2026-08-17):

- Coil / EMA / S/R / Fib at the close is worse than chance.
- About half of target-up days already gap 0.4× the target overnight — that
  information does not exist at yesterday's close.
- Tightest EOD pocket that still repeats: no uptrend, RSI < 30, and a rumble
  or strong close. Holdout ~33% hit / ~67% false at ~0.2 trades/week after
  1-trade/day and 4-trades/week caps. That is the high-conviction EOD rule.
- Using the next open (gap 75–99% of target) can look like 75–80% hit, but
  that is same-session, not 1-day-ahead. It is not the trade trigger.

Hit = next session high vs setup close >= that name's target_range_pct.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

RSI_WASHOUT = 40.0
RSI_RARE = 30.0
MAX_TRADES_PER_DAY = 1
MAX_TRADES_PER_WEEK = 4


def _as_date(value: str | None) -> datetime | None:
    if not value:
        return None
    return datetime.fromisoformat(str(value)[:10])


def is_eod_target_watch(confirmations: dict[str, bool], *, rsi: float | None) -> bool:
    """Wide research watch (~2× chance, ~78% false). Not the rare trade."""
    if confirmations.get("late_bar") or confirmations.get("uptrend"):
        return False
    if confirmations.get("setup_rattle"):
        return True
    return rsi is not None and rsi < RSI_WASHOUT


def rare_eod_score(confirmations: dict[str, bool], *, rsi: float | None) -> float:
    """0 = not a rare EOD setup. Higher = more extreme washout + energy."""
    if confirmations.get("late_bar") or confirmations.get("uptrend"):
        return 0.0
    if rsi is None or rsi >= RSI_RARE:
        return 0.0
    energy = bool(confirmations.get("setup_rattle") or confirmations.get("strong_close"))
    if not energy:
        return 0.0
    score = (RSI_RARE - float(rsi)) / 3.0
    if confirmations.get("setup_rattle"):
        score += 2.0
    if confirmations.get("strong_close"):
        score += 1.0
    return round(score, 3)


def is_rare_eod_setup(confirmations: dict[str, bool], *, rsi: float | None) -> bool:
    """1-day-ahead trade: washed out, RSI < 30, rumble or strong close."""
    return rare_eod_score(confirmations, rsi=rsi) > 0


def pick_rare_eod_trades(
    entries: list[dict],
    *,
    max_per_day: int = MAX_TRADES_PER_DAY,
    max_per_week: int = MAX_TRADES_PER_WEEK,
) -> list[dict]:
    """Keep the highest-score rare EOD names: 1 per day, 4 per ISO week."""
    scored = []
    for row in entries:
        item = dict(row)
        score = float(item.get("rare_eod_score") or 0.0)
        if not item.get("rare_eod"):
            score = 0.0
        item["rare_eod_score"] = score
        scored.append(item)

    winners: set[tuple[Any, str]] = set()
    by_day: dict[str, list[dict]] = {}
    for row in scored:
        if not row.get("rare_eod"):
            continue
        day = str(row.get("as_of") or row.get("date") or "")
        by_day.setdefault(day, []).append(row)
    daily_picks: list[dict] = []
    for day, rows in by_day.items():
        rows = sorted(rows, key=lambda item: float(item.get("rare_eod_score") or 0.0), reverse=True)
        daily_picks.extend(rows[:max_per_day])

    daily_picks.sort(key=lambda item: float(item.get("rare_eod_score") or 0.0), reverse=True)
    week_count: dict[str, int] = {}
    for row in daily_picks:
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
        if item.get("rare_eod") and key not in winners:
            item["rare_eod"] = False
            extra = list(item.get("reasons") or [])
            extra.append("Capped: max 1 rare EOD trade/day and 4/week — higher-score name kept")
            item["reasons"] = extra
        out.append(item)
    return out


def target_trade_payload(
    confirmations: dict[str, bool],
    *,
    rsi: float | None,
    target_pct: float,
    gap_pct: float | None = None,
) -> dict[str, Any]:
    watch = is_eod_target_watch(confirmations, rsi=rsi)
    rare = is_rare_eod_setup(confirmations, rsi=rsi)
    score = rare_eod_score(confirmations, rsi=rsi)
    reasons: list[str] = []
    if rare:
        reasons.append(
            f"Rare 1-day-ahead setup: no uptrend, RSI {rsi:.1f} < {RSI_RARE:.0f}, "
            "rumble or strong close"
        )
        reasons.append("Caps: 1 name/day, 4/week. Not 90% hit — that bar is not in EOD data.")
    elif watch:
        reasons.append("Wide washout watch only — too many false signals to trade")
    expected = float(target_pct or 0.0) if rare else 0.0
    return {
        "target_watch": watch,
        "rare_eod": rare,
        "rare_eod_score": score,
        "expected_move_pct": expected,
        "expected_horizon_days": 1,
        "reasons": reasons,
        "gap_pct": round(float(gap_pct), 3) if gap_pct is not None else None,
    }
