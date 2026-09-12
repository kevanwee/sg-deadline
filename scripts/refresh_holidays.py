"""Refresh data/holidays/sg-<year>.json from a data.gov.sg public-holidays dataset.

Usage:
    python scripts/refresh_holidays.py <year> <dataset_id> [--verified]

Find the dataset id by searching data.gov.sg for "Public Holidays for <year>" (published by
the Ministry of Manpower) and copying the id from the URL. The script writes a normalised
JSON file and leaves `verified: false` unless --verified is passed, because a human must
eyeball the result against the MOM gazette before the engine treats it as authoritative.

This script is the ONLY sanctioned way to produce holiday files by hand-editing is a
reviewable diff, never a silent edit.
"""

from __future__ import annotations

import argparse
import csv
import io
import json
import sys
import urllib.request
from datetime import date
from pathlib import Path

API = "https://api-open.data.gov.sg/v1/public/api/datasets/{id}/poll-download"
OUT = Path(__file__).resolve().parent.parent / "data" / "holidays"


def fetch_csv(dataset_id: str) -> str:
    with urllib.request.urlopen(API.format(id=dataset_id), timeout=30) as r:
        meta = json.load(r)
    url = meta["data"]["url"]
    with urllib.request.urlopen(url, timeout=30) as r:
        return r.read().decode("utf-8")


def normalise(csv_text: str, year: int) -> list[dict]:
    rows = list(csv.DictReader(io.StringIO(csv_text)))
    out = []
    for row in rows:
        d = date.fromisoformat(row["date"])
        if d.year != year:
            continue
        entry = {"date": d.isoformat(), "name": row["holiday"]}
        if "observance_strategy" in row and row["observance_strategy"] != "actual_day":
            entry["observance"] = row["observance_strategy"]
        out.append(entry)
    return sorted(out, key=lambda e: e["date"])


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("year", type=int)
    ap.add_argument("dataset_id")
    ap.add_argument("--verified", action="store_true")
    args = ap.parse_args()

    holidays = normalise(fetch_csv(args.dataset_id), args.year)
    if not holidays:
        print("no holidays parsed; check dataset id / column names", file=sys.stderr)
        return 1
    payload = {
        "jurisdiction": "SG",
        "year": args.year,
        "source": f"data.gov.sg dataset {args.dataset_id} (MOM)",
        "retrieved": date.today().isoformat(),
        "verified": args.verified,
        "holidays": holidays,
    }
    path = OUT / f"sg-{args.year}.json"
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    print(f"wrote {path} ({len(holidays)} entries, verified={args.verified})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
