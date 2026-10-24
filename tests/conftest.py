import pytest

from sg_deadline import load_calendar, load_limitation_rules, load_rules


@pytest.fixture(scope="session")
def cal():
    return load_calendar("SG")


@pytest.fixture(scope="session")
def rules():
    return load_rules()


@pytest.fixture(scope="session")
def limitation_rules():
    return load_limitation_rules()


@pytest.fixture(autouse=True)
def isolated_calendar_environment(monkeypatch, tmp_path):
    monkeypatch.setenv("SG_DEADLINE_OFFLINE", "1")
    monkeypatch.setenv("SG_DEADLINE_CACHE", str(tmp_path / "calendar-cache"))
