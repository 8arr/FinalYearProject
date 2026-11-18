"""Make fake but realistic data with known answers.

The simulated bus follows a straight road past the stop at a constant
speed, so the true arrival time of every trip is known exactly. The
simulated TFI feed only knows about delays shortly before arrival, while
the real delay depends on the hour of day and on rain. That gives the
tests something definite to find (or not find when effects are switched off).

    python -m bus.simulate data/sim.db --days 14
"""
import argparse
import math
import random
from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo

from collector import db
from .schedule import service_day_start

TZ = ZoneInfo("Europe/Dublin")
STOP = {"stop_id": "8240DB005029", "stop_code": "5029", "name": "Boroimhe Laurels",
        "lat": 53.445076, "lon": -6.234542}
ROUTE_ID = "1 41C c a"
SPEED = 7.0  # m/s
TFI_KNOWS_DELAY_FROM_S = 40 * 60
POLL_SECONDS = 60


def local_epoch(day, hour, minute=0):
    return int(datetime.combine(day, time(hour, minute), tzinfo=TZ).timestamp())


def true_delay(rng, hour, weekend, raining, effects):
    if not effects:
        return rng.gauss(0, 60)
    peak = hour in (7, 8, 16, 17, 18)
    delay = 240 if peak else 30
    if weekend:
        delay *= 0.5
    if raining:
        delay += 90
    return delay + rng.gauss(0, 45)


def simulate(conn, days=10, seed=1, first_day=date(2026, 11, 2), effects=True, delay_only=False,
             linger_choices=(0, 60, 120, 180)):
    """Fills the tables and returns {(trip_id, start_date): true arrival epoch}.

    delay_only copies the real feed, which mostly sends delays and no clock
    times, with the timetable in the schedule table instead. linger_choices
    are how many seconds the stop stays in the feed after the bus has gone,
    on the real feed it was 10 to 45 minutes.
    """
    rng = random.Random(seed)
    lat0, lon0 = STOP["lat"], STOP["lon"]
    road_lon = lon0 - 8 / (111_320 * math.cos(math.radians(lat0)))
    truth = {}
    trip_rows, vehicle_rows, polls, weather, schedule = [], [], [], [], []

    for d in range(days):
        day = first_day + timedelta(days=d)
        weekend = day.weekday() >= 5
        start_date = day.strftime("%Y%m%d")
        raining = {h: rng.random() < 0.25 for h in range(24)}

        first_poll = local_epoch(day, 0, 0)
        for t in range(first_poll, first_poll + 24 * 3600, POLL_SECONDS):
            polls.append({"polled_at": t, "feed": "trip_updates"})
            polls.append({"polled_at": t, "feed": "vehicles"})
            if t % 600 < POLL_SECONDS:
                hour = datetime.fromtimestamp(t, TZ).hour
                weather.append({
                    "polled_at": t,
                    "temperature_c": 9 + rng.gauss(0, 1),
                    "precipitation_mm": 1.2 if raining[hour] else 0.0,
                    "rain_mm": 1.2 if raining[hour] else 0.0,
                    "wind_kmh": abs(rng.gauss(15, 5)),
                    "weather_code": 61 if raining[hour] else 3,
                })

        for slot in range(6 * 3, 23 * 3):
            hour, minute = divmod(slot * 20, 60)
            scheduled = local_epoch(day, hour, minute)
            delay = true_delay(rng, hour, weekend, raining[hour], effects)
            actual = scheduled + delay
            trip_id = f"sim_{start_date}_{slot}"
            start_time = datetime.fromtimestamp(scheduled - 35 * 60, TZ).strftime("%H:%M:%S")
            truth[(trip_id, start_date)] = actual
            schedule.append((trip_id, STOP["stop_id"], 30, round(scheduled - service_day_start(start_date))))
            linger = rng.choice(linger_choices)

            t = (int(actual) - 75 * 60) // POLL_SECONDS * POLL_SECONDS + 7
            while t <= actual + linger:
                if t <= actual:
                    known = min(1, max(0, 1 - (actual - t) / TFI_KNOWS_DELAY_FROM_S)) if effects else 0
                else:
                    known = 1
                tfi_delay = round(known * delay + (rng.gauss(0, 20) if effects else 0))
                trip_rows.append({
                    "polled_at": t, "trip_id": trip_id, "route_id": ROUTE_ID, "direction_id": 0,
                    "start_date": start_date, "start_time": start_time, "vehicle_id": f"bus_{slot}",
                    "stop_id": STOP["stop_id"], "stop_sequence": 30,
                    "arrival_time": None if delay_only else scheduled + tfi_delay, "arrival_delay": tfi_delay,
                    "departure_time": None, "departure_delay": None, "schedule_relationship": "SCHEDULED",
                })
                t += POLL_SECONDS

            t = (int(actual) - 40 * 60) // POLL_SECONDS * POLL_SECONDS + 7
            while t <= actual + 10 * 60:
                along = SPEED * (t - actual)
                vehicle_rows.append({
                    "polled_at": t, "vehicle_id": f"bus_{slot}", "trip_id": trip_id,
                    "route_id": ROUTE_ID, "direction_id": 0, "start_date": start_date,
                    "start_time": start_time,
                    "lat": lat0 + (along + rng.gauss(0, 4)) / 111_320,
                    "lon": road_lon + rng.gauss(0, 4) / (111_320 * math.cos(math.radians(lat0))),
                    "bearing": 0.0, "speed": SPEED, "position_time": t,
                    "current_stop_sequence": 30, "stop_id": STOP["stop_id"],
                    "current_status": "IN_TRANSIT_TO",
                })
                t += POLL_SECONDS

    for p in polls:
        db.log_poll(conn, p["polled_at"], p["feed"], True)
    db.insert_rows(conn, "trip_updates", db.TRIP_UPDATE_COLS, trip_rows)
    db.insert_rows(conn, "vehicle_positions", db.VEHICLE_COLS, vehicle_rows)
    db.insert_rows(conn, "weather", db.WEATHER_COLS, weather)
    if delay_only:
        conn.executemany("INSERT INTO schedule (trip_id, stop_id, stop_sequence, arrival_s) VALUES (?,?,?,?)", schedule)
    conn.commit()
    return truth


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("path")
    ap.add_argument("--days", type=int, default=14)
    ap.add_argument("--seed", type=int, default=1)
    ap.add_argument("--no-effects", action="store_true")
    ap.add_argument("--delay-only", action="store_true", help="like the real feed, delays but no clock times")
    args = ap.parse_args()
    conn = db.connect(args.path)
    simulate(conn, args.days, args.seed, effects=not args.no_effects, delay_only=args.delay_only)
    print(f"wrote {args.path}")


if __name__ == "__main__":
    main()
