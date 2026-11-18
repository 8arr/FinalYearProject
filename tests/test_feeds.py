import os
import sys

from google.transit import gtfs_realtime_pb2 as pb

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from collector import db, feeds  # noqa: E402

ROUTES = {"1 41C c a"}
STOPS = {"8240DB005029": {}, "8240DB005031": {}}


def make_trip_update(trip_id, route_id, stop_ids, delay=None):
    msg = pb.FeedMessage()
    msg.header.gtfs_realtime_version = "2.0"
    ent = msg.entity.add()
    ent.id = trip_id
    ent.trip_update.trip.trip_id = trip_id
    ent.trip_update.trip.route_id = route_id
    ent.trip_update.trip.start_date = "20261110"
    ent.trip_update.vehicle.id = "bus1"
    for seq, sid in enumerate(stop_ids, start=1):
        stu = ent.trip_update.stop_time_update.add()
        stu.stop_id = sid
        stu.stop_sequence = seq
        stu.arrival.time = 1_800_000_000 + seq * 60
        if delay is not None:
            stu.arrival.delay = delay
    return msg


def test_keeps_only_target_stops():
    msg = make_trip_update("t1", "1 41C c a", ["8240DB000001", "8240DB005029", "8240DB005031"], delay=120)
    rows = feeds.trip_update_rows(msg, ROUTES, STOPS, 1000)
    assert [r["stop_id"] for r in rows] == ["8240DB005029", "8240DB005031"]
    assert rows[0]["arrival_delay"] == 120
    assert rows[0]["departure_delay"] is None
    assert rows[0]["direction_id"] is None
    assert rows[0]["vehicle_id"] == "bus1"


def test_other_routes_are_dropped():
    msg = make_trip_update("t2", "1 16 c a", ["8240DB005029"])
    assert feeds.trip_update_rows(msg, ROUTES, STOPS, 1000) == []


def test_missing_route_id_is_kept():
    msg = make_trip_update("t3", "", ["8240DB005029"])
    rows = feeds.trip_update_rows(msg, ROUTES, STOPS, 1000)
    assert len(rows) == 1
    assert rows[0]["route_id"] is None
    assert rows[0]["arrival_delay"] is None


def test_vehicle_rows_and_insert():
    msg = pb.FeedMessage()
    msg.header.gtfs_realtime_version = "2.0"
    for i, route in enumerate(["1 41C c a", "1 16 c a"]):
        ent = msg.entity.add()
        ent.id = str(i)
        ent.vehicle.trip.trip_id = f"trip{i}"
        ent.vehicle.trip.route_id = route
        ent.vehicle.vehicle.id = f"bus{i}"
        ent.vehicle.position.latitude = 53.445
        ent.vehicle.position.longitude = -6.2345
        ent.vehicle.timestamp = 1_800_000_000

    rows = feeds.vehicle_rows(msg, ROUTES, 1000)
    assert len(rows) == 1
    assert rows[0]["vehicle_id"] == "bus0"
    assert rows[0]["speed"] is None

    conn = db.connect(":memory:")
    db.insert_rows(conn, "vehicle_positions", db.VEHICLE_COLS, rows)
    assert conn.execute("SELECT COUNT(*) FROM vehicle_positions").fetchone()[0] == 1


def test_route_id_format_change_still_matches():
    # TFI changed "1 41C c a" to "1_41C_c_a" in a new timetable and the collector kept nothing for days
    msg = make_trip_update("t4", "1_41C_c_a", ["8240DB005029"])
    assert len(feeds.trip_update_rows(msg, {"1 41C c a"}, STOPS, 1000)) == 1
    assert len(feeds.trip_update_rows(msg, {"1_41C_c_a"}, STOPS, 1000)) == 1

    vehicles = pb.FeedMessage()
    vehicles.header.gtfs_realtime_version = "2.0"
    ent = vehicles.entity.add()
    ent.id = "1"
    ent.vehicle.trip.route_id = "1_41C_c_a"
    assert len(feeds.vehicle_rows(vehicles, {"1 41C c a"}, 1000)) == 1


def test_route_ids_at_stops_reports_what_is_there():
    msg = make_trip_update("t5", "something new", ["8240DB005029", "8240DB000001"])
    assert dict(feeds.route_ids_at_stops(msg, STOPS)) == {"something new": 1}


def test_fetch_retries_when_the_api_says_slow_down(monkeypatch):
    import threading
    from http.server import BaseHTTPRequestHandler, HTTPServer

    body = make_trip_update("t6", "1 41C c a", ["8240DB005029"]).SerializeToString()
    hits = []

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            hits.append(1)
            self.send_response(429 if len(hits) == 1 else 200)
            self.send_header("Retry-After", "0")
            self.end_headers()
            if len(hits) > 1:
                self.wfile.write(body)

        def log_message(self, *args):
            pass

    server = HTTPServer(("127.0.0.1", 0), Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    try:
        msg = feeds.fetch_feed(f"http://127.0.0.1:{server.server_port}/x", "key")
    finally:
        server.shutdown()
    assert len(hits) == 2
    assert len(msg.entity) == 1


def test_fetch_gives_up_after_the_retries(monkeypatch):
    import threading
    from http.server import BaseHTTPRequestHandler, HTTPServer
    import requests

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            self.send_response(429)
            self.send_header("Retry-After", "0")
            self.end_headers()

        def log_message(self, *args):
            pass

    server = HTTPServer(("127.0.0.1", 0), Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    try:
        try:
            feeds.fetch_feed(f"http://127.0.0.1:{server.server_port}/x", "key", retries=1)
            raised = False
        except requests.HTTPError:
            raised = True
    finally:
        server.shutdown()
    assert raised
