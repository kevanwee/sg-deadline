import pytest

from sg_deadline.calendar import Calendar, HolidayDataMissingError
from sg_deadline.paths import HOLIDAYS_DIR, RULES_DIR


def test_packaged_resources_exist():
    assert list(RULES_DIR.rglob("*.yaml"))
    assert list(HOLIDAYS_DIR.glob("sg-*.json"))


def test_zero_day_operations_do_not_mask_missing_holiday_data():
    from datetime import date

    cal = Calendar("SG")
    with pytest.raises(HolidayDataMissingError):
        cal.add_working_days(date(2040, 1, 1), 0)
    with pytest.raises(HolidayDataMissingError):
        cal.working_days_between(date(2040, 1, 1), date(2040, 1, 1))
