"""Timetable times, needed because the feed mostly reports delays and not clock times.

The time TFI is predicting for a bus is its timetable time plus the delay.
"""
from datetime import datetime
from zoneinfo import ZoneInfo

TZ = ZoneInfo("Europe/Dublin")


def load(conn):
    """{(trip_id, stop_id): seconds after the start of the service day}"""
    return {(t, s): sec for t, s, sec in conn.execute("SELECT trip_id, stop_id, arrival_s FROM schedule")}


def service_day_start(start_date):
    """GTFS counts times from noon minus 12 hours on the service day."""
    d = datetime.strptime(start_date, "%Y%m%d")
    return datetime(d.year, d.month, d.day, 12, tzinfo=TZ).timestamp() - 12 * 3600


def predicted_time(arrival_time, delay, start_date, scheduled_s):
    """The arrival time TFI is predicting, as epoch seconds, or None if it cannot be worked out."""
    if arrival_time:
        return arrival_time
    if delay is None or not start_date or scheduled_s is None:
        return None
    return service_day_start(start_date) + scheduled_s + delay
