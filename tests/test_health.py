from google.transit import gtfs_realtime_pb2 as pb

from bus import health
from collector import db

NOW = 1_800_000_000


def trip_feed(timestamp=NOW, delays=(60,), arrival_offset=600, route="1 41C c a"):
    msg = pb.FeedMessage()
    msg.header.gtfs_realtime_version = "2.0"
    msg.header.timestamp = timestamp
    for i, d in enumerate(delays):
        ent = msg.entity.add()
        ent.id = str(i)
        ent.trip_update.trip.trip_id = f"t{i}"
        ent.trip_update.trip.route_id = route
        stu = ent.trip_update.stop_time_update.add()
        stu.stop_id = "s"
        stu.arrival.delay = d
        stu.arrival.time = NOW + arrival_offset
    return msg


def vehicle_feed(lat, lon, timestamp=NOW):
    msg = pb.FeedMessage()
    msg.header.gtfs_realtime_version = "2.0"
    msg.header.timestamp = timestamp
    ent = msg.entity.add()
    ent.id = "1"
    ent.vehicle.trip.route_id = "1 41C c a"
    ent.vehicle.position.latitude = lat
    ent.vehicle.position.longitude = lon
    return msg


def texts(issues):
    return " | ".join(i.text for i in issues)


def test_healthy_feed_has_no_issues():
    assert health.check_feed(trip_feed(), NOW, route_ids={"1 41C c a"}) == []


def test_empty_feed_is_an_error():
    msg = pb.FeedMessage()
    msg.header.gtfs_realtime_version = "2.0"
    issues = health.check_feed(msg, NOW)
    assert health.has_errors(issues)


def test_stale_feed_is_an_error():
    issues = health.check_feed(trip_feed(timestamp=NOW - 3600), NOW)
    assert health.has_errors(issues)
    assert "stale" in texts(issues)


def test_feed_timestamp_in_the_future_is_an_error():
    assert health.has_errors(health.check_feed(trip_feed(timestamp=NOW + 3600), NOW))


def test_mostly_absurd_delays_are_an_error_but_one_is_a_warning():
    many = health.check_feed(trip_feed(delays=[99999, 99999, 60]), NOW)
    assert health.has_errors(many)
    one = health.check_feed(trip_feed(delays=[99999] + [60] * 19), NOW)
    assert not health.has_errors(one) and one


def test_arrival_times_far_in_the_past_are_flagged():
    issues = health.check_feed(trip_feed(arrival_offset=-86400), NOW)
    assert health.has_errors(issues)


def test_missing_route_is_only_a_warning():
    issues = health.check_feed(trip_feed(route="1 16 c a"), NOW, route_ids={"1 41C c a"})
    assert issues and not health.has_errors(issues)


def test_vehicle_in_the_atlantic_is_flagged():
    assert health.check_feed(vehicle_feed(53.44, -6.23), NOW, "vehicles") == []
    assert health.has_errors(health.check_feed(vehicle_feed(0.0, 0.0), NOW, "vehicles"))


def test_database_check_on_good_data(sim):
    conn, _ = sim
    issues, stats = health.check_database(conn, now=NOW)
    assert not health.has_errors(issues)
    assert stats["largest_gap_min"] <= 1


def test_database_check_notices_gaps_and_failed_polls():
    conn = db.connect(":memory:")
    for t in range(0, 600, 60):
        db.log_poll(conn, t, "trip_updates", True)
    for t in range(4000, 4600, 60):
        db.log_poll(conn, t, "trip_updates", True)
    for t in range(600, 4000, 600):
        db.log_poll(conn, t, "trip_updates", False, error="timeout")
    conn.execute("INSERT INTO trip_updates (polled_at, trip_id, stop_id, arrival_delay) VALUES (1,'t','s',90000)")
    issues, stats = health.check_database(conn, now=5000)
    assert "gaps" in texts(issues)
    assert "failed" in texts(issues)
    assert stats["implausible_delays"] == 1


def test_empty_database_is_an_error():
    issues, _ = health.check_database(db.connect(":memory:"), now=NOW)
    assert health.has_errors(issues)
