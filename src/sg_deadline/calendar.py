"""Working-day calendar backed by vendored public-holiday data.

Design rule: the engine must never *silently* treat a holiday as a working day.
If holiday data for a year is absent we raise HolidayDataMissingError rather than guess.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import date, timedelta
from pathlib import Path

from .paths import HOLIDAYS_DIR

SATURDAY, SUNDAY = 5, 6


class HolidayDataMissingError(LookupError):
    """Raised when a computation touches a year with no vendored holiday file."""


@dataclass(frozen=True)
class HolidayYear:
    year: int
    holidays: dict[date, str]
    source: str
    retrieved: str
    verified: bool


@dataclass
class Calendar:
    """Jurisdiction calendar. `years` holds every year we have authoritative data for."""

    jurisdiction: str
    years: dict[int, HolidayYear] = field(default_factory=dict)
    weekend: tuple[int, ...] = (SATURDAY, SUNDAY)

    # -- data coverage ---------------------------------------------------------------

    def ensure_year(self, year: int) -> HolidayYear:
        try:
            return self.years[year]
        except KeyError:
            raise HolidayDataMissingError(
                f"No public-holiday data for {self.jurisdiction} {year}. "
                f"Add data/holidays/{self.jurisdiction.lower()}-{year}.json "
                "(see scripts/refresh_holidays.py)."
            ) from None

    def holiday_name(self, d: date) -> str | None:
        return self.ensure_year(d.year).holidays.get(d)

    def coverage_notes(self, *dates: date) -> list[str]:
        """Provenance lines for every year touched, for inclusion in a trace."""
        out = []
        for year in sorted({d.year for d in dates}):
            hy = self.ensure_year(year)
            status = "verified" if hy.verified else "UNVERIFIED"
            out.append(
                f"holiday data {self.jurisdiction} {year}: {status}, "
                f"source={hy.source}, retrieved={hy.retrieved}"
            )
        return out

    # -- predicates ------------------------------------------------------------------

    def is_weekend(self, d: date) -> bool:
        return d.weekday() in self.weekend

    def is_holiday(self, d: date) -> bool:
        return self.holiday_name(d) is not None

    def is_working(self, d: date) -> bool:
        # Check coverage first so a weekend never masks missing holiday data.
        self.ensure_year(d.year)
        return not self.is_weekend(d) and not self.is_holiday(d)

    def why_non_working(self, d: date) -> str | None:
        """Human-readable reason a day is non-working, or None if it is a working day."""
        self.ensure_year(d.year)
        if self.is_weekend(d):
            return d.strftime("%A")
        name = self.holiday_name(d)
        return f"public holiday ({name})" if name else None

    # -- arithmetic ------------------------------------------------------------------

    def next_working(self, d: date, *, inclusive: bool = True) -> date:
        cur = d if inclusive else d + timedelta(days=1)
        while not self.is_working(cur):
            cur += timedelta(days=1)
        return cur

    def prev_working(self, d: date, *, inclusive: bool = True) -> date:
        cur = d if inclusive else d - timedelta(days=1)
        while not self.is_working(cur):
            cur -= timedelta(days=1)
        return cur

    def add_working_days(self, d: date, n: int) -> date:
        """Move n working days from d (d itself not counted). Negative n moves backwards."""
        step = 1 if n >= 0 else -1
        remaining = abs(n)
        cur = d
        while remaining:
            cur += timedelta(days=step)
            if self.is_working(cur):
                remaining -= 1
        return cur

    def working_days_between(self, start: date, end: date) -> int:
        """Count working days strictly after `start` up to and including `end`."""
        if end < start:
            return -self.working_days_between(end, start)
        count = 0
        cur = start
        while cur < end:
            cur += timedelta(days=1)
            if self.is_working(cur):
                count += 1
        return count


# -- loading -------------------------------------------------------------------------


def _parse_holiday_file(path: Path) -> HolidayYear:
    raw = json.loads(path.read_text(encoding="utf-8"))
    holidays = {date.fromisoformat(h["date"]): h["name"] for h in raw["holidays"]}
    return HolidayYear(
        year=int(raw["year"]),
        holidays=holidays,
        source=raw.get("source", "unknown"),
        retrieved=raw.get("retrieved", "unknown"),
        verified=bool(raw.get("verified", False)),
    )


def load_calendar(jurisdiction: str = "SG", holidays_dir: Path | None = None) -> Calendar:
    """Load every `<jur>-<year>.json` in the holidays directory for the jurisdiction."""
    directory = holidays_dir or HOLIDAYS_DIR
    prefix = f"{jurisdiction.lower()}-"
    years: dict[int, HolidayYear] = {}
    for path in sorted(directory.glob(f"{prefix}*.json")):
        hy = _parse_holiday_file(path)
        years[hy.year] = hy
    return Calendar(jurisdiction=jurisdiction.upper(), years=years)
