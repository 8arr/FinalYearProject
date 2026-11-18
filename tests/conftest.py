import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from collector import db  # noqa: E402
from bus import simulate  # noqa: E402

STOPS = {simulate.STOP["stop_id"]: simulate.STOP}
STOP_ID = simulate.STOP["stop_id"]


def make_db(**kwargs):
    conn = db.connect(":memory:")
    truth = simulate.simulate(conn, **kwargs)
    return conn, truth


@pytest.fixture(autouse=True)
def no_retry_waiting(monkeypatch):
    """The feed fetch waits a few seconds between retries, not in tests."""
    monkeypatch.setattr("collector.feeds.time.sleep", lambda s: None)


@pytest.fixture(scope="session")
def sim():
    """Two weeks of data where hour of day and rain really do change delays."""
    return make_db(days=14, seed=1)


@pytest.fixture(scope="session")
def sim_noise():
    """Two weeks where there is nothing to learn, TFI is as good as it gets."""
    return make_db(days=14, seed=1, effects=False)


@pytest.fixture
def stops():
    return STOPS
