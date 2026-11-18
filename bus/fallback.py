"""Estimate arrivals from history when TFI cannot be used.

Buses on a route run at roughly the same times on the same kind of day, so
the typical arrival time of each timetable slot over the last few weeks
makes a usable estimate on its own.
"""
import statistics
from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime, timedelta

from .dataset import TZ

MIN_OBSERVATIONS = 3
LOOKBACK_DAYS = 28


@dataclass
class HistoryEstimate:
    time: float
    slot: str
    observations: int
    spread_min: float  # middle 50% of past arrivals, a rough sense of how sure we are


def day_type(dt):
    return "weekday" if dt.weekday() < 5 else dt.strftime("%A")


def _seconds_into_day(epoch):
    dt = datetime.fromtimestamp(epoch, TZ)
    return dt.hour * 3600 + dt.minute * 60 + dt.second


def typical_times(arrivals, stop_id, now, truth="best", lookback_days=LOOKBACK_DAYS):
    """{(day type, timetable slot): [seconds into the day, ...]} from past arrivals."""
    cutoff = now - lookback_days * 86400
    groups = defaultdict(list)
    for a in arrivals:
        actual = a.actual(truth)
        if a.stop_id != stop_id or actual is None or not a.start_time:
            continue
        if not cutoff <= actual < now:
            continue
        key = (day_type(datetime.fromtimestamp(actual, TZ)), a.start_time)
        groups[key].append(_seconds_into_day(actual))
    return groups


def estimate_from_history(arrivals, stop_id, now, n=3, truth="best"):
    groups = typical_times(arrivals, stop_id, now, truth)
    today = datetime.fromtimestamp(now, TZ).replace(hour=0, minute=0, second=0, microsecond=0)
    found = []

    for offset in (0, 1):
        day = today + timedelta(days=offset)
        for (dtype, slot), secs in groups.items():
            if dtype != day_type(day) or len(secs) < MIN_OBSERVATIONS:
                continue
            when = day.timestamp() + statistics.median(secs)
            if when < now - 60:
                continue
            q = statistics.quantiles(secs, n=4) if len(secs) >= 4 else [min(secs), 0, max(secs)]
            found.append(HistoryEstimate(when, slot, len(secs), (q[2] - q[0]) / 60))
        if len(found) >= n:
            break

    found.sort(key=lambda e: e.time)
    return found[:n]


def backtest(arrivals, stop_id, truth="best"):
    """How good would the fallback have been on a recent day?

    Takes the latest day that has enough earlier days of the same kind,
    pretends it is just after midnight, builds estimates from the days
    before and compares each with when the bus really came. Returns the
    errors in seconds (estimate minus actual), one per timetable slot.
    """
    dated = [(a, a.actual(truth)) for a in arrivals if a.stop_id == stop_id and a.actual(truth)]
    days = sorted({datetime.fromtimestamp(t, TZ).date() for _, t in dated}, reverse=True)

    for day in days:
        now = datetime(day.year, day.month, day.day, 0, 1, tzinfo=TZ).timestamp()
        end = now + 86400
        history = [a for a, t in dated if t < now]
        estimates = {e.slot: e for e in estimate_from_history(history, stop_id, now, n=1000, truth=truth)
                     if e.time < end}
        errors = [estimates[a.start_time].time - t for a, t in dated
                  if now <= t < end and a.start_time in estimates]
        if errors:
            return errors
    return []
