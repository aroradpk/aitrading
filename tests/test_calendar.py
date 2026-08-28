from datetime import date

from scrl.calendar_nse import days_to_monthly_expiry, last_tuesday, next_monthly_expiry


def test_last_tuesday_known():
    assert last_tuesday(2026, 8) == date(2026, 8, 25)


def test_days_to_expiry_on_expiry():
    assert days_to_monthly_expiry(date(2026, 8, 25)) == 0


def test_next_expiry_rolls_month():
    assert next_monthly_expiry(date(2026, 8, 26)) == date(2026, 9, 29)
