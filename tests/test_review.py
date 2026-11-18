import sqlite3
import threading
import urllib.parse
import urllib.request
from http.server import HTTPServer

import pytest

from bus import review
from collector import db
from tests.conftest import STOPS
from bus import simulate


def test_describe_error():
    assert review.describe_error(1002, 1000) == "spot on"
    assert review.describe_error(1090, 1000) == "1 min 30 s late"
    assert review.describe_error(950, 1000) == "50 s early"


@pytest.fixture
def sim_copy(sim):
    """Review tests write to the database, so give them their own copy."""
    copy = sqlite3.connect(":memory:")
    sim[0].backup(copy)
    return copy


def test_reviews_are_saved_and_summarised():
    conn = sqlite3.connect(":memory:")
    review.ensure_table(conn)
    assert review.review_summary(conn)["agreement"] is None
    review.record_review(conn, ("t1", "20261102", "s"), 30, True)
    review.record_review(conn, ("t2", "20261102", "s"), 30, False, "gps jumped")
    summary = review.review_summary(conn)
    assert summary == {"reviewed": 2, "agreed": 1, "agreement": 0.5}


def test_cases_have_tfi_model_and_actual_and_skip_reviewed(sim_copy):
    conn = sim_copy
    cases = review.build_cases(conn, STOPS, 30, limit=5)
    assert len(cases) == 5
    c = cases[0]
    assert c["model"] is not None and c["tfi"] and c["actual"]

    review.record_review(conn, c["key"], 30, True)
    again = review.build_cases(conn, STOPS, 30, limit=500)
    assert c["key"] not in [x["key"] for x in again]


def test_case_page_shows_what_a_person_needs(sim_copy):
    conn = sim_copy
    case = review.build_cases(conn, STOPS, 30, limit=1)[0]
    page = review.render_case(conn, case, 1, 1, 30)
    for text in ("Boroimhe Laurels", "Detected arrival", "TFI said", "Model said",
                 "Looks right", "Looks wrong", "<svg"):
        assert text in page


def test_web_flow_saves_an_answer(tmp_path):
    path = str(tmp_path / "sim.db")
    simulate.simulate(db.connect(path), days=10)
    conn = sqlite3.connect(path, check_same_thread=False)
    review.ensure_table(conn)
    cases = review.build_cases(conn, STOPS, 30, limit=2)

    server = HTTPServer(("127.0.0.1", 0), review.make_handler(conn, cases, 30))
    threading.Thread(target=server.serve_forever, daemon=True).start()
    base = f"http://127.0.0.1:{server.server_port}"
    try:
        assert "Case 1 of 2" in urllib.request.urlopen(base + "/").read().decode()
        body = urllib.parse.urlencode({"answer": "yes", "note": "fine"}).encode()
        page = urllib.request.urlopen(base + "/review", body).read().decode()
        assert "Case 2 of 2" in page
        urllib.request.urlopen(base + "/review", urllib.parse.urlencode({"answer": "skip"}).encode())
        assert "All done" in urllib.request.urlopen(base + "/").read().decode()
        assert review.review_summary(conn)["reviewed"] == 1
    finally:
        server.shutdown()
