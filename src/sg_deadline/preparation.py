"""Front-end preparation: acquire calendars, freeze inputs, then call pure arithmetic.

Operations passed here must be deterministic and free of external effects: an
operation can be replayed after a missing calendar has been acquired. The engine
itself still reads no network and never suppresses missing-year errors.
"""

from __future__ import annotations

import json
import os
import uuid
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

from .calendar import Calendar, HolidayDataMissingError
from .calendar_store import (
    TTL,
    CalendarSourceError,
    CalendarStore,
    _parse_payload,
    canonical,
    digest,
)


class TrackedCalendar(Calendar):
    def __init__(self, original: Calendar):
        super().__init__(original.jurisdiction, dict(original.years), original.weekend)
        self.used: set[int] = set()

    def ensure_year(self, year: int):
        self.used.add(year)
        return super().ensure_year(year)


@dataclass
class Prepared:
    value: Any
    calendar: Calendar
    receipt: dict
    notes: list[str]
    warnings: list[str]


def prepare(
    operation: Callable,
    *,
    store: CalendarStore | None = None,
    offline: bool = False,
    refresh: bool = False,
    identity: dict | None = None,
    receipt_path: Path | None = None,
    replay: Path | None = None,
) -> Prepared:
    store = store or CalendarStore()
    identity = identity or {}
    warnings = []
    if replay:
        try:
            receipt = json.loads(Path(replay).read_bytes())
            if receipt.get("schema_version") != "1":
                raise CalendarSourceError("Unsupported calculation receipt version")
        except (OSError, ValueError, AttributeError) as exc:
            raise CalendarSourceError(f"Calculation receipt could not be read: {exc}") from exc
        body = {k: v for k, v in receipt.items() if k != "sha256"}
        if digest(canonical(body)) != receipt.get("sha256"):
            raise CalendarSourceError("Calculation receipt failed its hash check")
        if receipt["identity"] != identity:
            raise CalendarSourceError("Replay requires the same rule, inputs and engine revision")
        original = Calendar("SG")
        records = {int(year): row for year, row in receipt["calendars"].items()}
        for year, row in records.items():
            if row["calendar"]["jurisdiction"] != "SG" or row["calendar"]["year"] != year:
                raise CalendarSourceError("Receipt calendar jurisdiction or year is inconsistent")
            original.years[year] = _parse_payload(row["calendar"])
        cal = TrackedCalendar(original)
        value = operation(cal)
        notes = [*receipt["notes"], "Calculation receipt SHA-256 " + receipt["sha256"]]
        return Prepared(value, cal, receipt, notes, list(receipt["warnings"]))
    refreshed = False
    while True:
        original, records = store.calendar()
        cal = TrackedCalendar(original)
        try:
            value = operation(cal)
        except HolidayDataMissingError as exc:
            if offline or refreshed:
                detail = (
                    "Offline mode: no calendar retrieval attempted."
                    if offline
                    else "Official source has no usable calendar for this calculation."
                )
                raise HolidayDataMissingError(f"{exc} {detail}", year=exc.year) from exc
            status = store.refresh(exc.year, force=refresh)
            refreshed = True
            if status["error"]:
                raise HolidayDataMissingError(f"{exc} {status['error']}", year=exc.year) from exc
            continue
        stale = any(
            records[year]["provenance"]["kind"] == "bundled"
            or store.now() - datetime.fromisoformat(records[year]["provenance"]["retrieved_at"])
            >= TTL
            for year in cal.used
        )
        if not offline and not refreshed and (refresh or stale):
            status = store.refresh(force=refresh)
            refreshed = True
            if status["error"]:
                warnings.append(
                    "Calendar refresh unavailable; using the recorded cached/bundled "
                    "snapshot. " + status["error"]
                )
            else:
                continue
        if offline:
            warnings.append("Offline calendar mode: published amendments were not checked.")
        elif stale and refreshed:
            warnings.append(
                "Calendar snapshot is bundled or older than seven days; "
                "confirm whether the publisher has issued amendments."
            )
        break
    notes = []
    selected = {}
    for year in sorted(cal.used):
        row = records[year]
        snapshot_id = row.get("snapshot_id") or digest(canonical(row))
        selected[str(year)] = row | {"snapshot_id": snapshot_id}
        prov = row["provenance"]
        notes.append(
            f"Calendar SG {year} snapshot {snapshot_id}; "
            f"retrieved {prov['retrieved_at']}; {row['calendar']['source']}; "
            "legal verification remains separate."
        )
    receipt = {
        "schema_version": "1",
        "identity": identity,
        "created_at": store.now().isoformat(),
        "calendars": selected,
        "notes": notes,
        "warnings": warnings,
    }
    receipt["sha256"] = digest(canonical(receipt))
    destination = receipt_path or store.root / "calculations" / (uuid.uuid4().hex + ".json")
    destination.parent.mkdir(parents=True, exist_ok=True)
    try:
        with destination.open("xb") as stream:
            stream.write(canonical(receipt))
            stream.flush()
            os.fsync(stream.fileno())
    except FileExistsError as exc:
        raise CalendarSourceError("Calculation receipt already exists; choose a new path") from exc
    notes = [*notes, "Calculation receipt SHA-256 " + receipt["sha256"]]
    return Prepared(value, cal, receipt, notes, warnings)
