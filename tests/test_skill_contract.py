"""The skill adapter must report the engine's result and its limits, never a guessed date."""

import json
import subprocess
import sys
from pathlib import Path

ADAPTER = Path(__file__).resolve().parents[1] / "skills" / "sg-deadline" / "scripts" / "contract.py"
KEYS = {"result_date", "rule", "trace", "calendar", "engine", "limitations"}


def run(*args):
    process = subprocess.run([sys.executable, str(ADAPTER), *args], capture_output=True, text=True)
    return process.returncode, json.loads(process.stdout)


def test_compute_matches_engine_and_flags_unverified_inputs():
    code, out = run("compute", "sg.roc2021.defence", "2026-03-13")
    assert code == 0 and set(out) == KEYS
    assert out["result_date"] == "2026-04-06"
    assert out["rule"] == {
        "id": "sg.roc2021.defence",
        "source": "Rules of Court 2021, O 6 r 7",
        "verified": False,
    }
    assert any("DEADLINE: 2026-04-06" in line for line in out["trace"])
    assert {"year": 2026, "verified": False} in out["calendar"]["years"]
    assert any(
        "UNVERIFIED" in item for item in out["limitations"]
    )  # unverified rule must be disclosed


def test_limitation_is_not_rolled_and_says_so():
    code, out = run("limitation", "sg.limitation.contract", "2020-03-15")
    assert code == 0 and out["result_date"] == "2026-03-15"
    assert any("not rolled forward" in item for item in out["limitations"])


def test_missing_holiday_year_returns_no_date():
    code, out = run("compute", "sg.roc2021.defence", "2030-03-13")
    assert code == 3 and out["result_date"] is None
    assert out["limitations"] and "Holiday data missing" in out["limitations"][0]


def test_unknown_rule_and_bad_date_are_errors():
    assert run("compute", "sg.no-such-rule", "2026-01-01")[0] == 2
    assert run("compute", "sg.roc2021.defence", "13/03/2026")[0] == 2


def test_future_limitation_computes_without_claiming_calendar_coverage():
    code, out = run("limitation", "sg.limitation.contract", "2026-10-24")
    # Six anniversaries after 24 Oct 2026 is 24 Oct 2032; no business-day roll.
    assert code == 0 and out["result_date"] == "2032-10-24"
    assert out["calendar"]["years"] == []
    assert any("was not checked" in note for note in out["limitations"])
