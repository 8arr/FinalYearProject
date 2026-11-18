"""Next bus estimates for a stop, using TFI when it looks healthy and
the stored history when it does not.

    python -m bus.predict --stop 5029
    python -m bus.predict --stop 5029 --model data/model30.pkl
"""
import argparse
import time
from dataclasses import dataclass, field
from datetime import datetime

from . import health
from .dataset import TZ, is_weekend, local_hour
from .fallback import estimate_from_history

# the model was trained for buses about 30 to 60 minutes out, so for buses
# due sooner than this TFI is already close and we leave it alone
MODEL_MIN_ETA_MIN = 20
MODEL_MAX_ETA_MIN = 75


@dataclass
class Estimate:
    time: float
    tfi_time: float = None
    trip_id: str = None
    note: str = ""


@dataclass
class Result:
    source: str  # "tfi" or "history"
    estimates: list = field(default_factory=list)
    notes: list = field(default_factory=list)


def _upcoming_from_feed(msg, stop_id, now):
    found = []
    for ent in msg.entity:
        if not ent.HasField("trip_update"):
            continue
        for stu in ent.trip_update.stop_time_update:
            if stu.stop_id != stop_id or not stu.arrival.time:
                continue
            if stu.arrival.time >= now - 60:
                found.append((stu.arrival.time, stu.arrival.delay, ent.trip_update.trip.trip_id))
    return sorted(found)


def _apply_model(model, upcoming, now, weather):
    rain, wind = weather()
    samples = [{
        "tfi_time": t,
        "tfi_eta_min": (t - now) / 60,
        "tfi_delay_min": delay / 60,
        "hour": local_hour(now),
        "is_weekend": int(is_weekend(now)),
        "rain_mm": rain,
        "wind_kmh": wind,
    } for t, delay, _ in upcoming]
    predicted = model.predict(samples)
    return [
        p if MODEL_MIN_ETA_MIN <= s["tfi_eta_min"] <= MODEL_MAX_ETA_MIN else s["tfi_time"]
        for p, s in zip(predicted, samples)
    ]


def estimate_next(stop_id, fetch, history, now=None, route_ids=None, model=None,
                  weather=lambda: (0.0, 0.0), n=3):
    """fetch() returns the trip updates feed or raises. history(now, n) returns
    HistoryEstimate objects. Neither failing feed nor bad data stops us giving
    an answer."""
    now = now if now is not None else time.time()
    notes = []

    try:
        msg = fetch()
        issues = health.check_feed(msg, now, "trip_updates", route_ids)
        notes += [i.text for i in issues]
        usable = not health.has_errors(issues)
    except Exception as e:
        notes.append(f"could not reach TFI: {e}")
        usable = False

    if usable:
        upcoming = _upcoming_from_feed(msg, stop_id, now)[:n]
        times = _apply_model(model, upcoming, now, weather) if model and upcoming else [u[0] for u in upcoming]
        return Result("tfi", [Estimate(float(t), tfi_time=u[0], trip_id=u[2])
                              for t, u in zip(times, upcoming)], notes)

    notes.append("using past arrivals at this time of day instead")
    est = [Estimate(h.time, note=f"{h.observations} past trips, usually within "
                                 f"{h.spread_min / 2:.0f} min of this")
           for h in history(now, n)]
    return Result("history", est, notes)


def main():
    from collector import config, db, feeds
    from . import model as model_mod
    from .arrivals import build_arrivals
    from .weather_now import current_weather

    ap = argparse.ArgumentParser()
    ap.add_argument("--stop", default="5029", help="public stop number")
    ap.add_argument("--db", default=config.DB_PATH)
    ap.add_argument("--model")
    args = ap.parse_args()

    route_ids, stops = config.load_targets()
    stop = next(s for s in stops.values() if s["stop_code"] == args.stop)
    key = config.api_key()
    conn = db.connect(args.db)
    mdl = model_mod.load(args.model) if args.model else None

    def history(now, n):
        arrivals = build_arrivals(conn, {stop["stop_id"]: stop}, since=now - 29 * 86400)
        return estimate_from_history(arrivals, stop["stop_id"], now, n)

    result = estimate_next(
        stop["stop_id"],
        fetch=lambda: feeds.fetch_feed(config.TRIP_UPDATES_URL, key),
        history=history, route_ids=route_ids, model=mdl,
        weather=lambda: current_weather(stop["lat"], stop["lon"]),
    )

    print(f"{stop['name']} ({stop['stop_code']}), source: {result.source}")
    for note in result.notes:
        print(f"  note: {note}")
    if not result.estimates:
        print("  no buses found")
    for e in result.estimates:
        at = datetime.fromtimestamp(e.time, TZ).strftime("%H:%M")
        extra = f"  (TFI said {datetime.fromtimestamp(e.tfi_time, TZ).strftime('%H:%M')})" if e.tfi_time else ""
        print(f"  {at}{extra}  {e.note}")


if __name__ == "__main__":
    main()
