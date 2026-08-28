"""Permission engine: the highest-conviction output is often DENY."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime

import pandas as pd

from scrl.adversary import AdversaryReport
from scrl.calendar_nse import days_to_monthly_expiry
from scrl.regime import RegimeSnapshot
from scrl.retrieval import AnalogSet
from scrl.specialists import SpecialistBoard


@dataclass
class Permission:
    decision: str  # DENY | ALLOW_SMALL | ALLOW
    cash_weight: float
    reasons: list[str] = field(default_factory=list)


def decide(
    regime: RegimeSnapshot,
    analogs: AnalogSet,
    board: SpecialistBoard,
    adversary: AdversaryReport,
    as_of: date | datetime | pd.Timestamp,
    horizon_days: int = 20,
    expiry_buffer_days: int = 1,
) -> Permission:
    reasons: list[str] = []
    as_of_d = pd.Timestamp(as_of).date()
    dte = days_to_monthly_expiry(as_of_d)

    if regime.high_entropy:
        reasons.append(f"high regime entropy {regime.entropy:.2f}")
    if analogs.n < 15:
        reasons.append(f"analog sample too small n={analogs.n}")
    if analogs.straddles_zero:
        reasons.append("analog 10d forward returns straddle zero")
    if board.disagreement:
        reasons.append("trend and fade specialists both fired")
    if dte <= expiry_buffer_days:
        reasons.append(f"monthly expiry in {dte} day(s)")
    if adversary.killed:
        reasons.append("adversary kill: " + "; ".join(adversary.kills))

    active = []
    if board.trend.fire and board.trend.healthy:
        active.append("trend")
    if board.fade.fire and board.fade.healthy:
        active.append("fade")

    if reasons:
        return Permission(decision="DENY", cash_weight=1.0, reasons=reasons)

    if not active:
        reasons.append("no healthy specialist firing")
        return Permission(decision="DENY", cash_weight=1.0, reasons=reasons)

    if analogs.same_sign and not regime.high_entropy:
        return Permission(
            decision="ALLOW_SMALL",
            cash_weight=0.7,
            reasons=[f"analogs same-sign median={analogs.median_10:.3f}; specialists={active}"],
        )
    return Permission(decision="DENY", cash_weight=1.0, reasons=["insufficient agreement"])
