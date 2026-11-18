"""Whole chain test: a fake NTA server, the real collector code, the
database, arrival detection, evaluation inputs and the live estimate.

The fake bus reaches the stop at a time we choose, so the right answer is known.
"""
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

import pytest
from google.transit import gtfs_realtime_pb2 as pb

from bus import health, predict
from bus.arrivals import build_arrivals
from bus.fallback import HistoryEstimate
from bus.simulate import ROUTE_ID, SPEED, STOP
from collector import config, db, feeds, run

ARRIVES_AT = 1_800_000_000 + 40 * 60
SCHEDULED = ARRIVES_AT - 120
START_DATE = "20261110"
LAT0 = STOP["lat"]
LON0 = STOP["lon"]


class FakeNta:
    """Serves the feeds as they would look at self.now."""

    def __init__(self):
        self.now = 0
        self.down = False

    def feed(self, kind):
        msg = pb.FeedMessage()
        msg.header.gtfs_realtime_version = "2.0"
        msg.header.timestamp = self.now
        ent = msg.entity.add()
        ent.id = "1"
        if kind == "TripUpdates":
            if self.now > ARRIVES_AT:
                return msg  # the stop drops out once the bus has gone
            tu = ent.trip_update
            tu.trip.trip_id, tu.trip.route_id, tu.trip.start_date = "trip1", ROUTE_ID, START_DATE
            tu.trip.start_time = "10:00:00"
            stu = tu.stop_time_update.add()
            stu.stop_id = STOP["stop_id"]
            stu.arrival.time = SCHEDULED
            stu.arrival.delay = 0
        else:
            v = ent.vehicle
            v.trip.trip_id, v.trip.route_id, v.trip.start_date = "trip1", ROUTE_ID, START_DATE
            v.vehicle.id = "bus1"
            v.position.latitude = LAT0 + SPEED * (self.now - ARRIVES_AT) / 111_320
            v.position.longitude = LON0
            v.timestamp = self.now
        return msg


@pytest.fixture
def nta():
    fake = FakeNta()

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            if fake.down:
                self.send_response(503)
                self.end_headers()
                return
            body = fake.feed(self.path.strip("/")).SerializeToString()
            self.send_response(200)
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, *args):
            pass

    server = HTTPServer(("127.0.0.1", 0), Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    base = f"http://127.0.0.1:{server.server_port}"
    old = (config.TRIP_UPDATES_URL, config.VEHICLES_URL)
    config.TRIP_UPDATES_URL, config.VEHICLES_URL = f"{base}/TripUpdates", f"{base}/Vehicles"
    fake.url = config.TRIP_UPDATES_URL
    yield fake
    config.TRIP_UPDATES_URL, config.VEHICLES_URL = old
    server.shutdown()


def poll_through(nta, conn, start, end, step=60):
    stops = {STOP["stop_id"]: STOP}
    for t in range(start, end, step):
        nta.now = t
        run.poll_trip_updates(conn, "key", {ROUTE_ID}, stops, t)
        run.poll_vehicles(conn, "key", {ROUTE_ID}, t)
    conn.commit()


def test_collected_data_gives_the_right_arrival(nta):
    conn = db.connect(":memory:")
    poll_through(nta, conn, ARRIVES_AT - 45 * 60, ARRIVES_AT + 10 * 60)

    arrivals = build_arrivals(conn, {STOP["stop_id"]: STOP})
    assert len(arrivals) == 1
    a = arrivals[0]
    assert a.gps_time == pytest.approx(ARRIVES_AT, abs=3)
    # the stop vanished at the first poll after ARRIVES_AT, the feed method takes a minute off that
    assert ARRIVES_AT - 60 <= a.feed_time <= ARRIVES_AT + 60
    issues, _ = health.check_database(conn, now=ARRIVES_AT + 700)
    assert not health.has_errors(issues)


def test_live_estimate_from_the_fake_feed(nta):
    nta.now = ARRIVES_AT - 1800
    result = predict.estimate_next(
        STOP["stop_id"], lambda: feeds.fetch_feed(nta.url, "key"),
        lambda now, n: [], now=nta.now, route_ids={ROUTE_ID})
    assert result.source == "tfi"
    assert result.estimates[0].time == SCHEDULED


def test_tfi_outage_does_not_stop_the_estimate(nta):
    nta.now = ARRIVES_AT - 1800
    nta.down = True

    def history(now, n):
        return [HistoryEstimate(ARRIVES_AT, "10:00:00", 8, 2.0)]

    result = predict.estimate_next(
        STOP["stop_id"], lambda: feeds.fetch_feed(nta.url, "key"), history, now=nta.now)
    assert result.source == "history"
    assert result.estimates[0].time == ARRIVES_AT


def test_collector_records_failures_and_keeps_going(nta):
    conn = db.connect(":memory:")
    nta.down = True
    poll_through(nta, conn, ARRIVES_AT - 600, ARRIVES_AT - 300)
    nta.down = False
    poll_through(nta, conn, ARRIVES_AT - 300, ARRIVES_AT - 120)

    failed, ok = (conn.execute(f"SELECT COUNT(*) FROM polls WHERE ok={v}").fetchone()[0] for v in (0, 1))
    assert failed == 10 and ok == 6
    assert conn.execute("SELECT COUNT(*) FROM trip_updates").fetchone()[0] == 3
