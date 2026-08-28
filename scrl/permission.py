"""Permission engine: the highest-conviction output is often DENY."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime

import pandas as pd

from scrl.adversary import AdversaryReport
from scrl.calendar_nse import days_to_monthly_expiry
from scrl.mandates import Mandate, SWING
from scrl.regime import RegimeSnapshot
from scrl.retrieval import AnalogSet
from scrl.specialists import SpecialistBoard


@dataclass
class Permission:
    decision: str
    cash_weight: float
    today: str
    reasons: list[str] = field(default_factory=list)


def decide(
    regime: RegimeSnapshot,
    analogs: AnalogSet,
    board: SpecialistBoard,
    adversary: AdversaryReport,
    as_of: date | datetime | pd.Timestamp,
    horizon_days: int = 20,
    expiry_buffer_days: int = 1,
    mandate: Mandate | None = None,
) -> Permission:
    m = mandate or SWING
    reasons: list[str] = []
    as_of_d = pd.Timestamp(as_of).date()
    dte = days_to_monthly_expiry(as_of_d)

    if m.name in {"swing", "position"}:
        return _decide_trading(m, regime, analogs, board, adversary, dte, reasons)
    return _decide_longterm(m, regime, analogs, adversary, reasons)


def _decide_trading(
    m: Mandate,
    regime: RegimeSnapshot,
    analogs: AnalogSet,
    board: SpecialistBoard,
    adversary: AdversaryReport,
    dte: int,
    reasons: list[str],
) -> Permission:
    if m.regime_blocks_entry and regime.high_entropy:
        reasons.append(f"high regime entropy {regime.entropy:.2f}")
    if analogs.n < 15:
        reasons.append(f"analog sample too small n={analogs.n}")
    if m.analog_straddle_blocks_entry and analogs.straddles_zero:
        reasons.append(f"analog {analogs.horizon_days}d forward returns straddle zero")
    if board.disagreement:
        reasons.append("trend and fade specialists both fired")
    if m.kill_near_expiry and dte <= m.expiry_buffer_days:
        reasons.append(f"monthly expiry in {dte} day(s)")
    if adversary.killed:
        reasons.append("adversary kill: " + "; ".join(adversary.kills))

    active = []
    if board.trend.fire and board.trend.healthy:
        active.append("trend")
    if board.fade.fire and board.fade.healthy:
        active.append("fade")

    deny_today = (
        f"Do not open a new {m.label} trade. Cash stays 100%. "
        f"If you already hold from an older thesis, that is a different ticket — do not average in."
    )
    if reasons:
        return Permission(decision="DENY", cash_weight=1.0, today=deny_today, reasons=reasons)

    if m.require_healthy_specialist and not active:
        reasons.append("no healthy specialist firing")
        return Permission(decision="DENY", cash_weight=1.0, today=deny_today, reasons=reasons)

    if analogs.same_sign and not (m.regime_blocks_entry and regime.high_entropy):
        return Permission(
            decision="ALLOW_SMALL",
            cash_weight=0.7,
            today=(
                f"Paper a small {m.label} expression only (defined risk). "
                f"Size so W2 counterfactual is survivable. Log it in the journal. No live size-up yet."
            ),
            reasons=[f"analogs same-sign median={analogs.median_10:.3f}; specialists={active or ['none required']}"],
        )
    return Permission(
        decision="DENY",
        cash_weight=1.0,
        today=deny_today,
        reasons=["insufficient agreement"],
    )


def _decide_longterm(
    m: Mandate,
    regime: RegimeSnapshot,
    analogs: AnalogSet,
    adversary: AdversaryReport,
    reasons: list[str],
) -> Permission:
    """Core-holding review. 10-day chop is not a sell. Missing analog edge is not a buy."""
    if analogs.n < 15:
        reasons.append(f"analog sample too small n={analogs.n}")
        return Permission(
            decision="WAIT",
            cash_weight=1.0,
            today="Not enough comparable 60-day episodes. Do not start a new core lot today.",
            reasons=reasons,
        )
    if adversary.killed:
        reasons.append("adversary kill: " + "; ".join(adversary.kills))
        return Permission(
            decision="WAIT",
            cash_weight=1.0,
            today="Blocked on data quality. Fix the analog/history issue before adding capital.",
            reasons=reasons,
        )

    if regime.state == "risk_off" and regime.probabilities.get("risk_off", 0) >= 0.5:
        reasons.append("regime mass on risk_off — delay new long-term adds")
        return Permission(
            decision="TRIM" if analogs.median_10 < 0 else "HOLD",
            cash_weight=0.4 if analogs.median_10 < 0 else 0.2,
            today=(
                "Do not add. If this name is already a core holding, hold unless your written "
                "invalidation (business, not a 10-day chart) is hit. New capital waits."
            ),
            reasons=reasons,
        )

    if analogs.same_sign and analogs.median_10 > 0:
        reasons.append(f"60d analog median {analogs.median_10:.3f} same-sign positive")
        return Permission(
            decision="ADD_SMALL",
            cash_weight=0.0,
            today=(
                "Eligible to scale a core holding by a small scheduled lot, not a swing entry. "
                "Next review = next earnings. Do not use 52w-high distance as the reason."
            ),
            reasons=reasons,
        )

    reasons.append("no 60d analog edge; quality holding is a HOLD not a BUY")
    return Permission(
        decision="HOLD",
        cash_weight=0.0,
        today=(
            "If you already own it as a multi-year compounder, keep the position and ignore "
            "1–4 week noise. If you do not own it, WAIT — there is no statistical license to start today."
        ),
        reasons=reasons,
    )
