"""NSE monthly expiry approximation (last Tuesday of the month)."""

from __future__ import annotations

import calendar
from datetime import date, timedelta


def last_tuesday(year: int, month: int) -> date:
    last_day = calendar.monthrange(year, month)[1]
    d = date(year, month, last_day)
    # Tuesday = 1
    offset = (d.weekday() - 1) % 7
    return d - timedelta(days=offset)


def next_monthly_expiry(as_of: date) -> date:
    candidate = last_tuesday(as_of.year, as_of.month)
    if candidate < as_of:
        if as_of.month == 12:
            return last_tuesday(as_of.year + 1, 1)
        return last_tuesday(as_of.year, as_of.month + 1)
    return candidate


def days_to_monthly_expiry(as_of: date) -> int:
    return (next_monthly_expiry(as_of) - as_of).days
