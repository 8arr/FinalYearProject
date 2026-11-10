import requests

from . import config


def fetch_weather(lat, lon, polled_at, timeout=15):
    params = {
        "latitude": lat,
        "longitude": lon,
        "current": "temperature_2m,precipitation,rain,wind_speed_10m,weather_code",
    }
    r = requests.get(config.WEATHER_URL, params=params, timeout=timeout)
    r.raise_for_status()
    cur = r.json()["current"]
    return {
        "polled_at": polled_at,
        "temperature_c": cur.get("temperature_2m"),
        "precipitation_mm": cur.get("precipitation"),
        "rain_mm": cur.get("rain"),
        "wind_kmh": cur.get("wind_speed_10m"),
        "weather_code": cur.get("weather_code"),
    }
