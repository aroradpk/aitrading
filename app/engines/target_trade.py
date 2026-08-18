"""Find next-session target-rise trades from EOD structure.

Empirical on the 5-scrip book, daily parquet 2021-09-17 → 2026-08-17
(in-sample through 2025-08-14, last year held out):

- Coil / EMA20 / S/R / Fib at yesterday's close do **not** beat chance for
  next session high vs today's close >= the book target (lift < 1).
- Target-up days cluster after a **washed-out** tape (no uptrend) with either
  a rumble bar (range >= 2.5%, close not ±5%) or RSI < 40.
- That EOD watch is ~2× base rate, still ~75–80% false — not a 7.
- If the next open gaps >= 0.4× the book target, finishing the full target
  is common (~55–70% on the holdout year). A gap already >= target is late.

Hit = next session high vs setup close >= that name's target_range_pct.
"""

from __future__ import annotations

from typing import Any

RSI_WASHOUT = 40.0
OPEN_DRIVE_FRAC = 0.4


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
    """Use at the next open. gap_pct is (open / prior close - 1) * 100."""
    target_pct = float(target_pct or 0.0)
    gap_pct = float(gap_pct or 0.0)
    if target_pct <= 0:
        return {
            "open_drive": False,
            "already_printed": False,
            "gap_pct": round(gap_pct, 3),
            "open_drive_frac": OPEN_DRIVE_FRAC,
        }
    already = gap_pct >= target_pct
    drive = (not already) and gap_pct >= OPEN_DRIVE_FRAC * target_pct
    return {
        "open_drive": drive,
        "already_printed": already,
        "gap_pct": round(gap_pct, 3),
        "open_drive_frac": OPEN_DRIVE_FRAC,
    }


def target_trade_payload(
    confirmations: dict[str, bool],
    *,
    rsi: float | None,
    target_pct: float,
    gap_pct: float | None = None,
) -> dict[str, Any]:
    watch = is_eod_target_watch(confirmations, rsi=rsi)
    gap_info = classify_open_gap(gap_pct or 0.0, target_pct) if gap_pct is not None else {
        "open_drive": False,
        "already_printed": False,
        "gap_pct": None,
        "open_drive_frac": OPEN_DRIVE_FRAC,
    }
    reasons: list[str] = []
    if watch:
        if confirmations.get("setup_rattle"):
            reasons.append("Washed-out rumble (range >= 2.5%, close not ±5%)")
        if rsi is not None and rsi < RSI_WASHOUT:
            reasons.append(f"RSI {rsi:.1f} < {RSI_WASHOUT:.0f} without an uptrend")
        reasons.append("Not an uptrend — coil/EMA/S/R at close do not forecast these targets")
    if gap_info.get("already_printed"):
        reasons.append("Open already printed the book target — late, do not chase")
    elif gap_info.get("open_drive"):
        reasons.append(
            f"Open gap {gap_info['gap_pct']}% >= {OPEN_DRIVE_FRAC:.0%} of the {target_pct}% target"
        )
    return {
        "target_watch": watch,
        "expected_move_pct": float(target_pct or 0.0) if watch else 0.0,
        "expected_horizon_days": 1,
        **gap_info,
        "reasons": reasons,
    }
