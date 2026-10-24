"""Official-calendar preparation and immutable cache, outside the arithmetic engine.

Only calendar requests (never matter facts) leave this process. Downloaded data
remains unverified. A source change creates a snapshot; it never edits a receipt.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import tempfile
import urllib.parse
import urllib.request
import uuid
from contextlib import contextmanager
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from typing import Any

from .calendar import Calendar, HolidayYear, load_calendar
from .paths import HOLIDAYS_DIR

COLLECTION = "https://data.gov.sg/collections/691/view"
METADATA = "https://api-production.data.gov.sg/v2/public/api/collections/691/metadata"
DATA = "https://data.gov.sg/api/action/datastore_search?resource_id={}&limit=10000"
TTL = timedelta(days=7)


class CalendarSourceError(ValueError):
    """Official data unavailable, malformed, incomplete, or cached bytes altered."""


def canonical(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(",", ":")).encode()


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def utcnow() -> datetime:
    return datetime.now(UTC)


def default_cache() -> Path:
    if os.environ.get("SG_DEADLINE_CACHE"):
        return Path(os.environ["SG_DEADLINE_CACHE"]).expanduser()
    base = Path(os.environ.get("LOCALAPPDATA", Path.home() / ".cache"))
    return base / "sg-deadline" / "calendars"


def atomic_bytes(path: Path, raw: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    handle, name = tempfile.mkstemp(dir=path.parent, prefix=".writing-")
    try:
        with os.fdopen(handle, "wb") as stream:
            stream.write(raw)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(name, path)
    finally:
        Path(name).unlink(missing_ok=True)


def atomic_json(path: Path, value: Any) -> None:
    atomic_bytes(path, canonical(value))


@contextmanager
def cache_lock(root: Path):
    root.mkdir(parents=True, exist_ok=True)
    with (root / "refresh.lock").open("a+b") as stream:
        stream.seek(0)
        if os.name == "nt":
            import msvcrt

            # Windows permits locking beyond EOF. Reading/initialising this
            # byte first races another process which already owns its lock.
            msvcrt.locking(stream.fileno(), msvcrt.LK_LOCK, 1)
        else:
            import fcntl

            fcntl.flock(stream, fcntl.LOCK_EX)
        try:
            yield
        finally:
            if os.name == "nt":
                stream.seek(0)
                msvcrt.locking(stream.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                fcntl.flock(stream, fcntl.LOCK_UN)


def download(url: str) -> bytes:
    """Fixed official endpoints only; redirects cannot change the trusted host."""
    request = urllib.request.Request(
        url,
        headers={
            "User-Agent": "sg-deadline/0.2 official-calendar-client",
            "Accept": "application/json,text/html",
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=12) as response:
            final = urllib.parse.urlsplit(response.url)
            expected = urllib.parse.urlsplit(url)
            if final.scheme != "https" or final.hostname != expected.hostname:
                raise CalendarSourceError("Official calendar endpoint redirected to another host")
            raw = response.read(4 * 1024 * 1024 + 1)
            if len(raw) > 4 * 1024 * 1024:
                raise CalendarSourceError("Official calendar response exceeds the supported size")
            return raw
    except (OSError, ValueError) as exc:
        raise CalendarSourceError(f"Official calendar retrieval failed: {exc}") from exc


def holiday_payloads(raw: bytes, dataset: str) -> dict[int, list[dict]]:
    try:
        value = json.loads(raw)
        result = value["result"]
        rows = result["records"]
        if (
            value.get("success") is not True
            or result["resource_id"] != dataset
            or not rows
            or len(rows) != result["total"]
        ):
            raise ValueError("partial or mismatched dataset")
        years: dict[int, list[dict]] = {}
        seen = set()
        for row in rows:
            day = date.fromisoformat(row["date"])
            name = row["holiday"]
            if (
                day in seen
                or not isinstance(name, str)
                or not name.strip()
                or ("Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday")[
                    day.weekday()
                ]
                != row["day"]
            ):
                raise ValueError("duplicate date, empty name or inconsistent weekday")
            seen.add(day)
            years.setdefault(day.year, []).append({"date": day.isoformat(), "name": name})
        return {year: sorted(entries, key=lambda h: h["date"]) for year, entries in years.items()}
    except (ValueError, KeyError, TypeError) as exc:
        raise CalendarSourceError(f"Official calendar dataset failed validation: {exc}") from exc


class CalendarStore:
    def __init__(self, root: Path | None = None, *, fetch=download, now=utcnow):
        self.root = Path(root) if root is not None else default_cache()
        self.fetch = fetch
        self.now = now

    def save_raw(self, raw: bytes) -> str:
        sha = digest(raw)
        target = self.root / "raw" / sha
        target.parent.mkdir(parents=True, exist_ok=True)
        if target.exists():
            if digest(target.read_bytes()) != sha:
                raise CalendarSourceError("Cached official source bytes failed their hash check")
        else:
            atomic_bytes(target, raw)
        return sha

    def read_snapshot(self, snapshot_id: str) -> dict:
        if not re.fullmatch(r"[a-f0-9]{64}", snapshot_id):
            raise CalendarSourceError("Invalid calendar snapshot identifier")
        path = self.root / "snapshots" / (snapshot_id + ".json")
        raw = path.read_bytes()
        if digest(raw) != snapshot_id:
            raise CalendarSourceError("Calendar snapshot failed its hash check")
        snapshot = json.loads(raw)
        for source in snapshot["provenance"].get("documents", []):
            source_hash = source["sha256"]
            if not re.fullmatch(r"[a-f0-9]{64}", source_hash):
                raise CalendarSourceError("Invalid official-source hash")
            if digest((self.root / "raw" / source_hash).read_bytes()) != source_hash:
                raise CalendarSourceError("Cached official source bytes failed their hash check")
        return snapshot

    def current(self, year: int) -> tuple[str, dict] | None:
        path = self.root / "years" / f"sg-{year}.json"
        if not path.exists():
            return None
        try:
            item = json.loads(path.read_bytes())
            snapshot = self.read_snapshot(item["snapshot"])
            if snapshot["calendar"]["year"] != year:
                raise CalendarSourceError("Calendar pointer names a different year")
            return item["snapshot"], snapshot
        except (OSError, ValueError, KeyError, TypeError) as exc:
            raise CalendarSourceError(f"Invalid calendar cache for {year}: {exc}") from exc

    def publish(self, calendar: dict, provenance: dict) -> str:
        value = {"calendar": calendar, "provenance": provenance}
        raw = canonical(value)
        sha = digest(raw)
        path = self.root / "snapshots" / (sha + ".json")
        path.parent.mkdir(parents=True, exist_ok=True)
        if not path.exists():
            atomic_bytes(path, raw)
        elif digest(path.read_bytes()) != sha:
            raise CalendarSourceError("Calendar snapshot failed its hash check")
        atomic_json(self.root / "years" / f"sg-{calendar['year']}.json", {"snapshot": sha})
        return sha

    def refresh(self, year: int | None = None, *, force: bool = False) -> dict:
        """Refresh all published years in one batch, never infer unpublished holidays."""
        with cache_lock(self.root):
            status_file = self.root / "last-refresh.json"
            status = json.loads(status_file.read_bytes()) if status_file.exists() else {}
            checked = datetime.fromisoformat(status["checked_at"]) if status else None
            retry = timedelta(minutes=15) if status.get("error") else timedelta(days=1)
            if checked and not force and self.now() - checked < retry:
                return status
            try:
                metadata_raw = self.fetch(METADATA)
                meta = json.loads(metadata_raw)["data"]["collectionMetadata"]
                if (
                    meta["managedBy"] != "Ministry of Manpower"
                    or str(meta["collectionId"]) != "691"
                ):
                    raise CalendarSourceError("Calendar collection publisher or identity changed")
                page_raw = self.fetch(COLLECTION)
                page = page_raw.decode("utf-8").replace('\\"', '"')
                found = re.findall(
                    r'"Public Holidays for (\d{4})":\{"datasetId":"(d_[a-f0-9]{32})"', page
                )
                annual = {int(y): dataset for y, dataset in found}
                if any(len({d for y, d in found if int(y) == year}) != 1 for year in annual):
                    raise CalendarSourceError("Official calendar catalogue has ambiguous years")
                consolidated = re.findall(
                    r'"Singapore Public Holidays \(consolidated\)":'
                    r'\{"datasetId":"(d_[a-f0-9]{32})"',
                    page,
                )
                if not annual or len(set(consolidated)) != 1:
                    raise CalendarSourceError("Official calendar catalogue format changed")
                datasets = [consolidated[0]]
                documents = [
                    {"url": METADATA, "sha256": self.save_raw(metadata_raw)},
                    {"url": COLLECTION, "sha256": self.save_raw(page_raw)},
                ]
                by_year = {}
                origins = {}
                while datasets:
                    dataset = datasets.pop(0)
                    if dataset not in meta["childDatasets"]:
                        raise CalendarSourceError("Dataset is outside the official MOM collection")
                    url = DATA.format(dataset)
                    raw = self.fetch(url)
                    grouped = holiday_payloads(raw, dataset)
                    if dataset != consolidated[0] and set(grouped) != {
                        y for y, value in annual.items() if value == dataset
                    }:
                        raise CalendarSourceError("Annual calendar contains another year")
                    doc = {"url": url, "sha256": self.save_raw(raw)}
                    for y, holidays in grouped.items():
                        if y not in annual:
                            raise CalendarSourceError(
                                "Dataset contains an unpublished catalogue year"
                            )
                        by_year[y] = holidays
                        origins[y] = (dataset, doc)
                    if dataset == consolidated[0]:
                        datasets.extend(annual[y] for y in sorted(set(annual) - set(grouped)))
                # Everything is validated before any year pointer is changed.
                changed, added = [], []
                for y, holidays in by_year.items():
                    previous = self.current(y)
                    if previous is None:
                        added.append(y)
                    elif previous[1]["calendar"]["holidays"] != holidays:
                        changed.append(y)
                    dataset, doc = origins[y]
                    calendar = {
                        "jurisdiction": "SG",
                        "year": y,
                        "holidays": holidays,
                        "source": f"MOM data.gov.sg dataset {dataset}",
                        "retrieved": self.now().date().isoformat(),
                        "verified": False,
                    }
                    self.publish(
                        calendar,
                        {
                            "kind": "official-download",
                            "dataset_id": dataset,
                            "retrieved_at": self.now().isoformat(),
                            "documents": [*documents, doc],
                        },
                    )
                status = {
                    "checked_at": self.now().isoformat(),
                    "status": "ok",
                    "published_years": sorted(by_year),
                    "added_years": sorted(added),
                    "changed_years": sorted(changed),
                    "error": None,
                }
            except (OSError, ValueError, KeyError, TypeError) as exc:
                status = {
                    "checked_at": self.now().isoformat(),
                    "status": "unavailable",
                    "published_years": status.get("published_years", []),
                    "error": str(exc),
                }
            atomic_json(self.root / "refreshes" / (uuid.uuid4().hex + ".json"), status)
            atomic_json(status_file, status)
            return status

    def calendar(self) -> tuple[Calendar, dict[int, dict]]:
        cal = load_calendar("SG")
        records = {}
        for year, holiday_year in cal.years.items():
            path = HOLIDAYS_DIR / f"sg-{year}.json"
            payload = json.loads(path.read_bytes())
            records[year] = {
                "calendar": payload,
                "provenance": {
                    "kind": "bundled",
                    "source_sha256": digest(path.read_bytes()),
                    "retrieved_at": holiday_year.retrieved,
                },
            }
        for path in sorted((self.root / "years").glob("sg-*.json")):
            year = int(path.stem[3:])
            item = self.current(year)
            if item:
                sha, snapshot = item
                cal.years[year] = _parse_payload(snapshot["calendar"])
                records[year] = snapshot | {"snapshot_id": sha}
        return cal, records

    def status(self) -> dict:
        cal, records = self.calendar()
        path = self.root / "last-refresh.json"
        last = json.loads(path.read_bytes()) if path.exists() else None
        return {
            "jurisdiction": "SG",
            "refresh_interval_days": 7,
            "last_refresh": last,
            "network_at_arithmetic_time": False,
            "years": [
                {
                    "year": year,
                    "verified": item.verified,
                    "source": item.source,
                    "kind": records[year]["provenance"]["kind"],
                    "snapshot_id": records[year].get("snapshot_id"),
                    "retrieved_at": records[year]["provenance"]["retrieved_at"],
                }
                for year, item in sorted(cal.years.items())
            ],
        }


def _parse_payload(payload: dict) -> HolidayYear:
    return HolidayYear(
        year=payload["year"],
        holidays={date.fromisoformat(h["date"]): h["name"] for h in payload["holidays"]},
        source=payload["source"],
        retrieved=payload["retrieved"],
        verified=payload["verified"],
    )
