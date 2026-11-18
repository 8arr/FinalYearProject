"""Load the scheduled stop times for our routes and stops into the database.

The feed mostly reports how late a bus is (a delay in seconds) and only
rarely a clock time, so to get the time TFI is predicting we need the
timetable time to add the delay to. Run this once, and again when TFI
publishes a new timetable.

    python scripts/load_schedule.py --db data/bus.db
"""
import argparse
import os
import sys
import tempfile
import zipfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))

from find_stops import GTFS_URL, download, read_csv  # noqa: E402
from collector import config, db  # noqa: E402


def seconds(hms):
    """GTFS times can go past 24:00:00 for trips that run after midnight."""
    h, m, s = (int(x) for x in hms.split(":"))
    return h * 3600 + m * 60 + s


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--db", default=config.DB_PATH)
    ap.add_argument("--zip", help="use an already downloaded GTFS zip")
    args = ap.parse_args()

    names = {r["short_name"].upper() for r in config.load_targets_raw()["routes"]}
    _, stops = config.load_targets()

    zip_path, tmp = args.zip, None
    if not zip_path:
        tmp = tempfile.NamedTemporaryFile(suffix=".zip", delete=False)
        tmp.close()
        zip_path = tmp.name
        print("downloading GTFS (about 180MB)...")
        download(GTFS_URL, zip_path)

    rows = []
    try:
        with zipfile.ZipFile(zip_path) as zf:
            route_ids = {r["route_id"] for r in read_csv(zf, "routes.txt")
                         if r["route_short_name"].upper() in names}
            trips = {t["trip_id"] for t in read_csv(zf, "trips.txt") if t["route_id"] in route_ids}
            for st in read_csv(zf, "stop_times.txt"):
                if st["trip_id"] in trips and st["stop_id"] in stops and st["arrival_time"]:
                    rows.append((st["trip_id"], st["stop_id"], int(st["stop_sequence"]),
                                 seconds(st["arrival_time"])))
    finally:
        if tmp:
            os.unlink(tmp.name)

    conn = db.connect(args.db)
    conn.executemany(
        "INSERT OR REPLACE INTO schedule (trip_id, stop_id, stop_sequence, arrival_s) VALUES (?,?,?,?)", rows)
    conn.commit()
    print(f"loaded {len(rows)} scheduled stop times for {len(trips)} trips into {args.db}")


if __name__ == "__main__":
    main()
