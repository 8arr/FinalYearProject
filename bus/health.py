"""Checks that tell us whether data from TFI looks sane.

Used on the live feed before trusting it, and on the stored data before
running any tests on it, so a TFI fault does not get mistaken for a bug
in this project (or the other way round).
"""
import time
from dataclasses import dataclass

STALE_AFTER_S = 5 * 60
MAX_FUTURE_S = 2 * 60
MAX_DELAY_S = 3 * 3600
MAX_ARRIVAL_AHEAD_S = 24 * 3600
MAX_ARRIVAL_BEHIND_S = 3600
IRELAND = (51.2, 55.6, -10.9, -5.2)  # south, north, west, east
MAX_BAD_SHARE = 0.10


@dataclass
class Issue:
    level: str  # "error" or "warning"
    text: str


def has_errors(issues):
    return any(i.level == "error" for i in issues)


def check_feed(msg, now=None, kind="trip_updates", route_ids=None):
    now = now if now is not None else time.time()
    issues = []

    if len(msg.entity) == 0:
        issues.append(Issue("error", "feed has no entities"))
        return issues

    ts = msg.header.timestamp
    if not ts:
        issues.append(Issue("error", "feed has no timestamp"))
    elif now - ts > STALE_AFTER_S:
        issues.append(Issue("error", f"feed is stale, last updated {int(now - ts)}s ago"))
    elif ts - now > MAX_FUTURE_S:
        issues.append(Issue("error", f"feed timestamp is {int(ts - now)}s in the future"))

    if kind == "trip_updates":
        issues += _check_trip_updates(msg, now)
    else:
        issues += _check_vehicles(msg)

    if route_ids:
        found = {e.trip_update.trip.route_id for e in msg.entity if e.HasField("trip_update")}
        found |= {e.vehicle.trip.route_id for e in msg.entity if e.HasField("vehicle")}
        if not found & set(route_ids):
            issues.append(Issue("warning", "nothing in the feed for our route (may just be night time)"))
    return issues


def _share_issue(bad, total, what):
    if total == 0 or bad == 0:
        return []
    level = "error" if bad / total > MAX_BAD_SHARE else "warning"
    return [Issue(level, f"{bad} of {total} {what}")]


def _check_trip_updates(msg, now):
    bad = total = 0
    for ent in msg.entity:
        if not ent.HasField("trip_update"):
            continue
        for stu in ent.trip_update.stop_time_update:
            if not stu.HasField("arrival"):
                continue
            total += 1
            a = stu.arrival
            if abs(a.delay) > MAX_DELAY_S or (
                    a.time and not now - MAX_ARRIVAL_BEHIND_S < a.time < now + MAX_ARRIVAL_AHEAD_S):
                bad += 1
    return _share_issue(bad, total, "predicted arrivals have an implausible time or delay")


def _check_vehicles(msg):
    south, north, west, east = IRELAND
    bad = total = 0
    for ent in msg.entity:
        if not ent.HasField("vehicle"):
            continue
        total += 1
        p = ent.vehicle.position
        if not (south <= p.latitude <= north and west <= p.longitude <= east):
            bad += 1
    return _share_issue(bad, total, "vehicle positions are outside Ireland")


def check_database(conn, interval=60, now=None, window_s=24 * 3600):
    """Quality report for what the collector has stored.

    Returns (issues, stats). Gaps in collection are warnings because they
    just mean fewer usable samples.
    """
    now = now if now is not None else time.time()
    issues = []
    stats = {}

    total = conn.execute("SELECT COUNT(*) FROM polls").fetchone()[0]
    if total == 0:
        return [Issue("error", "no polls recorded yet")], stats

    rows = conn.execute(
        "SELECT polled_at, ok FROM polls WHERE feed='trip_updates' ORDER BY polled_at").fetchall()
    ok_times = [t for t, ok in rows if ok]
    stats["polls"] = len(rows)
    stats["failed_polls"] = len(rows) - len(ok_times)
    if rows:
        stats["failure_rate"] = stats["failed_polls"] / len(rows)
        if stats["failure_rate"] > 0.05:
            issues.append(Issue("warning", f"{stats['failure_rate']:.0%} of polls failed"))

    gaps = [b - a for a, b in zip(ok_times, ok_times[1:])]
    big = [g for g in gaps if g > 5 * interval]
    stats["largest_gap_min"] = max(gaps, default=0) / 60
    if big:
        issues.append(Issue("warning", f"{len(big)} gaps longer than {5 * interval // 60} min "
                                       f"(largest {stats['largest_gap_min']:.0f} min)"))

    last = ok_times[-1] if ok_times else None
    if last is not None and now - last > window_s:
        issues.append(Issue("warning", f"last good poll was {(now - last) / 3600:.0f}h ago"))

    bad_delays = conn.execute(
        "SELECT COUNT(*) FROM trip_updates WHERE ABS(arrival_delay) > ?", (MAX_DELAY_S,)).fetchone()[0]
    stats["implausible_delays"] = bad_delays
    if bad_delays:
        issues.append(Issue("warning", f"{bad_delays} stored delays are over {MAX_DELAY_S // 3600} hours"))

    if conn.execute("SELECT COUNT(*) FROM trip_updates").fetchone()[0] == 0:
        issues.append(Issue("error", "no trip updates stored"))
    return issues, stats
