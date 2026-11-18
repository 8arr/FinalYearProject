"""Quick look at what the collector has stored so far."""
import os
import sqlite3
import sys
import time

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from collector import config  # noqa: E402


def main():
    conn = sqlite3.connect(config.DB_PATH)
    for table in ("trip_updates", "vehicle_positions", "weather", "polls"):
        n = conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
        print(f"{table:<18} {n}")

    last = conn.execute("SELECT MAX(polled_at) FROM polls").fetchone()[0]
    if last:
        print(f"last poll          {int(time.time()) - last}s ago")

    print("\nrows stored in the last 24h (0 for a whole day means the filter is not matching):")
    since = int(time.time()) - 86400
    for table in ("trip_updates", "vehicle_positions"):
        n = conn.execute(f"SELECT COUNT(*) FROM {table} WHERE polled_at > ?", (since,)).fetchone()[0]
        newest = conn.execute(f"SELECT MAX(polled_at) FROM {table}").fetchone()[0]
        ago = f"{(int(time.time()) - newest) / 3600:.1f}h ago" if newest else "never"
        print(f"  {table}: {n}, newest row {ago}")

    print("\nfailed polls in the last 24h:")
    rows = conn.execute(
        "SELECT feed, COUNT(*) FROM polls WHERE ok = 0 AND polled_at > ? GROUP BY feed",
        (int(time.time()) - 86400,),
    ).fetchall()
    for feed, n in rows or [("none", 0)]:
        print(f"  {feed}: {n}")


if __name__ == "__main__":
    main()
