import time

from collector.weather import fetch_weather


def current_weather(lat, lon):
    """(rain mm, wind km/h), or zeros if the weather service is down."""
    try:
        w = fetch_weather(lat, lon, int(time.time()))
        return w["rain_mm"] or 0.0, w["wind_kmh"] or 0.0
    except Exception:
        return 0.0, 0.0
