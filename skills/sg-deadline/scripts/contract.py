"""Run the sg-deadline engine and print the legal-engineering computation contract (computation@1).

Usage:
    python contract.py compute <rule-id> <YYYY-MM-DD>
    python contract.py limitation <rule-id> <YYYY-MM-DD>

Exit codes: 0 computed, 2 unknown rule or bad input, 3 holiday data missing, 4 engine not installed.
"""

import argparse
import json
import os
import sys
from datetime import date
from pathlib import Path

# Workspace assemblies can supply the engine and resources from the same pinned
# archive as this adapter. Prefer those bytes over a machine's installed package.
RUNTIME = Path(__file__).resolve().parent.parent / "runtime"
if (RUNTIME / "sg_deadline" / "__init__.py").is_file():
    sys.path.insert(0, str(RUNTIME))


def engine_revision():
    source = Path(__file__).resolve().parent.parent / "TOOLKIT-SOURCE.json"
    if source.is_file() and (RUNTIME / "sg_deadline" / "__init__.py").is_file():
        return json.loads(source.read_text(encoding="utf-8"))["revision"]
    try:
        from importlib.metadata import version

        return "sg-deadline " + version("sg-deadline")
    except Exception:
        return "unknown"


def emit(payload, code=0):
    print(json.dumps(payload, indent=2))
    sys.exit(code)


def main(argv):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("kind", choices=["compute", "limitation"])
    parser.add_argument("rule_id")
    parser.add_argument("trigger")
    parser.add_argument(
        "--offline", action="store_true", default=os.environ.get("SG_DEADLINE_OFFLINE") == "1"
    )
    parser.add_argument("--refresh", action="store_true")
    parser.add_argument("--cache-dir", type=Path)
    parser.add_argument("--receipt", type=Path)
    parser.add_argument("--replay", type=Path)
    args = parser.parse_args(argv)
    kind, rule_id, trigger_text = args.kind, args.rule_id, args.trigger
    try:
        from sg_deadline.calendar import HolidayDataMissingError
        from sg_deadline.calendar_store import CalendarSourceError, CalendarStore, canonical, digest
        from sg_deadline.engine import compute
        from sg_deadline.limitation import limitation_period, load_limitation_rules
        from sg_deadline.preparation import prepare
        from sg_deadline.rules import load_rules
    except ImportError:
        emit(
            {
                "status": "error",
                "error": "sg-deadline is not installed; see SKILL.md. "
                "Do not compute the date by hand.",
            },
            4,
        )
    try:
        trigger = date.fromisoformat(trigger_text)
    except ValueError:
        emit({"status": "error", "error": f"Trigger must be YYYY-MM-DD, got {trigger_text!r}"}, 2)
    rules = load_rules() if kind == "compute" else load_limitation_rules()
    if rule_id not in rules:
        emit(
            {
                "status": "error",
                "error": f"Unknown rule {rule_id!r}; "
                "list rules with python -m sg_deadline.cli rules",
            },
            2,
        )
    rule = rules[rule_id]
    skill = Path(__file__).resolve().parent.parent
    cache = args.cache_dir
    if (
        cache is None
        and "SG_DEADLINE_CACHE" not in os.environ
        and skill.parent.name == "skills"
        and skill.parent.parent.name in {".agents", ".claude"}
    ):
        cache = skill.parents[2] / ".legal-eng/calendars"
    identity = {
        "engine": engine_revision(),
        "kind": kind,
        "rule_id": rule_id,
        "trigger": trigger_text,
        "rule_sha256": digest(canonical(rule.model_dump(mode="json"))),
    }
    try:
        prepared = prepare(
            lambda cal: (
                compute(rule, trigger, cal)
                if kind == "compute"
                else limitation_period(rule, trigger, cal)
            ),
            store=CalendarStore(cache),
            offline=args.offline,
            refresh=args.refresh,
            identity=identity,
            receipt_path=args.receipt,
            replay=args.replay,
        )
        result, cal = prepared.value, prepared.calendar
    except (HolidayDataMissingError, CalendarSourceError, OSError) as exc:
        emit(
            {
                "result_date": None,
                "rule": {"id": rule.id, "source": rule.source, "verified": rule.verified},
                "trace": [f"No computation: {exc}"],
                "calendar": {"jurisdiction": "SG", "years": []},
                "engine": {"name": "sg-deadline", "revision": engine_revision()},
                "limitations": [
                    f"Holiday data missing: {str(exc).rstrip('.')}. "
                    "The date cannot be computed until the gazetted holidays are added."
                ],
            },
            3,
        )
    years = [
        {"year": year, "verified": cal.ensure_year(year).verified} for year in sorted(cal.used)
    ]
    limitations = [*result.warnings, *prepared.warnings]
    for entry in years:
        if not entry["verified"]:
            limitations.append(
                f"Holiday data for SG {entry['year']} is unverified; "
                "check it against the gazetted public holidays."
            )
    if kind == "limitation":
        limitations.append(
            "Limitation date: the last day to commence proceedings; "
            "it is not rolled forward to a working day."
        )
    emit(
        {
            "result_date": result.deadline.isoformat(),
            "rule": {"id": rule.id, "source": rule.source, "verified": bool(rule.verified)},
            "trace": [*result.trace, *prepared.notes],
            "calendar": {"jurisdiction": "SG", "years": years},
            "engine": {"name": "sg-deadline", "revision": engine_revision()},
            "limitations": limitations,
        }
    )


if __name__ == "__main__":
    main(sys.argv[1:])
