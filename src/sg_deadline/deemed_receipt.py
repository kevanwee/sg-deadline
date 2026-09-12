"""Contractual deemed-receipt arithmetic for notices.

The contract's notice clause is expressed as data (DeemedReceiptRule); this module only does
the date math. Extracting the rule from a clause is the job of a reviewer or an LLM
(see the oblig-register project), not this library.
"""

from __future__ import annotations

from datetime import date, datetime, time, timedelta

from pydantic import BaseModel, model_validator

from .calendar import Calendar
from .engine import Result, _fmt


class DeemedReceiptRule(BaseModel):
    method: str  # email | post | courier | hand | fax | portal ...
    offset_days: int = 0
    business_days: bool = False  # count offset in working days rather than calendar days
    # If the notice is sent after this local time on a working day, or on a non-working day,
    # it is treated as sent on the next working day (common "after 5pm" wording).
    cutoff: time | None = None
    non_working_day_defers: bool = False
    roll_to_working_day: bool = False  # roll the final date forward if it is non-working
    clause_ref: str = ""
    verbatim: str = ""  # the clause wording this rule was derived from, for audit

    @model_validator(mode="after")
    def _sane(self) -> DeemedReceiptRule:
        if self.offset_days < 0:
            raise ValueError("offset_days must be >= 0")
        return self


def deemed_receipt(rule: DeemedReceiptRule, sent_at: datetime, cal: Calendar) -> Result:
    trace = [
        f"deemed receipt by {rule.method}"
        + (f" ({rule.clause_ref})" if rule.clause_ref else ""),
        f"sent at: {sent_at.isoformat(sep=' ', timespec='minutes')} "
        f"({sent_at.strftime('%a')})",
    ]
    if rule.verbatim:
        trace.append(f'clause: "{rule.verbatim}"')

    effective: date = sent_at.date()
    reason = cal.why_non_working(effective)
    if rule.non_working_day_defers and reason:
        effective = cal.next_working(effective, inclusive=False)
        trace.append(f"sent on a {reason}: treated as sent on {_fmt(effective)}")
    elif rule.cutoff is not None and sent_at.time() > rule.cutoff:
        effective = cal.next_working(effective, inclusive=False)
        trace.append(f"sent after cutoff {rule.cutoff.strftime('%H:%M')}: treated as sent "
                     f"on next working day {_fmt(effective)}")
    else:
        trace.append(f"effective sending date: {_fmt(effective)}")

    if rule.offset_days == 0:
        deemed = effective
        trace.append("no offset: deemed received on the effective sending date")
    elif rule.business_days:
        deemed = cal.add_working_days(effective, rule.offset_days)
        trace.append(f"+ {rule.offset_days} business day(s) = {_fmt(deemed)}")
    else:
        deemed = effective + timedelta(days=rule.offset_days)
        trace.append(f"+ {rule.offset_days} calendar day(s) = {_fmt(deemed)}")

    reason = cal.why_non_working(deemed)
    if reason and rule.roll_to_working_day:
        rolled = cal.next_working(deemed)
        trace.append(f"{_fmt(deemed)} is a {reason}: rolled to {_fmt(rolled)}")
        deemed = rolled
    elif reason:
        trace.append(f"{_fmt(deemed)} is a {reason}; clause does not roll, date unchanged")

    trace.append(f"DEEMED RECEIVED: {_fmt(deemed)}")
    trace.extend(cal.coverage_notes(sent_at.date(), deemed))
    return Result(rule_id=f"deemed_receipt.{rule.method}", trigger=sent_at.date(),
                  deadline=deemed, trace=trace)
