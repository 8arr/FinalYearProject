"""Polls the NTA realtime feeds and weather and stores what we need in SQLite.

    export NTA_API_KEY=...
    python -m collector.run
"""
import logging
import signal
import time

from . import config, db, feeds
from .weather import fetch_weather

log = logging.getLogger("collector")
stopping = False


def handle_signal(signum, frame):
    global stopping
    stopping = True


def poll_trip_updates(conn, key, route_ids, stops, now):
    try:
        msg = feeds.fetch_feed(config.TRIP_UPDATES_URL, key)
        rows = feeds.trip_update_rows(msg, route_ids, stops, now)
        db.insert_rows(conn, "trip_updates", db.TRIP_UPDATE_COLS, rows)
        db.log_poll(conn, now, "trip_updates", True, msg.header.timestamp or None, len(msg.entity), len(rows))
        log.info("trip updates: %d rows from %d entities", len(rows), len(msg.entity))
    except Exception as e:
        log.warning("trip updates failed: %s", e)
        db.log_poll(conn, now, "trip_updates", False, error=str(e)[:300])


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
    next_run = time.time()
    while not stopping:
        now = int(time.time())
        poll_trip_updates(conn, key, route_ids, stops, now)
        poll_vehicles(conn, key, route_ids, now)
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
