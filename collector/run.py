"""Polls the NTA realtime feeds and weather and stores what we need in SQLite.

    export NTA_API_KEY=...
    python -m collector.run
"""
import logging
import signal
import time
from datetime import datetime
from zoneinfo import ZoneInfo

from . import config, db, feeds
from .weather import fetch_weather

log = logging.getLogger("collector")
stopping = False

# the 41C runs from early morning until late, so hours of nothing during the
# day means our filter has stopped matching (this happened when TFI changed
# the route id format) and not that there are no buses
SILENT_AFTER_S = 3 * 3600
WARN_EVERY_S = 1800


def in_service_hours(epoch):
    return 8 <= datetime.fromtimestamp(epoch, ZoneInfo("Europe/Dublin")).hour < 21


def handle_signal(signum, frame):
    global stopping
    stopping = True


def poll_trip_updates(conn, key, route_ids, stops, now):
    """Returns (rows kept, route ids seen at our stops if nothing was kept)."""
    try:
        msg = feeds.fetch_feed(config.TRIP_UPDATES_URL, key)
        rows = feeds.trip_update_rows(msg, route_ids, stops, now)
        db.insert_rows(conn, "trip_updates", db.TRIP_UPDATE_COLS, rows)
        db.log_poll(conn, now, "trip_updates", True, msg.header.timestamp or None, len(msg.entity), len(rows))
        log.info("trip updates: %d rows from %d entities", len(rows), len(msg.entity))
        return len(rows), (None if rows else feeds.route_ids_at_stops(msg, stops))
    except Exception as e:
        log.warning("trip updates failed: %s", e)
        db.log_poll(conn, now, "trip_updates", False, error=str(e)[:300])
        return None, None


def poll_vehicles(conn, key, route_ids, now):
    try:
        msg = feeds.fetch_feed(config.VEHICLES_URL, key)
        rows = feeds.vehicle_rows(msg, route_ids, now)
        db.insert_rows(conn, "vehicle_positions", db.VEHICLE_COLS, rows)
        db.log_poll(conn, now, "vehicles", True, msg.header.timestamp or None, len(msg.entity), len(rows))
        log.info("vehicles: %d on our routes of %d", len(rows), len(msg.entity))
    except Exception as e:
        log.warning("vehicles failed: %s", e)
        db.log_poll(conn, now, "vehicles", False, error=str(e)[:300])


def poll_weather(conn, lat, lon, now):
    try:
        row = fetch_weather(lat, lon, now)
        db.insert_rows(conn, "weather", db.WEATHER_COLS, [row])
        db.log_poll(conn, now, "weather", True, kept=1)
    except Exception as e:
        log.warning("weather failed: %s", e)
        db.log_poll(conn, now, "weather", False, error=str(e)[:300])


def main():
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    signal.signal(signal.SIGTERM, handle_signal)
    signal.signal(signal.SIGINT, handle_signal)

    key = config.api_key()
    route_ids, stops = config.load_targets()
    main_stop = next(iter(stops.values()))
    conn = db.connect(config.DB_PATH)
    log.info("watching %d stops on %s, every %ds", len(stops), sorted(route_ids), config.POLL_SECONDS)

    last_weather = 0
    last_kept = last_warned = int(time.time())
    next_run = time.time()
    while not stopping:
        now = int(time.time())
        kept, seen = poll_trip_updates(conn, key, route_ids, stops, now)
        poll_vehicles(conn, key, route_ids, now)
        if kept:
            last_kept = now
        elif kept == 0 and in_service_hours(now) and now - last_kept > SILENT_AFTER_S \
                and now - last_warned > WARN_EVERY_S:
            last_warned = now
            log.warning("nothing kept for %.0f hours but the feed is up. Route ids at our stops: %s. "
                        "Filter is %s", (now - last_kept) / 3600, dict(seen), sorted(route_ids))
        if now - last_weather >= config.WEATHER_EVERY_SECONDS:
            poll_weather(conn, main_stop["lat"], main_stop["lon"], now)
            last_weather = now
        conn.commit()

        # keep a steady cadence instead of drifting by however long the requests took
        next_run += config.POLL_SECONDS
        delay = next_run - time.time()
        if delay < 0:
            next_run = time.time()
            delay = 0
        end = time.time() + delay
        while not stopping and time.time() < end:
            time.sleep(min(1, end - time.time()))

    conn.close()
    log.info("stopped")


if __name__ == "__main__":
    main()
