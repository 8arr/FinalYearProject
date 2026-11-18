"""First look at a collected database: is the data there and does it look usable?

    python scripts/data_overview.py data/bus.db
"""
import os
import sqlite3
import sys
from datetime import datetime
from zoneinfo import ZoneInfo

TZ = ZoneInfo("Europe/Dublin")


def local(epoch):
    return datetime.fromtimestamp(epoch, TZ).strftime("%a %d %b %Y %H:%M")


def one(conn, sql, *args):
    return conn.execute(sql, args).fetchone()[0]


def filled(conn, table, columns):
    total = one(conn, f"SELECT COUNT(*) FROM {table}")
    print(f"  {'column':<22}{'filled':>10}{'share':>8}")
    for col in columns:
        n = one(conn, f"SELECT COUNT({col}) FROM {table}")
        share = f"{n / total:.0%}" if total else "n/a"
        print(f"  {col:<22}{n:>10}{share:>8}")


def main():
    path = sys.argv[1] if len(sys.argv) > 1 else os.path.join("data", "bus.db")
    conn = sqlite3.connect(f"file:{path}?mode=ro", uri=True)

    print(f"database: {path}\n")
    first, last = conn.execute("SELECT MIN(polled_at), MAX(polled_at) FROM polls").fetchone()
    if first is None:
        sys.exit("no polls in this database")
    print(f"collected from {local(first)} to {local(last)} ({(last - first) / 86400:.1f} days)\n")

    print("rows per table")
    for t in ("polls", "trip_updates", "vehicle_positions", "weather"):
        print(f"  {t:<20}{one(conn, f'SELECT COUNT(*) FROM {t}'):>10}")

    print("\npolls by feed (ok = request worked)")
    for feed, total, ok in conn.execute("SELECT feed, COUNT(*), SUM(ok) FROM polls GROUP BY feed"):
        print(f"  {feed:<14}{total:>8} polls, {ok / total:.1%} ok")

    print("\ntrip_updates, how much of each column is filled in")
    filled(conn, "trip_updates", ["arrival_time", "arrival_delay", "departure_time", "start_date",
                                  "start_time", "vehicle_id", "route_id"])
    print("\nvehicle_positions, how much of each column is filled in")
    filled(conn, "vehicle_positions", ["trip_id", "start_date", "position_time", "speed", "route_id"])

    print("\narrival_delay in minutes (what TFI says about lateness)")
    delays = [r[0] / 60 for r in conn.execute("SELECT arrival_delay FROM trip_updates WHERE arrival_delay IS NOT NULL")]
    if delays:
        delays.sort()
        n = len(delays)
        print(f"  lowest {delays[0]:.1f}, 10th percentile {delays[n // 10]:.1f}, median {delays[n // 2]:.1f}, "
              f"90th percentile {delays[9 * n // 10]:.1f}, highest {delays[-1]:.1f}")
    else:
        print("  none stored")

    print("\nper stop: trips seen")
    for stop, trips in conn.execute(
            "SELECT stop_id, COUNT(DISTINCT trip_id || start_date) FROM trip_updates GROUP BY stop_id"):
        print(f"  {stop:<16}{trips:>6} trips")

    print("\nper day (local date): trips seen at any stop, bus positions stored")
    days = {}
    for t, trip, start in conn.execute("SELECT polled_at, trip_id, start_date FROM trip_updates"):
        d = datetime.fromtimestamp(t, TZ).date()
        days.setdefault(d, [set(), 0])[0].add((trip, start))
    for t, in conn.execute("SELECT polled_at FROM vehicle_positions"):
        d = datetime.fromtimestamp(t, TZ).date()
        days.setdefault(d, [set(), 0])[1] += 1
    for d in sorted(days):
        print(f"  {d}  {len(days[d][0]):>5} trips  {days[d][1]:>7} positions")

    print("\nmost recent trip_updates rows")
    for row in conn.execute(
            "SELECT polled_at, trip_id, stop_id, arrival_time, arrival_delay FROM trip_updates "
            "ORDER BY polled_at DESC LIMIT 5"):
        at = local(row[3]) if row[3] else "none"
        print(f"  polled {local(row[0])}  trip {row[1]}  stop {row[2]}  due {at}  delay {row[4]}s")


if __name__ == "__main__":
    main()
