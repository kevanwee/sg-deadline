"""Run the sg-deadline engine and print the legal-engineering computation contract (computation@1).

Usage:
    python contract.py compute <rule-id> <YYYY-MM-DD>
    python contract.py limitation <rule-id> <YYYY-MM-DD>

Exit codes: 0 computed, 2 unknown rule or bad input, 3 holiday data missing, 4 engine not installed.
"""

import contextlib
import json
import sys
from datetime import date
from pathlib import Path


def engine_revision():
    source = Path(__file__).resolve().parent.parent / "TOOLKIT-SOURCE.json"
    if source.is_file():
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
    if len(argv) != 3 or argv[0] not in ("compute", "limitation"):
        emit({"status": "error", "error": __doc__.strip()}, 2)
    kind, rule_id, trigger_text = argv
    try:
        from sg_deadline.calendar import HolidayDataMissingError, load_calendar
        from sg_deadline.engine import compute
        from sg_deadline.limitation import limitation_period, load_limitation_rules
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
    rule, cal = rules[rule_id], load_calendar("SG")
    try:
        result = (
            compute(rule, trigger, cal)
            if kind == "compute"
            else limitation_period(rule, trigger, cal)
        )
    except HolidayDataMissingError as exc:
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
    years = []
    touched_years = ({result.deadline.year} if kind == "limitation" else range(
        min(trigger.year, result.deadline.year), max(trigger.year, result.deadline.year) + 1
    ))
    for year in sorted(touched_years):
        with contextlib.suppress(HolidayDataMissingError):
            years.append({"year": year, "verified": cal.ensure_year(year).verified})
    limitations = list(result.warnings)
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
            "trace": list(result.trace),
            "calendar": {"jurisdiction": "SG", "years": years},
            "engine": {"name": "sg-deadline", "revision": engine_revision()},
            "limitations": limitations,
        }
    )


if __name__ == "__main__":
    main(sys.argv[1:])
