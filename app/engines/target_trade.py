"""Find next-session target-rise trades from EOD structure, then a rare open take.

80% hit / 10% false at 3–4 trades a week is not available on this 5-scrip book.
EOD coil/EMA/S/R is worse than chance. EOD washout watch is ~2× chance and ~78% false.

The only rule that approaches ~80% hit is taking **after the open**, when the gap
is already most of the book target but not complete, one name per session:

- Take: 0.75 <= (open / prior close - 1) / target < 1.0
- One trade per day = the name with the largest gap fraction
- Holdout 2025-08-18→2026-08-14: 14 takes, 78.6% hit, 21.4% false, ~0.3/week
- In-sample: 69 takes, 75.4% hit, 24.6% false, ~0.3/week

A gap already >= target is late. 3–4 trades/week needs gap ~0.25–0.35 and
falls to ~35–45% hit — do not use that as high conviction.
"""

from __future__ import annotations

from typing import Any

RSI_WASHOUT = 40.0
OPEN_DRIVE_FRAC = 0.4
TAKE_GAP_FRAC = 0.75


def gap_fraction(gap_pct: float, target_pct: float) -> float | None:
    target_pct = float(target_pct or 0.0)
    if target_pct <= 0:
        return None
    return float(gap_pct or 0.0) / target_pct


def is_eod_target_watch(confirmations: dict[str, bool], *, rsi: float | None) -> bool:
    """Close-of-day watch: next session may print the book % from this close."""
    if confirmations.get("late_bar"):
        return False
    if confirmations.get("uptrend"):
        return False
    if confirmations.get("setup_rattle"):
        return True
    return rsi is not None and rsi < RSI_WASHOUT


def classify_open_gap(gap_pct: float, target_pct: float) -> dict[str, Any]:
    """Use at the session open. gap_pct is (open / prior close - 1) * 100."""
    target_pct = float(target_pct or 0.0)
    gap_pct = float(gap_pct or 0.0)
    frac = gap_fraction(gap_pct, target_pct)
    already = bool(frac is not None and frac >= 1.0)
    drive = bool(frac is not None and (not already) and frac >= OPEN_DRIVE_FRAC)
    take = bool(frac is not None and (not already) and frac >= TAKE_GAP_FRAC)
    remaining = round(target_pct - gap_pct, 3) if target_pct and not already else 0.0
    conviction = 0.0
    if take and frac is not None:
        conviction = round(min(10.0, 7.0 + 12.0 * (frac - TAKE_GAP_FRAC)), 1)
    return {
        "open_drive": drive,
        "rare_take": take,
        "already_printed": already,
        "gap_pct": round(gap_pct, 3),
        "gap_frac": round(frac, 3) if frac is not None else None,
        "remaining_pct": remaining,
        "take_conviction": conviction,
        "open_drive_frac": OPEN_DRIVE_FRAC,
        "take_gap_frac": TAKE_GAP_FRAC,
    }


def session_gap_pct(frame) -> float | None:
    if frame is None or len(frame) < 2:
        return None
    prev = float(frame["close"].iloc[-2])
    if prev <= 0:
        return None
    return (float(frame["open"].iloc[-1]) / prev - 1.0) * 100


def pick_daily_takes(entries: list[dict]) -> list[dict]:
    """Keep at most one rare_take per as_of date (largest gap fraction)."""
    winners: dict[str, dict] = {}
    for row in entries:
        if not row.get("rare_take"):
            continue
        day = str(row.get("as_of") or row.get("date") or "")
        prev = winners.get(day)
        if prev is None or float(row.get("gap_frac") or 0) > float(prev.get("gap_frac") or 0):
            winners[day] = row
    winner_keys = {(w.get("symbol"), str(w.get("as_of") or w.get("date") or "")) for w in winners.values()}
    out = []
    for row in entries:
        item = dict(row)
        key = (item.get("symbol"), str(item.get("as_of") or item.get("date") or ""))
        if item.get("rare_take") and key not in winner_keys:
            item["rare_take"] = False
            item["take_conviction"] = 0.0
            extra = list(item.get("reasons") or [])
            extra.append("Larger open gap on another name this session — max 1 take/day")
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
    gap_info = (
        classify_open_gap(gap_pct, target_pct)
        if gap_pct is not None
        else {
            "open_drive": False,
            "rare_take": False,
            "already_printed": False,
            "gap_pct": None,
            "gap_frac": None,
            "remaining_pct": 0.0,
            "take_conviction": 0.0,
            "open_drive_frac": OPEN_DRIVE_FRAC,
            "take_gap_frac": TAKE_GAP_FRAC,
        }
    )
    reasons: list[str] = []
    if gap_info.get("already_printed"):
        reasons.append("Open already printed the book target — late, do not chase")
    elif gap_info.get("rare_take"):
        reasons.append(
            f"Rare take: open gap {gap_info['gap_pct']}% is {gap_info['gap_frac']:.0%} of the "
            f"{target_pct}% target; leftover {gap_info['remaining_pct']}%"
        )
        reasons.append("Max one take per session — highest gap fraction wins")
    if watch and not gap_info.get("rare_take"):
        if confirmations.get("setup_rattle"):
            reasons.append("Washed-out rumble (range >= 2.5%, close not ±5%)")
        if rsi is not None and rsi < RSI_WASHOUT:
            reasons.append(f"RSI {rsi:.1f} < {RSI_WASHOUT:.0f} without an uptrend")
        reasons.append("EOD watch only — not high-conviction until the next open gaps 75% of target")
    expected = 0.0
    if gap_info.get("rare_take"):
        expected = float(gap_info.get("remaining_pct") or 0.0)
    elif watch:
        expected = float(target_pct or 0.0)
    return {
        "target_watch": watch,
        "expected_move_pct": expected,
        "expected_horizon_days": 1,
        **gap_info,
        "reasons": reasons,
    }
