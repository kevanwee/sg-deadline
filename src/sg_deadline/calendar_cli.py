"""Calendar maintenance, suitable for a periodic local scheduler or CI job."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from .calendar_store import CalendarSourceError, CalendarStore


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=["status", "refresh"])
    parser.add_argument("--cache-dir", type=Path)
    args = parser.parse_args(argv)
    store = CalendarStore(args.cache_dir)
    try:
        if args.action == "refresh":
            refresh = store.refresh(force=True)
            print(json.dumps(store.status(), indent=2))
            return 0 if refresh["status"] == "ok" else 3
        print(json.dumps(store.status(), indent=2))
        return 0
    except (OSError, CalendarSourceError) as exc:
        print(json.dumps({"status": "error", "error": str(exc)}))
        return 3


if __name__ == "__main__":
    raise SystemExit(main())
