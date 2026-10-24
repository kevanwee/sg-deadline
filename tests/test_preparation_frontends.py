"""All application entry points share preparation; pure arithmetic remains unchanged."""

import json
import subprocess
import sys
from pathlib import Path

from test_calendar_store import Publisher, setup

from sg_deadline.cli import main
from sg_deadline.preparation import prepare


def test_cli_uses_cached_year_and_replays_saved_receipt(tmp_path, capsys):
    _, _, store = setup(tmp_path / "cache")
    assert store.refresh()["status"] == "ok"
    receipt = tmp_path / "receipt.json"
    args = [
        "--calendar-cache",
        str(store.root),
        "--offline",
        "--json",
        "--receipt",
        str(receipt),
        "compute",
        "sg.roc2021.defence",
        "2027-01-16",
    ]
    assert main(args) == 0
    original = json.loads(capsys.readouterr().out)
    # 16 Jan + 21 calendar days = Sat 6 Feb, then Sun 7 and observed Mon 8 -> Tue 9.
    assert original["deadline"] == "2027-02-09"
    assert any("snapshot" in line for line in original["trace"])
    replay = [
        "--calendar-cache",
        str(tmp_path / "empty"),
        "--replay",
        str(receipt),
        "--json",
        "compute",
        "sg.roc2021.defence",
        "2027-01-16",
    ]
    assert main(replay) == 0
    assert json.loads(capsys.readouterr().out) == original


def test_contract_retains_computation_v1_shape_and_calendar_provenance(tmp_path):
    _, _, store = setup(tmp_path / "cache")
    store.refresh()
    adapter = Path(__file__).resolve().parents[1] / "skills/sg-deadline/scripts/contract.py"
    run = subprocess.run(
        [
            sys.executable,
            str(adapter),
            "compute",
            "sg.roc2021.defence",
            "2027-01-16",
            "--cache-dir",
            str(store.root),
            "--offline",
        ],
        capture_output=True,
        text=True,
    )
    assert run.returncode == 0, run.stderr
    result = json.loads(run.stdout)
    assert result["result_date"] == "2027-02-09"
    assert set(result) == {"result_date", "rule", "trace", "calendar", "engine", "limitations"}
    assert result["calendar"]["years"] == [{"year": 2027, "verified": False}]
    assert any("snapshot" in line for line in result["trace"])
    assert result["limitations"]


def test_mcp_tools_use_preparation_for_procedural_notice_and_working_days(tmp_path, monkeypatch):
    from sg_deadline import server

    _, _, store = setup(tmp_path / "cache")
    store.refresh()
    monkeypatch.setattr(
        server, "prepare", lambda operation, **kwargs: prepare(operation, store=store, **kwargs)
    )
    result = server.compute_deadline("sg.roc2021.defence", "2027-01-16")
    assert result["deadline"] == "2027-02-09"
    assert result["calendar_receipt"]["calendars"]["2027"]
    assert server.add_working_days("2027-02-05", 1)["date"] == "2027-02-09"
    assert server.working_days_between("2027-02-05", "2027-02-09")["working_days"] == 1
    assert server.is_working_day("2027-02-08")["working"] is False
    notice = server.deemed_receipt_date("email", "2027-02-05T18:00", cutoff="17:00")
    assert notice["deadline"] == "2027-02-09"


def test_failed_refresh_is_retried_after_short_cooldown(tmp_path):
    source, now, store = setup(tmp_path)
    source.broken = True
    assert store.refresh()["status"] == "unavailable"
    source.broken = False
    assert store.refresh()["status"] == "unavailable"
    from datetime import timedelta

    now[0] += timedelta(minutes=16)
    assert store.refresh()["status"] == "ok"


def test_concurrent_refresh_preserves_a_complete_snapshot(tmp_path):
    from concurrent.futures import ThreadPoolExecutor

    source = Publisher()
    stores = [type(setup(tmp_path)[2])(tmp_path, fetch=source) for _ in range(2)]
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(lambda store: store.refresh(), stores))
    assert all(result["status"] == "ok" for result in results)
    assert len(source.calls) == 3
    assert stores[0].current(2027)[1]["calendar"]["year"] == 2027
