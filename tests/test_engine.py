"""Golden cases. Each expected value was computed by hand from the rule semantics; if a test
here fails after a change to the engine, the engine is wrong, not the test (unless the rule
semantics themselves were deliberately changed and the change is documented)."""

from datetime import date

import pytest

from sg_deadline import Direction, HolidayDataMissingError, Period, RollDirection, Rule, compute


def mk(period, *, direction=Direction.AFTER, clear_days=False, roll=RollDirection.AUTO,
       short=True, rid="sg.test.rule"):
    return Rule(id=rid, source="test", description="test", period=Period(**period),
                direction=direction, clear_days=clear_days, roll=roll,
                short_period_excludes_non_working=short, verified=True)


# -- long periods (> 7 days): calendar days, roll forward on non-working expiry ----------

def test_21_days_landing_on_working_day(cal):
    r = compute(mk({"days": 21}), date(2026, 3, 2), cal)  # Mon
    assert r.deadline == date(2026, 3, 23)  # Mon


def test_21_days_landing_on_good_friday_rolls_to_monday(cal):
    r = compute(mk({"days": 21}), date(2026, 3, 13), cal)  # Fri -> 3 Apr Good Friday
    assert r.deadline == date(2026, 4, 6)
    assert any("rolled forward" in line for line in r.trace)


def test_14_days_landing_on_saturday_rolls_to_monday(cal):
    r = compute(mk({"days": 14}), date(2026, 3, 14), cal)  # Sat + 14 = Sat 28 Mar
    assert r.deadline == date(2026, 3, 30)


def test_roll_none_keeps_non_working_date(cal):
    r = compute(mk({"days": 14}, roll=RollDirection.NONE), date(2026, 3, 14), cal)
    assert r.deadline == date(2026, 3, 28)


# -- short periods (<= 7 days): exclude Sat/Sun/PH from the count ------------------------

def test_7_days_excludes_weekend(cal):
    # Fri 13 Mar: Mon16(1) Tue17(2) Wed18(3) Thu19(4) Fri20(5) Mon23(6) Tue24(7)
    r = compute(mk({"days": 7}), date(2026, 3, 13), cal)
    assert r.deadline == date(2026, 3, 24)


def test_5_days_excludes_christmas_and_weekend(cal):
    # Wed 23 Dec: Thu24(1) [Fri25 PH, Sat, Sun] Mon28(2) Tue29(3) Wed30(4) Thu31(5)
    r = compute(mk({"days": 5}), date(2026, 12, 23), cal)
    assert r.deadline == date(2026, 12, 31)


def test_short_period_exclusion_can_be_disabled(cal):
    r = compute(mk({"days": 5}, short=False), date(2026, 12, 23), cal)
    # 23 + 5 = Mon 28 Dec, working day, no roll
    assert r.deadline == date(2026, 12, 28)


def test_8_days_is_not_short(cal):
    # 8 > 7: calendar days. Fri 13 Mar + 8 = Sat 21 Mar (also Hari Raya Puasa) -> Mon 23
    r = compute(mk({"days": 8}), date(2026, 3, 13), cal)
    assert r.deadline == date(2026, 3, 23)


# -- "before" direction and clear days ---------------------------------------------------

def test_two_clear_days_before_tuesday_hearing(cal):
    # Hearing Tue 10 Mar. 2 clear days, short period so Sat/Sun excluded:
    # step back Mon 9 (1), [Sun, Sat skipped], Fri 6 (2), Thu 5 (3) -> act by Thu 5 Mar
    r = compute(mk({"days": 2}, direction=Direction.BEFORE, clear_days=True),
                date(2026, 3, 10), cal)
    assert r.deadline == date(2026, 3, 5)


def test_14_days_before_rolls_backward(cal):
    # 14 days before Mon 16 Mar = Mon 2 Mar (working). Use a date that lands on Sunday:
    # 14 days before Sun 29 Mar = Sun 15 Mar -> roll BACK to Fri 13 Mar
    r = compute(mk({"days": 14}, direction=Direction.BEFORE), date(2026, 3, 29), cal)
    assert r.deadline == date(2026, 3, 13)
    assert any("rolled BACK" in line for line in r.trace)


# -- month arithmetic --------------------------------------------------------------------

def test_three_months_corresponding_date(cal):
    r = compute(mk({"months": 3}), date(2026, 3, 5), cal)
    assert r.deadline == date(2026, 6, 5)


def test_three_months_from_month_end_clamps(cal):
    r = compute(mk({"months": 3}), date(2026, 1, 31), cal)
    assert r.deadline == date(2026, 4, 30)
    assert any("corresponding date does not exist" in line for line in r.trace)


def test_month_period_spanning_uncovered_year_raises(cal):
    with pytest.raises(HolidayDataMissingError):
        compute(mk({"months": 3}), date(2026, 11, 30), cal)


# -- trace and warnings ------------------------------------------------------------------

def test_trace_has_deadline_and_coverage_lines(cal):
    r = compute(mk({"days": 21}), date(2026, 3, 2), cal)
    assert r.trace[-1].startswith("holiday data SG 2026")
    assert any(line.startswith("DEADLINE:") for line in r.trace)


def test_unverified_rule_emits_warning(cal, rules):
    r = compute(rules["sg.roc2021.defence"], date(2026, 3, 2), cal)
    assert r.warnings and "UNVERIFIED" in r.warnings[0]


def test_all_bundled_rules_load_and_compute(cal, rules):
    assert len(rules) >= 8
    for rule in rules.values():
        compute(rule, date(2026, 6, 15), cal)
