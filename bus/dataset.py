"""Turn arrivals into training and test rows.

For each arrival we find the moment TFI was saying the bus was `horizon`
minutes away, and keep what it predicted then along with things we could
have known at that point (time of day, weather). The moment is picked from
what TFI said, not from when the bus actually arrived, otherwise the real
arrival time would leak into the inputs.
"""
from bisect import bisect_left
from collections import defaultdict
from datetime import datetime

from . import schedule as schedule_mod
from .schedule import TZ

POLL_TOLERANCE_S = 120
WEATHER_MAX_AGE_S = 30 * 60


def local_hour(epoch):
    dt = datetime.fromtimestamp(epoch, TZ)
    return dt.hour + dt.minute / 60


def is_weekend(epoch):
    return datetime.fromtimestamp(epoch, TZ).weekday() >= 5


def _load_predictions(conn, stop_ids):
    marks = ",".join("?" * len(stop_ids))
    sched = schedule_mod.load(conn)
    rows = conn.execute(
        "SELECT trip_id, start_date, stop_id, polled_at, arrival_time, arrival_delay"
        f" FROM trip_updates WHERE stop_id IN ({marks}) ORDER BY polled_at", list(stop_ids))
    preds = defaultdict(list)
    for trip_id, start_date, stop_id, polled_at, arrival_time, delay in rows:
        due = schedule_mod.predicted_time(arrival_time, delay, start_date, sched.get((trip_id, stop_id)))
        if due is not None:
            preds[(trip_id, start_date, stop_id)].append((polled_at, due, delay))
    return preds


def _load_weather(conn):
    rows = conn.execute(
        "SELECT polled_at, rain_mm, wind_kmh FROM weather ORDER BY polled_at").fetchall()
    return [r[0] for r in rows], rows


def _weather_at(times, rows, t):
    i = bisect_left(times, t + 1) - 1
    if i < 0 or t - times[i] > WEATHER_MAX_AGE_S:
        return 0.0, 0.0
    return rows[i][1] or 0.0, rows[i][2] or 0.0


def build_samples(conn, arrivals, stop_ids, horizon_min, truth="gps"):
    """One sample per arrival that has both a known arrival time and a
    TFI prediction from about `horizon_min` minutes earlier."""
    preds = _load_predictions(conn, stop_ids)
    w_times, w_rows = _load_weather(conn)
    samples = []

    for a in arrivals:
        actual = a.actual(truth)
        if actual is None:
            continue
        series = preds.get((a.trip_id, a.start_date, a.stop_id))
        if not series:
            continue
        target = horizon_min * 60
        best = min(range(len(series)), key=lambda j: abs((series[j][1] - series[j][0]) - target))
        if abs((series[best][1] - series[best][0]) - target) > POLL_TOLERANCE_S:
            continue
        polled_at, due, delay = series[best]
        rain, wind = _weather_at(w_times, w_rows, polled_at)
        samples.append({
            "trip_id": a.trip_id,
            "start_date": a.start_date,
            "stop_id": a.stop_id,
            "polled_at": polled_at,
            "actual": actual,
            "tfi_time": due,
            "tfi_eta_min": (due - polled_at) / 60,
            "tfi_delay_min": (delay or 0) / 60,
            "hour": local_hour(polled_at),
            "is_weekend": int(is_weekend(polled_at)),
            "rain_mm": rain,
            "wind_kmh": wind,
        })

    samples.sort(key=lambda s: s["actual"])
    return samples
