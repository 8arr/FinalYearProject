"""Work out when buses really arrived at a stop.

The feed only gives predictions, so the real arrival time has to be
reconstructed afterwards. Two methods are used so they can be compared:

gps   the bus position is interpolated between polls and the time it was
      closest to the stop is used (as long as that is within `radius` metres)
feed  the time the stop disappeared from the feed, minus a minute
"""
from collections import defaultdict
from dataclasses import dataclass

from .geo import closest_on_segment, distance_m

RADIUS_M = 25
MAX_GPS_GAP_S = 180
FEED_OFFSET_S = 60
# if the stop vanished while the bus was still further away than this
# it was probably cancelled or dropped from the feed, not a real arrival
MAX_DUE_WHEN_GONE_S = 5 * 60


@dataclass
class Arrival:
    trip_id: str
    start_date: str
    start_time: str
    stop_id: str
    gps_time: float = None
    feed_time: float = None

    def actual(self, truth="best"):
        if truth == "gps":
            return self.gps_time
        if truth == "feed":
            return self.feed_time
        return self.gps_time if self.gps_time is not None else self.feed_time


def gps_arrival(points, stop, radius=RADIUS_M, max_gap=MAX_GPS_GAP_S):
    """points: (time, lat, lon) sorted by time. stop: (lat, lon).

    Returns the estimated arrival time or None if the bus never got
    within `radius` metres of the stop.
    """
    if not points:
        return None

    first = points[0]
    if distance_m(stop[0], stop[1], first[1], first[2]) <= radius:
        return first[0]

    for (t0, la0, lo0), (t1, la1, lo1) in zip(points, points[1:]):
        if t1 - t0 > max_gap:
            # too long since the last fix to trust a straight line between them
            if distance_m(stop[0], stop[1], la1, lo1) <= radius:
                return t1
            continue
        dist, frac = closest_on_segment((la0, lo0), (la1, lo1), stop)
        if dist <= radius:
            return t0 + frac * (t1 - t0)
    return None


def feed_arrival(last_seen, due_time, next_poll, interval, offset=FEED_OFFSET_S):
    """Arrival estimate from the stop disappearing from the feed.

    last_seen is the last poll that listed the stop, due_time the prediction
    in that poll and next_poll the first good poll after it.
    """
    if next_poll is None or next_poll - last_seen > 2.5 * interval:
        return None  # collector was down, cannot tell when it vanished
    if due_time is not None and due_time - last_seen > MAX_DUE_WHEN_GONE_S:
        return None
    return next_poll - offset


def build_arrivals(conn, stops, interval=60, radius=RADIUS_M, since=None):
    """stops: dict of stop_id to {lat, lon}. Returns a list of Arrival."""
    marks = ",".join("?" * len(stops))
    sql = (
        "SELECT trip_id, start_date, start_time, stop_id, polled_at, arrival_time"
        f" FROM trip_updates WHERE stop_id IN ({marks})"
    )
    args = list(stops)
    if since is not None:
        sql += " AND polled_at >= ?"
        args.append(since)
    sql += " ORDER BY polled_at"

    seen = {}
    for trip_id, start_date, start_time, stop_id, polled_at, arr in conn.execute(sql, args):
        key = (trip_id, start_date, stop_id)
        if key not in seen:
            seen[key] = {"start_time": start_time, "last": polled_at, "due": arr}
        else:
            seen[key]["last"] = polled_at
            seen[key]["due"] = arr

    good_polls = [r[0] for r in conn.execute(
        "SELECT polled_at FROM polls WHERE feed='trip_updates' AND ok=1 ORDER BY polled_at")]

    tracks = defaultdict(list)
    for trip_id, start_date, t, polled, lat, lon in conn.execute(
            "SELECT trip_id, start_date, position_time, polled_at, lat, lon FROM vehicle_positions"
            " WHERE trip_id IS NOT NULL ORDER BY polled_at"):
        tracks[(trip_id, start_date)].append((t or polled, lat, lon))

    arrivals = []
    for (trip_id, start_date, stop_id), info in seen.items():
        stop = (stops[stop_id]["lat"], stops[stop_id]["lon"])
        pts = sorted(set(tracks.get((trip_id, start_date), [])))
        nxt = _first_after(good_polls, info["last"])
        arrivals.append(Arrival(
            trip_id=trip_id,
            start_date=start_date,
            start_time=info["start_time"],
            stop_id=stop_id,
            gps_time=gps_arrival(pts, stop, radius),
            feed_time=feed_arrival(info["last"], info["due"], nxt, interval),
        ))
    return arrivals


def _first_after(sorted_times, value):
    from bisect import bisect_right
    i = bisect_right(sorted_times, value)
    return sorted_times[i] if i < len(sorted_times) else None
