from datetime import date

import pytest

from sg_deadline import HolidayDataMissingError


def test_weekend_and_holiday_detection(cal):
    assert cal.is_working(date(2026, 1, 2))  # Fri
    assert not cal.is_working(date(2026, 1, 3))  # Sat
    assert not cal.is_working(date(2026, 1, 1))  # New Year's Day
    assert cal.why_non_working(date(2026, 1, 1)) == "public holiday (New Year's Day)"
    assert cal.why_non_working(date(2026, 1, 4)) == "Sunday"
    assert cal.why_non_working(date(2026, 1, 5)) is None


def test_observed_holiday_is_non_working(cal):
    # National Day 2026 falls on a Sunday; Monday 10 Aug is the observed holiday.
    assert not cal.is_working(date(2026, 8, 10))


def test_add_working_days_skips_christmas_and_weekend(cal):
    # Thu 24 Dec -> skip Fri 25 (PH), Sat, Sun -> Mon 28 (1), Tue 29 (2), Wed 30 (3)
    assert cal.add_working_days(date(2026, 12, 24), 3) == date(2026, 12, 30)


def test_add_working_days_backwards(cal):
    assert cal.add_working_days(date(2026, 12, 28), -1) == date(2026, 12, 24)


def test_working_days_between(cal):
    # after 23 Dec up to and incl. 31 Dec: 24, 28, 29, 30, 31
    assert cal.working_days_between(date(2026, 12, 23), date(2026, 12, 31)) == 5
    assert cal.working_days_between(date(2026, 12, 31), date(2026, 12, 23)) == -5
    assert cal.working_days_between(date(2026, 3, 2), date(2026, 3, 2)) == 0


def test_missing_year_raises_rather_than_guessing(cal):
    with pytest.raises(HolidayDataMissingError):
        cal.is_working(date(2031, 6, 1))
