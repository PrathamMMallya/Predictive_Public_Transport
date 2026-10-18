"""
Import the BMTC GTFS feed (server/data/gtfs/*.txt) into SQLite
(server/data/bmtc_gtfs.db).

Why SQLite: GTFS static data is read-only and relational. The key queries —
"routes whose trips serve stop A before stop B", "stop times for trip X" —
are indexed SQL joins. MongoDB stays the store for users/tickets/live state.

Usage:  python import_gtfs.py
"""

import csv
import os
import sqlite3
import sys
import time

DATA_DIR = os.path.join(os.path.dirname(__file__), "data", "gtfs")
DB_PATH = os.path.join(os.path.dirname(__file__), "data", "bmtc_gtfs.db")

CHUNK = 50_000


def import_table(cur, conn, filename, columns, table, cast=None, rename=None):
    path = os.path.join(DATA_DIR, filename)
    if not os.path.exists(path):
        print(f"  ! {filename} missing — skipped")
        return 0

    cast = cast or {}
    rename = rename or {}
    table_cols = [rename.get(c, c) for c in columns]
    placeholders = ",".join("?" * len(table_cols))
    col_list = ",".join(table_cols)

    t0 = time.time()
    total = 0
    with open(path, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        batch = []
        for row in reader:
            try:
                batch.append(tuple(cast.get(c, str)(row[c]) if row[c] != "" else None for c in columns))
            except (ValueError, KeyError):
                continue
            if len(batch) >= CHUNK:
                cur.executemany(f"INSERT INTO {table} ({col_list}) VALUES ({placeholders})", batch)
                total += len(batch)
                batch.clear()
                conn.commit()
        if batch:
            cur.executemany(f"INSERT INTO {table} ({col_list}) VALUES ({placeholders})", batch)
            total += len(batch)
        conn.commit()
    print(f"  ✓ {table}: {total:,} rows ({time.time() - t0:.1f}s)")
    return total


def main():
    if os.path.exists(DB_PATH):
        os.remove(DB_PATH)

    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute("PRAGMA journal_mode=WAL")
    cur.execute("PRAGMA synchronous=OFF")

    cur.executescript("""
    CREATE TABLE routes (
        route_id TEXT PRIMARY KEY,
        route_short_name TEXT,
        route_long_name TEXT,
        route_type INTEGER
    );
    CREATE TABLE stops (
        stop_id TEXT PRIMARY KEY,
        stop_name TEXT,
        stop_lat REAL,
        stop_lon REAL,
        zone_id TEXT
    );
    CREATE TABLE trips (
        trip_id TEXT PRIMARY KEY,
        route_id TEXT,
        service_id TEXT,
        direction_id INTEGER,
        shape_id TEXT,
        trip_headsign TEXT
    );
    CREATE TABLE stop_times (
        trip_id TEXT,
        arrival_time TEXT,
        departure_time TEXT,
        stop_id TEXT,
        stop_sequence INTEGER
    );
    CREATE TABLE shapes (
        shape_id TEXT,
        lat REAL,
        lon REAL,
        seq INTEGER,
        dist REAL
    );
    CREATE TABLE fare_attributes (
        fare_id TEXT PRIMARY KEY,
        price REAL
    );
    CREATE TABLE fare_rules (
        fare_id TEXT,
        route_id TEXT,
        origin_id TEXT,
        destination_id TEXT
    );
    """)

    print("Importing GTFS → SQLite…")
    import_table(cur, conn, "routes.txt",
                 ["route_id", "route_short_name", "route_long_name", "route_type"],
                 "routes", {"route_type": int})
    import_table(cur, conn, "stops.txt",
                 ["stop_id", "stop_name", "stop_lat", "stop_lon", "zone_id"],
                 "stops", {"stop_lat": float, "stop_lon": float})
    import_table(cur, conn, "trips.txt",
                 ["trip_id", "route_id", "service_id", "direction_id", "shape_id", "trip_headsign"],
                 "trips", {"direction_id": int})
    import_table(cur, conn, "stop_times.txt",
                 ["trip_id", "arrival_time", "departure_time", "stop_id", "stop_sequence"],
                 "stop_times", {"stop_sequence": int})
    import_table(cur, conn, "shapes.txt",
                 ["shape_id", "shape_pt_lat", "shape_pt_lon", "shape_pt_sequence", "shape_dist_traveled"],
                 "shapes", {"shape_pt_lat": float, "shape_pt_lon": float,
                            "shape_pt_sequence": int, "shape_dist_traveled": float},
                 rename={"shape_pt_lat": "lat", "shape_pt_lon": "lon",
                         "shape_pt_sequence": "seq", "shape_dist_traveled": "dist"})
    import_table(cur, conn, "fare_attributes.txt",
                 ["fare_id", "price"], "fare_attributes", {"price": float})
    import_table(cur, conn, "fare_rules.txt",
                 ["fare_id", "route_id", "origin_id", "destination_id"], "fare_rules")

    print("Building indexes…")
    t0 = time.time()
    cur.executescript("""
    CREATE INDEX idx_routes_short ON routes(route_short_name);
    CREATE INDEX idx_stops_name ON stops(stop_name);
    CREATE INDEX idx_trips_route ON trips(route_id, direction_id);
    CREATE INDEX idx_st_trip ON stop_times(trip_id, stop_sequence);
    CREATE INDEX idx_st_stop ON stop_times(stop_id);
    CREATE INDEX idx_shapes_id ON shapes(shape_id, seq);
    CREATE INDEX idx_fare_rules_route ON fare_rules(route_id, origin_id, destination_id);
    """)
    conn.commit()
    print(f"  ✓ indexes ({time.time() - t0:.1f}s)")

    for table in ("routes", "stops", "trips", "stop_times", "shapes"):
        count = cur.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
        print(f"  {table}: {count:,}")

    conn.close()
    print(f"Done → {DB_PATH}")


if __name__ == "__main__":
    sys.exit(main())
