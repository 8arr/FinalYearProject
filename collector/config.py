import json
import os

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

API_BASE = "https://api.nationaltransport.ie/gtfsr/v2"
TRIP_UPDATES_URL = f"{API_BASE}/TripUpdates"
VEHICLES_URL = f"{API_BASE}/Vehicles"

WEATHER_URL = "https://api.open-meteo.com/v1/forecast"

POLL_SECONDS = int(os.environ.get("POLL_SECONDS", "60"))
WEATHER_EVERY_SECONDS = int(os.environ.get("WEATHER_EVERY_SECONDS", "600"))
DB_PATH = os.environ.get("BUS_DB_PATH", os.path.join(ROOT, "data", "bus.db"))
TARGETS_PATH = os.path.join(ROOT, "data", "targets.json")


def api_key():
    key = os.environ.get("NTA_API_KEY")
    if not key:
        raise SystemExit("NTA_API_KEY is not set")
    return key


def load_targets():
    with open(TARGETS_PATH) as f:
        t = json.load(f)
    route_ids = {r["route_id"] for r in t["routes"]}
    stops = {s["stop_id"]: s for s in t["stops"]}
    return route_ids, stops
