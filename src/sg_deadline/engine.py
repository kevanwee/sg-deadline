"""The computation engine. Pure functions; no I/O; every step recorded in `Result.trace`.

The trace is the product. A lawyer does not trust a date; they trust a derivation they can
check line-by-line against the rule text. Never remove trace lines to tidy output.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, timedelta

from .calendar import Calendar
from .rules import Direction, RollDirection, Rule


@dataclass
class Result:
    rule_id: str
    trigger: date
    deadline: date
    trace: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "rule_id": self.rule_id,
            "trigger": self.trigger.isoformat(),
            "deadline": self.deadline.isoformat(),
            "deadline_weekday": self.deadline.strftime("%A"),
            "trace": list(self.trace),
            "warnings": list(self.warnings),
        }


def _fmt(d: date) -> str:
    return f"{d.isoformat()} ({d.strftime('%a')})"


def _resolve_roll(rule: Rule) -> RollDirection:
    if rule.roll is not RollDirection.AUTO:
        return rule.roll
    return RollDirection.FORWARD if rule.direction is Direction.AFTER else RollDirection.BACKWARD


def compute(rule: Rule, trigger: date, cal: Calendar) -> Result:
    """Apply `rule` to `trigger` under `cal`. Raises HolidayDataMissingError on uncovered years."""
    sign = 1 if rule.direction is Direction.AFTER else -1
    trace: list[str] = [
        f"rule {rule.id}: {rule.description}",
        f"source: {rule.source}",
        f"trigger date: {_fmt(trigger)}",
        f"period: {rule.period}, direction: {rule.direction.value}"
        + (", clear days" if rule.clear_days else ""),
    ]
    warnings: list[str] = []
    if not rule.verified:
        warnings.append(
            f"rule {rule.id} is marked UNVERIFIED; confirm the period and rule reference "
            "against the current text on Singapore Statutes Online."
        )

    if rule.period.is_day_based:
        n = rule.period.total_days
        if rule.clear_days:
            # "at least n days must intervene": step one extra day so that n whole days
            # sit strictly between the trigger and the deadline.
            n += 1
            trace.append(f"clear days: at least {rule.period.total_days} days must intervene, "
                         f"so stepping {n} days")
        short = (
            rule.short_period_excludes_non_working
            and rule.period.total_days <= rule.short_period_threshold_days
        )
        if short:
            trace.append(
                f"period is {rule.period.total_days} days <= {rule.short_period_threshold_days}: "
                "Saturdays, Sundays and public holidays are excluded from the count"
            )
            cur = trigger
            counted = 0
            while counted < n:
                cur += timedelta(days=sign)
                reason = cal.why_non_working(cur)
                if reason:
                    trace.append(f"  skip {_fmt(cur)}: {reason}")
                else:
                    counted += 1
                    trace.append(f"  day {counted}: {_fmt(cur)}")
            raw = cur
        else:
            raw = trigger + timedelta(days=sign * n)
            trace.append(f"calendar-day count: {_fmt(trigger)} {'+' if sign > 0 else '-'} {n} days "
                         f"= {_fmt(raw)}")
    else:
        rd = rule.period.to_relativedelta()
        raw = trigger + rd if sign > 0 else trigger - rd
        trace.append(f"calendar-month/year arithmetic: {_fmt(trigger)} "
                     f"{'+' if sign > 0 else '-'} {rule.period} = {_fmt(raw)}")
        if raw.day != trigger.day:
            trace.append("  note: corresponding date does not exist in target month; "
                         "used the last day of that month")

    deadline = raw
    roll = _resolve_roll(rule)
    reason = cal.why_non_working(raw)
    if reason and roll is not RollDirection.NONE:
        if roll is RollDirection.FORWARD:
            deadline = cal.next_working(raw)
            trace.append(f"{_fmt(raw)} is a {reason}: rolled forward to next working day "
                         f"{_fmt(deadline)}")
        else:
            deadline = cal.prev_working(raw)
            trace.append(f"{_fmt(raw)} is a {reason}: rolled BACK to previous working day "
                         f"{_fmt(deadline)} (conservative; act early)")
    elif reason:
        trace.append(f"{_fmt(raw)} is a {reason}; rule does not roll, deadline unchanged")
    else:
        trace.append(f"{_fmt(raw)} is a working day; no roll needed")

    trace.append(f"DEADLINE: {_fmt(deadline)}")
    trace.extend(cal.coverage_notes(trigger, deadline))
    for note in rule.notes:
        trace.append(f"note: {note}")
    return Result(rule_id=rule.id, trigger=trigger, deadline=deadline, trace=trace,
                  warnings=warnings)
