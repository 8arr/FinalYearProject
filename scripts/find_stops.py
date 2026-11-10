"""Work out which stops and route ids to collect for.

Downloads the static TFI GTFS zip (no API key needed), finds the main stop
by its public stop number, then picks the closest stops that are served by
the given routes. The result goes into data/targets.json which the
collector reads.

    python scripts/find_stops.py --main 5029 --routes 41C --count 6
"""
import argparse
import csv
import io
import json
import math
import os
import sys
import tempfile
import zipfile

import requests

GTFS_URL = "https://www.transportforireland.ie/transitData/Data/GTFS_All.zip"
OUT_PATH = os.path.join(os.path.dirname(__file__), "..", "data", "targets.json")


def download(url, dest):
    with requests.get(url, stream=True, timeout=60) as r:
        r.raise_for_status()
        with open(dest, "wb") as f:
            for chunk in r.iter_content(1 << 20):
                f.write(chunk)


def read_csv(zf, name):
    with zf.open(name) as raw:
        yield from csv.DictReader(io.TextIOWrapper(raw, encoding="utf-8-sig"))


def metres_between(lat1, lon1, lat2, lon2):
    # flat earth approximation is plenty accurate over a few km
    dy = (lat2 - lat1) * 111_320
    dx = (lon2 - lon1) * 111_320 * math.cos(math.radians(lat1))
    return math.hypot(dx, dy)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--main", default="5029", help="public stop number of the main stop")
    ap.add_argument("--routes", nargs="+", default=["41C"], help="route short names")
    ap.add_argument("--count", type=int, default=6, help="total stops to keep, main stop included")
    ap.add_argument("--zip", help="use an already downloaded GTFS zip")
    args = ap.parse_args()

    zip_path = args.zip
    tmp = None
    if not zip_path:
        tmp = tempfile.NamedTemporaryFile(suffix=".zip", delete=False)
        tmp.close()
        zip_path = tmp.name
        print("downloading GTFS (about 140MB)...")
        download(GTFS_URL, zip_path)

    try:
        with zipfile.ZipFile(zip_path) as zf:
            wanted = {r.upper() for r in args.routes}
            route_ids = {}
            for r in read_csv(zf, "routes.txt"):
                if r["route_short_name"].upper() in wanted:
                    route_ids[r["route_id"]] = r["route_short_name"]
            if not route_ids:
                sys.exit(f"no routes found for {args.routes}")

            trip_ids = {t["trip_id"] for t in read_csv(zf, "trips.txt") if t["route_id"] in route_ids}

            stops = {s["stop_id"]: s for s in read_csv(zf, "stops.txt")}
            main = next((s for s in stops.values() if s["stop_code"] == args.main), None)
            if main is None:
                sys.exit(f"stop {args.main} not found")

            served = set()
            for st in read_csv(zf, "stop_times.txt"):
                if st["trip_id"] in trip_ids:
                    served.add(st["stop_id"])
    finally:
        if tmp:
            os.unlink(tmp.name)

    if main["stop_id"] not in served:
        sys.exit(f"stop {args.main} is not served by {args.routes}")

    mlat, mlon = float(main["stop_lat"]), float(main["stop_lon"])

    def dist(s):
        return metres_between(mlat, mlon, float(s["stop_lat"]), float(s["stop_lon"]))

    nearest = sorted((stops[i] for i in served), key=dist)[: args.count]
    out = {
        "main_stop_code": args.main,
        "routes": [{"route_id": rid, "short_name": name} for rid, name in route_ids.items()],
        "stops": [
            {
                "stop_id": s["stop_id"],
                "stop_code": s["stop_code"],
                "name": s["stop_name"],
                "lat": float(s["stop_lat"]),
                "lon": float(s["stop_lon"]),
                "metres_from_main": round(dist(s)),
            }
            for s in nearest
        ],
    }

    with open(OUT_PATH, "w") as f:
        json.dump(out, f, indent=2)
        f.write("\n")

    for s in out["stops"]:
        print(f"{s['stop_code']:>6}  {s['name']:<20} {s['metres_from_main']:>4}m")
    print(f"wrote {os.path.normpath(OUT_PATH)}")


if __name__ == "__main__":
    main()
