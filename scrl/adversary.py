"""Structured adversary. Kills are mechanical, not rhetorical."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date

import pandas as pd

from scrl.mandates import Mandate, SWING


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
    mandate: Mandate | None = None,
) -> AdversaryReport:
    report = AdversaryReport()
    as_of_d = pd.Timestamp(as_of).date()
    m = mandate or SWING

    if last_earnings is not None:
        age = (as_of_d - pd.Timestamp(last_earnings).date()).days
        if m.kill_stale_earnings and m.earnings_max_age_days is not None and age > m.earnings_max_age_days:
            report.kills.append(
                f"horizon mismatch: last earnings {age}d ago vs {m.label} "
                f"(max age {m.earnings_max_age_days}d)"
            )
        elif age <= 2:
            report.warnings.append("earnings just printed; gap/IV path risk")
        elif not m.kill_stale_earnings:
            report.warnings.append(
                f"last earnings {age}d ago — fine for {m.label}; next print is the review date, not a swing trigger"
            )

    if analog_n < 15:
        report.kills.append(f"analog n={analog_n} < 15")
    if analog_straddles:
        if m.analog_straddle_blocks_entry:
            report.warnings.append("analog distribution straddles zero — no directional prior")
        else:
            report.warnings.append(
                "near-term analog straddles zero; ignored for entry because this mandate is not a 10-day trade"
            )
    if m.kill_near_expiry and days_to_expiry <= m.expiry_buffer_days:
        report.kills.append("expiry microstructure is not a swing investment process")
    if dist_52w_high is not None and dist_52w_high < -0.12:
        report.warnings.append(
            "distance-from-52w-high is not a catalyst; it is a description of the past"
        )
    if residual_20 is not None and abs(residual_20) < 0.02 and m.name == "swing":
        report.warnings.append("20d factor residual is small; no unused idiosyncratic move")
    if extra_kills:
        report.kills.extend(extra_kills)
    return report
