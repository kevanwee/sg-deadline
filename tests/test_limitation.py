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
