import pytest

from bus.arrivals import build_arrivals, feed_arrival, gps_arrival
from bus.simulate import SPEED

STOP = (53.445076, -6.234542)
BASE = 1_800_000_000


def track(arrive_at, times, offset_m=0.0, speed=SPEED):
    """Positions of a bus heading north that is level with the stop at arrive_at."""
    pts = []
    for t in times:
        along = speed * (t - arrive_at)
        pts.append((t, STOP[0] + along / 111_320, STOP[1] + offset_m / 68_000))
    return pts


def test_gps_arrival_is_interpolated_between_polls():
    # polls every 60s never land on the stop, the answer has to come from between them
    pts = track(BASE + 30, range(BASE - 600, BASE + 600, 60))
    assert gps_arrival(pts, STOP) == pytest.approx(BASE + 30, abs=1)


def test_gps_arrival_ignores_a_bus_that_passes_too_far_away():
    pts = track(BASE, range(BASE - 600, BASE + 600, 60), offset_m=100)
    assert gps_arrival(pts, STOP) is None


def test_gps_arrival_with_no_points():
    assert gps_arrival([], STOP) is None


def test_gps_arrival_does_not_trust_a_long_gap_in_the_track():
    pts = track(BASE, [BASE - 600, BASE - 300, BASE + 300, BASE + 600])
    assert gps_arrival(pts, STOP) is None


def test_gps_arrival_when_bus_is_already_at_the_stop():
    pts = [(BASE, STOP[0], STOP[1]), (BASE + 60, STOP[0] + 0.0001, STOP[1])]
    assert gps_arrival(pts, STOP) == BASE


def test_feed_arrival_is_a_minute_before_it_disappeared():
    assert feed_arrival(last_seen=1000, due_time=1030, next_poll=1060, interval=60) == 1000


def test_feed_arrival_unknown_when_collector_was_down():
    assert feed_arrival(last_seen=1000, due_time=1030, next_poll=1000 + 3600, interval=60) is None
    assert feed_arrival(last_seen=1000, due_time=1030, next_poll=None, interval=60) is None


def test_feed_arrival_ignores_trips_dropped_while_still_far_away():
    # the stop vanished while TFI still said 30 minutes, that is a cancellation not an arrival
    assert feed_arrival(last_seen=1000, due_time=1000 + 1800, next_poll=1060, interval=60) is None


def test_simulated_arrivals_match_the_known_answers(sim, stops):
    conn, truth = sim
    arrivals = build_arrivals(conn, stops)
    assert len(arrivals) == len(truth)

    gps_errors = [a.gps_time - truth[(a.trip_id, a.start_date)] for a in arrivals]
    assert max(abs(e) for e in gps_errors) < 6


def test_feed_method_is_late_on_average_because_due_lingers(sim, stops):
    conn, truth = sim
    arrivals = build_arrivals(conn, stops)
    errors = [a.feed_time - truth[(a.trip_id, a.start_date)] for a in arrivals if a.feed_time]
    assert len(errors) == len(arrivals)
    mean = sum(errors) / len(errors)
    assert 20 < mean < 80
    assert max(errors) < 200


def test_missing_polls_remove_feed_estimate_but_not_gps(stops):
    from tests.conftest import make_db
    conn, truth = make_db(days=1, seed=3)
    (trip_id, start_date), actual = sorted(truth.items(), key=lambda kv: kv[1])[10]
    conn.execute("DELETE FROM polls WHERE feed='trip_updates' AND polled_at > ? AND polled_at < ?",
                 (actual - 120, actual + 900))
    arrivals = {a.trip_id: a for a in build_arrivals(conn, stops)}
    assert arrivals[trip_id].feed_time is None
    assert arrivals[trip_id].gps_time == pytest.approx(actual, abs=6)


def test_cancelled_trip_has_no_arrival(stops):
    from tests.conftest import make_db
    conn, truth = make_db(days=1, seed=3)
    (trip_id, start_date), actual = sorted(truth.items(), key=lambda kv: kv[1])[10]
    conn.execute("DELETE FROM vehicle_positions WHERE trip_id = ?", (trip_id,))
    conn.execute("DELETE FROM trip_updates WHERE trip_id = ? AND polled_at > ?", (trip_id, actual - 1800))
    arrival = {a.trip_id: a for a in build_arrivals(conn, stops)}[trip_id]
    assert arrival.gps_time is None
    assert arrival.feed_time is None
