"""Calendar preparation tests. Dates in altered/future publisher fixtures are synthetic."""

import json
from datetime import UTC, date, datetime, timedelta

import pytest

from sg_deadline.calendar import HolidayDataMissingError
from sg_deadline.calendar_store import (
    COLLECTION,
    DATA,
    METADATA,
    CalendarSourceError,
    CalendarStore,
    canonical,
)
from sg_deadline.preparation import prepare

CONSOLIDATED = "d_" + "a" * 32
ANNUAL = "d_" + "b" * 32
FUTURE = "d_" + "c" * 32
# MOM's published 2027 dates including the 8 February observed holiday.
DATES = [
    "2027-01-01",
    "2027-02-06",
    "2027-02-07",
    "2027-02-08",
    "2027-03-10",
    "2027-03-26",
    "2027-05-01",
    "2027-05-17",
    "2027-05-20",
    "2027-08-09",
    "2027-10-28",
    "2027-12-25",
]


class Publisher:
    def __init__(self):
        self.calls = []
        self.extra = False
        self.future = False
        self.broken = False
        self.partial = False

    def __call__(self, url):
        self.calls.append(url)
        if self.broken:
            raise OSError("SYNTHETIC network outage")
        if url == METADATA:
            return canonical(
                {
                    "data": {
                        "collectionMetadata": {
                            "collectionId": "691",
                            "managedBy": "Ministry of Manpower",
                            "childDatasets": [CONSOLIDATED, ANNUAL, FUTURE],
                        }
                    }
                }
            )
        if url == COLLECTION:
            names = {
                "Singapore Public Holidays (consolidated)": {"datasetId": CONSOLIDATED},
                "Public Holidays for 2027": {"datasetId": ANNUAL},
            }
            if self.future:
                names["Public Holidays for 2033"] = {"datasetId": FUTURE}
            return canonical(names)
        dataset = FUTURE if url == DATA.format(FUTURE) else CONSOLIDATED
        days = ["2033-01-01", "2033-12-25"] if dataset == FUTURE else DATES
        if self.extra and dataset == CONSOLIDATED:
            days = [*days, "2027-02-09"]
        rows = [
            {
                "date": day,
                "holiday": "SYNTHETIC publisher fixture",
                "day": date.fromisoformat(day).strftime("%A"),
            }
            for day in days
        ]
        return canonical(
            {
                "success": True,
                "result": {
                    "resource_id": dataset,
                    "records": rows,
                    "total": len(rows) + int(self.partial),
                },
            }
        )


def setup(tmp_path):
    source = Publisher()
    now = [datetime(2026, 10, 24, tzinfo=UTC)]
    store = CalendarStore(tmp_path, fetch=source, now=lambda: now[0])
    return source, now, store


def next_day(cal):
    # Friday 5 February + one working day skips Sat/Sun and observed Mon 8 -> Tue 9.
    return cal.add_working_days(date(2027, 2, 5), 1)


def test_missing_year_fetches_official_collection_once_then_works_offline(tmp_path):
    source, _, store = setup(tmp_path)
    result = prepare(next_day, store=store, identity={"rule": "SYNTHETIC one working day"})
    assert result.value == date(2027, 2, 9)
    assert len(source.calls) == 3
    assert result.receipt["calendars"]["2027"]["calendar"]["verified"] is False
    snapshot = result.receipt["calendars"]["2027"]["snapshot_id"]
    assert store.read_snapshot(snapshot)["provenance"]["documents"]
    source.broken = True
    again = prepare(next_day, store=store, offline=True)
    assert again.value == date(2027, 2, 9) and len(source.calls) == 3
    assert any("Offline" in warning for warning in again.warnings)


def test_refresh_changes_new_calculations_but_receipt_replays_original(tmp_path):
    source, now, store = setup(tmp_path)
    path = tmp_path / "matter-receipt.json"
    original = prepare(next_day, store=store, identity={"rule": "SYNTHETIC"}, receipt_path=path)
    original_bytes = path.read_bytes()
    source.extra = True
    now[0] += timedelta(days=8)
    # In this synthetic amendment Tuesday 9 is also a holiday -> Wednesday 10.
    updated = prepare(next_day, store=store, identity={"rule": "SYNTHETIC"})
    assert updated.value == date(2027, 2, 10)
    assert store.status()["last_refresh"]["changed_years"] == [2027]
    assert original.receipt["calendars"] != updated.receipt["calendars"]
    assert path.read_bytes() == original_bytes
    assert original.value == date(2027, 2, 9)
    source.broken = True
    replay = prepare(next_day, store=store, replay=path, identity={"rule": "SYNTHETIC"})
    assert replay.value == original.value and replay.notes == original.notes
    with pytest.raises(CalendarSourceError, match="same rule"):
        prepare(next_day, store=store, replay=path, identity={"rule": "different"})


def test_dynamic_later_year_is_discovered_without_changing_code(tmp_path):
    source, _, store = setup(tmp_path)
    source.future = True
    # Fixture-only 2033 year proves discovery is not bounded to current catalogue years.
    result = prepare(lambda cal: cal.is_working(date(2033, 1, 3)), store=store)
    assert result.value is True
    assert "2033" in result.receipt["calendars"]
    assert DATA.format(FUTURE) in source.calls


def test_unpublished_year_and_network_failure_never_invent_calendar(tmp_path):
    source, _, store = setup(tmp_path)
    with pytest.raises(HolidayDataMissingError):
        prepare(lambda cal: cal.is_working(date(2099, 1, 2)), store=store)
    assert store.current(2099) is None
    source.broken = True
    status = store.refresh(force=True)
    assert status["status"] == "unavailable"
    with pytest.raises(HolidayDataMissingError):
        prepare(next_day, store=CalendarStore(tmp_path / "empty", fetch=source))


def test_expired_cache_falls_back_with_warning_and_refresh_can_be_forced(tmp_path):
    source, now, store = setup(tmp_path)
    prepare(next_day, store=store)
    now[0] += timedelta(days=8)
    source.broken = True
    result = prepare(next_day, store=store)
    assert result.value == date(2027, 2, 9)
    assert any("refresh unavailable" in warning for warning in result.warnings)
    source.broken = False
    source.extra = True
    assert prepare(next_day, store=store, refresh=True).value == date(2027, 2, 10)


def test_partial_or_tampered_data_cannot_replace_or_drive_calendar(tmp_path):
    source, _, store = setup(tmp_path)
    original = prepare(next_day, store=store)
    pointer = (tmp_path / "years/sg-2027.json").read_bytes()
    source.partial = True
    assert store.refresh(force=True)["status"] == "unavailable"
    assert (tmp_path / "years/sg-2027.json").read_bytes() == pointer
    row = original.receipt["calendars"]["2027"]
    sha = row["provenance"]["documents"][-1]["sha256"]
    (tmp_path / "raw" / sha).write_bytes(b"altered")
    with pytest.raises(CalendarSourceError, match="hash check"):
        prepare(next_day, store=store, offline=True)


def test_offline_replay_needs_no_cache_and_rejects_tampering(tmp_path):
    _, _, store = setup(tmp_path / "cache")
    receipt = tmp_path / "receipt.json"
    prepare(next_day, store=store, receipt_path=receipt, identity={"rule": "fixed"})
    empty = CalendarStore(tmp_path / "empty", fetch=lambda _: pytest.fail("Network used on replay"))
    assert prepare(next_day, store=empty, replay=receipt, identity={"rule": "fixed"}).value == date(
        2027, 2, 9
    )
    value = json.loads(receipt.read_bytes())
    value["calendars"]["2027"]["calendar"]["holidays"] = []
    receipt.write_text(json.dumps(value))
    with pytest.raises(CalendarSourceError, match="hash check"):
        prepare(next_day, store=empty, replay=receipt, identity={"rule": "fixed"})


def test_arithmetic_core_still_refuses_missing_year_without_network():
    from sg_deadline.calendar import load_calendar

    with pytest.raises(HolidayDataMissingError) as error:
        load_calendar().is_working(date(2033, 1, 3))
    assert error.value.year == 2033


def test_existing_receipt_is_never_overwritten(tmp_path):
    _, _, store = setup(tmp_path / "cache")
    receipt = tmp_path / "receipt.json"
    prepare(next_day, store=store, receipt_path=receipt)
    original = receipt.read_bytes()
    with pytest.raises(CalendarSourceError, match="already exists"):
        prepare(next_day, store=store, receipt_path=receipt)
    assert receipt.read_bytes() == original
