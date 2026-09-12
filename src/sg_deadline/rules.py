"""Rule model and YAML loader.

A Rule is *data*, not code. Everything a rule needs to compute a deadline is declared in
YAML under rules/<jurisdiction>/. Adding a rule must never require a Python change.
"""

from __future__ import annotations

from enum import StrEnum
from pathlib import Path

import yaml
from dateutil.relativedelta import relativedelta
from pydantic import BaseModel, Field, model_validator

from .paths import RULES_DIR


class Direction(StrEnum):
    AFTER = "after"  # "within X after D": deadline is later than the trigger
    BEFORE = "before"  # "not less than X before D": deadline is earlier than the trigger


class RollDirection(StrEnum):
    AUTO = "auto"  # forward for AFTER, backward for BEFORE (conservative)
    FORWARD = "forward"
    BACKWARD = "backward"
    NONE = "none"


class Period(BaseModel):
    days: int = 0
    weeks: int = 0
    months: int = 0
    years: int = 0

    @model_validator(mode="after")
    def _non_empty(self) -> Period:
        if not any((self.days, self.weeks, self.months, self.years)):
            raise ValueError("period must be non-zero")
        if any(v < 0 for v in (self.days, self.weeks, self.months, self.years)):
            raise ValueError("period components must be non-negative")
        return self

    @property
    def is_day_based(self) -> bool:
        return self.months == 0 and self.years == 0

    @property
    def total_days(self) -> int:
        """Only meaningful when is_day_based."""
        return self.days + 7 * self.weeks

    def to_relativedelta(self) -> relativedelta:
        return relativedelta(
            days=self.days, weeks=self.weeks, months=self.months, years=self.years
        )

    def __str__(self) -> str:
        parts = []
        for name, v in (
            ("year", self.years),
            ("month", self.months),
            ("week", self.weeks),
            ("day", self.days),
        ):
            if v:
                parts.append(f"{v} {name}" + ("" if v == 1 else "s"))
        return ", ".join(parts)


class Rule(BaseModel):
    id: str = Field(pattern=r"^[a-z0-9]+(\.[a-z0-9_-]+)+$")
    source: str
    description: str
    period: Period
    direction: Direction = Direction.AFTER
    clear_days: bool = False
    # ROC 2021 O 3 r 2(5): a period of 7 days or less excludes Sat/Sun/public holidays.
    short_period_excludes_non_working: bool = True
    short_period_threshold_days: int = 7
    # ROC 2021 O 3 r 2(6): if the period expires on a Sat/Sun/public holiday, an act done
    # on the next working day is in time.
    roll: RollDirection = RollDirection.AUTO
    verified: bool = False
    notes: list[str] = Field(default_factory=list)
    tags: list[str] = Field(default_factory=list)

    @property
    def jurisdiction(self) -> str:
        return self.id.split(".", 1)[0].upper()


class RuleSet(BaseModel):
    jurisdiction: str
    instrument: str
    rules: list[Rule]


def load_rules(
    rules_dir: Path | None = None, jurisdiction: str | None = None
) -> dict[str, Rule]:
    """Load every rules/**/*.yaml into a dict keyed by rule id. Duplicate ids are an error."""
    directory = rules_dir or RULES_DIR
    out: dict[str, Rule] = {}
    for path in sorted(directory.rglob("*.yaml")):
        raw = yaml.safe_load(path.read_text(encoding="utf-8"))
        if "rules" not in raw:
            continue  # e.g. a limitation-only file; see limitation.py
        rs = RuleSet.model_validate(raw)
        if jurisdiction and rs.jurisdiction.upper() != jurisdiction.upper():
            continue
        for rule in rs.rules:
            if rule.id in out:
                raise ValueError(f"duplicate rule id {rule.id!r} in {path}")
            out[rule.id] = rule
    return out
