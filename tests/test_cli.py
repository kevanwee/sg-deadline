import json

from sg_deadline.cli import main


def test_compute_json(capsys):
    rc = main(["--json", "compute", "sg.roc2021.defence", "2026-03-13"])
    assert rc == 0
    out = json.loads(capsys.readouterr().out)
    assert out["deadline"] == "2026-04-06"


def test_unknown_rule(capsys):
    assert main(["compute", "sg.nope", "2026-03-13"]) == 2


def test_rules_list(capsys):
    assert main(["rules"]) == 0
    assert "sg.roc2021.defence" in capsys.readouterr().out


def test_missing_holiday_year_exit_code(capsys):
    assert main(["compute", "sg.roc2021.defence", "2031-03-13"]) == 3
