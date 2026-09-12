"""Limitation Act 1959 periods.

Limitation is deliberately separated from the procedural engine: limitation periods are
expressed in years, run from accrual (or knowledge), do not use the ROC short-period rule,
and are NOT rolled to the next working day by default. eLitigation accepts filings 24/7,
so the historic "registry closed" extension is not relied on here.
"""

from __future__ import annotations

from datetime import date
from pathlib import Path

import yaml
from dateutil.relativedelta import relativedelta
from pydantic import BaseModel, Field

from .calendar import Calendar
from .engine import Result, _fmt
from .paths import RULES_DIR


class LimitationRule(BaseModel):
    id: str
    source: str
    description: str
    years: int
    runs_from: str = "accrual"  # accrual | knowledge | judgment
    longstop_years: int | None = None
    verified: bool = False
    notes: list[str] = Field(default_factory=list)


class LimitationSet(BaseModel):
    jurisdiction: str
    instrument: str
    limitation: list[LimitationRule]


def load_limitation_rules(rules_dir: Path | None = None) -> dict[str, LimitationRule]:
    directory = rules_dir or RULES_DIR
    out: dict[str, LimitationRule] = {}
    for path in sorted(directory.rglob("*.yaml")):
        raw = yaml.safe_load(path.read_text(encoding="utf-8"))
        if "limitation" not in raw:
            continue
        ls = LimitationSet.model_validate(raw)
        for r in ls.limitation:
            if r.id in out:
                raise ValueError(f"duplicate limitation id {r.id!r} in {path}")
            out[r.id] = r
    return out


def limitation_period(
    rule: LimitationRule,
    start: date,
    cal: Calendar | None = None,
    *,
    longstop_start: date | None = None,
) -> Result:
    """Last day on which proceedings may be commenced.

    Convention: the day of accrual is excluded and the period expires at the end of the
    corresponding anniversary date. A claim filed ON the anniversary is treated as in time.
    """
    expiry = start + relativedelta(years=rule.years)
    trace = [
        f"limitation {rule.id}: {rule.description}",
        f"source: {rule.source}",
        f"period runs from {rule.runs_from}: {_fmt(start)}",
        f"{rule.years} years from {_fmt(start)} = {_fmt(expiry)} (anniversary convention; "
        "day of accrual excluded, last day inclusive)",
    ]
    warnings: list[str] = []
    if not rule.verified:
        warnings.append(f"limitation rule {rule.id} is UNVERIFIED; confirm against the Act.")

    deadline = expiry
    if rule.longstop_years is not None:
        ls_start = longstop_start or start
        longstop = ls_start + relativedelta(years=rule.longstop_years)
        trace.append(f"longstop: {rule.longstop_years} years from {_fmt(ls_start)} = "
                     f"{_fmt(longstop)}")
        if longstop < deadline:
            deadline = longstop
            trace.append("longstop is earlier and therefore controls")

    if cal is not None:
        reason = cal.why_non_working(deadline)
        if reason:
            trace.append(f"{_fmt(deadline)} is a {reason}. Limitation is NOT extended; "
                         "file before this date. (eLitigation accepts electronic filing on "
                         "non-working days.)")
        trace.extend(cal.coverage_notes(deadline))

    trace.append(f"LAST DAY TO COMMENCE: {_fmt(deadline)}")
    for n in rule.notes:
        trace.append(f"note: {n}")
    return Result(rule_id=rule.id, trigger=start, deadline=deadline, trace=trace,
                  warnings=warnings)
