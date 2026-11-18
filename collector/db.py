import sqlite3

SCHEMA = """
CREATE TABLE IF NOT EXISTS polls (
    id INTEGER PRIMARY KEY,
    polled_at INTEGER NOT NULL,
    feed TEXT NOT NULL,
    ok INTEGER NOT NULL,
    feed_timestamp INTEGER,
    entities_total INTEGER,
    rows_kept INTEGER,
    error TEXT
);

CREATE TABLE IF NOT EXISTS trip_updates (
    id INTEGER PRIMARY KEY,
    polled_at INTEGER NOT NULL,
    trip_id TEXT NOT NULL,
    route_id TEXT,
    direction_id INTEGER,
    start_date TEXT,
    start_time TEXT,
    vehicle_id TEXT,
    stop_id TEXT NOT NULL,
    stop_sequence INTEGER,
    arrival_time INTEGER,
    arrival_delay INTEGER,
    departure_time INTEGER,
    departure_delay INTEGER,
    schedule_relationship TEXT
);
CREATE INDEX IF NOT EXISTS idx_tu_stop_time ON trip_updates (stop_id, polled_at);
CREATE INDEX IF NOT EXISTS idx_tu_trip ON trip_updates (trip_id, start_date);

CREATE TABLE IF NOT EXISTS vehicle_positions (
    id INTEGER PRIMARY KEY,
    polled_at INTEGER NOT NULL,
    vehicle_id TEXT,
    trip_id TEXT,
    route_id TEXT,
    direction_id INTEGER,
    start_date TEXT,
    start_time TEXT,
    lat REAL,
    lon REAL,
    bearing REAL,
    speed REAL,
    position_time INTEGER,
    current_stop_sequence INTEGER,
    stop_id TEXT,
    current_status TEXT
);
CREATE INDEX IF NOT EXISTS idx_vp_trip ON vehicle_positions (trip_id, start_date, polled_at);

CREATE TABLE IF NOT EXISTS schedule (
    trip_id TEXT NOT NULL,
    stop_id TEXT NOT NULL,
    stop_sequence INTEGER,
    arrival_s INTEGER NOT NULL,
    PRIMARY KEY (trip_id, stop_id)
);

CREATE TABLE IF NOT EXISTS weather (
    id INTEGER PRIMARY KEY,
    polled_at INTEGER NOT NULL,
    temperature_c REAL,
    precipitation_mm REAL,
    rain_mm REAL,
    wind_kmh REAL,
    weather_code INTEGER
);
"""

TRIP_UPDATE_COLS = (
    "polled_at", "trip_id", "route_id", "direction_id", "start_date", "start_time",
    "vehicle_id", "stop_id", "stop_sequence", "arrival_time", "arrival_delay",
    "departure_time", "departure_delay", "schedule_relationship",
)

VEHICLE_COLS = (
    "polled_at", "vehicle_id", "trip_id", "route_id", "direction_id", "start_date",
    "start_time", "lat", "lon", "bearing", "speed", "position_time",
    "current_stop_sequence", "stop_id", "current_status",
)

WEATHER_COLS = (
    "polled_at", "temperature_c", "precipitation_mm", "rain_mm", "wind_kmh", "weather_code",
)


def connect(path):
    conn = sqlite3.connect(path)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.executescript(SCHEMA)
    return conn


def insert_rows(conn, table, cols, rows):
    if not rows:
        return
    marks = ",".join("?" * len(cols))
    sql = f"INSERT INTO {table} ({','.join(cols)}) VALUES ({marks})"
    conn.executemany(sql, [tuple(r[c] for c in cols) for r in rows])


def log_poll(conn, polled_at, feed, ok, feed_timestamp=None, total=None, kept=None, error=None):
    conn.execute(
        "INSERT INTO polls (polled_at, feed, ok, feed_timestamp, entities_total, rows_kept, error)"
        " VALUES (?,?,?,?,?,?,?)",
        (polled_at, feed, int(ok), feed_timestamp, total, kept, error),
    )
