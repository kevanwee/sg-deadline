from datetime import date

from sg_deadline import limitation_period


def test_contract_six_years_anniversary(cal, limitation_rules):
    r = limitation_period(limitation_rules["sg.limitation.contract"], date(2020, 3, 15), cal)
    assert r.deadline == date(2026, 3, 15)  # Sunday, deliberately not rolled
    assert any("NOT extended" in line for line in r.trace)


def test_leap_day_accrual(cal, limitation_rules):
    r = limitation_period(limitation_rules["sg.limitation.tort"], date(2020, 2, 29), cal)
    assert r.deadline == date(2026, 2, 28)


def test_longstop_controls_when_earlier(cal, limitation_rules):
    rule = limitation_rules["sg.limitation.latent-damage-knowledge"]
    # act in 2010, knowledge in 2024 -> 3y from knowledge = 2027 but longstop 2025 controls
    r = limitation_period(rule, date(2024, 6, 1), None, longstop_start=date(2010, 6, 1))
    assert r.deadline == date(2025, 6, 1)
    assert any("longstop is earlier" in line for line in r.trace)


def test_longstop_does_not_control_when_later(cal, limitation_rules):
    rule = limitation_rules["sg.limitation.latent-damage-knowledge"]
    r = limitation_period(rule, date(2022, 6, 1), None, longstop_start=date(2020, 6, 1))
    assert r.deadline == date(2025, 6, 1)


def test_future_limitation_does_not_require_a_working_day_calendar(cal, limitation_rules):
    result = limitation_period(limitation_rules["sg.limitation.contract"], date(2026, 10, 24), cal)
    # Six calendar years after 24 Oct 2026; no holiday adjustment.
    assert result.deadline == date(2032, 10, 24)
    assert any("2032" in line and "was not checked" in line for line in result.trace)
    assert any("NOT rolled" in warning for warning in result.warnings)
    assert not any("holiday data SG 2032:" in line for line in result.trace)


def test_future_leap_day_limitation_stays_on_the_anniversary(cal, limitation_rules):
    result = limitation_period(limitation_rules["sg.limitation.contract"], date(2028, 2, 29), cal)
    # Six years after leap day 2028 clamps to the final February day in 2034.
    assert result.deadline == date(2034, 2, 28)


def test_missing_holiday_data_still_blocks_working_day_computation(cal):
    import pytest

    from sg_deadline.calendar import HolidayDataMissingError
    with pytest.raises(HolidayDataMissingError):
        cal.next_working(date(2032, 10, 24))
