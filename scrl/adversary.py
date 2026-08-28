"""Structured adversary. Kills are mechanical, not rhetorical."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date

import pandas as pd


@dataclass
class AdversaryReport:
    kills: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    @property
    def killed(self) -> bool:
        return len(self.kills) > 0


def critique(
    as_of: date | pd.Timestamp,
    horizon_days: int,
    last_earnings: date | pd.Timestamp | None,
    analog_n: int,
    analog_straddles: bool,
    days_to_expiry: int,
    residual_20: float | None,
    dist_52w_high: float | None,
    extra_kills: list[str] | None = None,
) -> AdversaryReport:
    report = AdversaryReport()
    as_of_d = pd.Timestamp(as_of).date()

    if last_earnings is not None:
        age = (as_of_d - pd.Timestamp(last_earnings).date()).days
        if age > horizon_days:
            report.kills.append(
                f"horizon mismatch: last earnings {age}d ago vs {horizon_days}d trade window"
            )
        elif age <= 2:
            report.warnings.append("earnings just printed; gap/IV path risk")

    if analog_n < 15:
        report.kills.append(f"analog n={analog_n} < 15")
    if analog_straddles:
        report.warnings.append("analog distribution straddles zero — no directional prior")
    if days_to_expiry <= 1:
        report.kills.append("expiry microstructure is not a 1–4 week investment process")
    if dist_52w_high is not None and dist_52w_high < -0.12:
        report.warnings.append(
            "distance-from-52w-high is not a catalyst; it is a description of the past"
        )
    if residual_20 is not None and abs(residual_20) < 0.02:
        report.warnings.append("20d factor residual is small; no unused idiosyncratic move")
    if extra_kills:
        report.kills.extend(extra_kills)
    return report
