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
