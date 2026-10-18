"""
Query layer over the BMTC GTFS SQLite database (data/bmtc_gtfs.db).

All GTFS access in the app goes through here. GTFS times can exceed 24:00
(e.g. "25:10:00" = 01:10 next service day) — parse_time() handles that.
"""

import os
import sqlite3
from bisect import bisect_right
from datetime import datetime, timedelta

DB_PATH = os.path.join(os.path.dirname(__file__), "data", "bmtc_gtfs.db")

_conn = None


def _db():
    global _conn
    if _conn is None:
        _conn = sqlite3.connect(DB_PATH, check_same_thread=False)
        _conn.row_factory = sqlite3.Row
    return _conn


def parse_time(t):
    """GTFS HH:MM:SS (hours may be >= 24) → minutes since service-day midnight."""
    if not t:
        return None
    hh, mm, *_ = t.split(":")
    return int(hh) * 60 + int(mm)


def fmt_time(minutes):
    """Minutes since midnight → HH:MM (wrapped to 24h for display)."""
    return f"{(minutes // 60) % 24:02d}:{minutes % 60:02d}"


# -------------------------------------------------
# SEARCH
# -------------------------------------------------
def search_routes(text, limit=15):
    """Route-number search: variants with per-direction endpoints."""
    q = f"%{text.strip()}%"
    rows = _db().execute(
        """
        SELECT r.route_id, r.route_short_name, r.route_long_name,
               t.direction_id, COUNT(DISTINCT t.trip_id) AS trip_count
        FROM routes r
        JOIN trips t ON t.route_id = r.route_id
        WHERE r.route_short_name LIKE ?
        GROUP BY r.route_id, t.direction_id
        ORDER BY r.route_short_name, t.direction_id
        LIMIT ?
        """,
        (q, limit * 2),
    ).fetchall()

    variants = []
    for row in rows:
        endpoints = _direction_endpoints(row["route_id"], row["direction_id"])
        variants.append({
            "route_id": row["route_id"],
            "direction_id": row["direction_id"],
            "routeno": row["route_short_name"],
            "route_long_name": row["route_long_name"],
            "fromstation": endpoints[0],
            "tostation": endpoints[1],
            "trip_count": row["trip_count"],
        })
    return variants[:limit]


def _direction_endpoints(route_id, direction_id):
    """First and last stop names of the direction's longest trip."""
    row = _db().execute(
        """
        SELECT t.trip_id FROM trips t
        WHERE t.route_id = ? AND t.direction_id = ?
        LIMIT 1
        """,
        (route_id, direction_id),
    ).fetchone()
    if not row:
        return "", ""
    stops = _db().execute(
        """
        SELECT s.stop_name FROM stop_times st
        JOIN stops s ON s.stop_id = st.stop_id
        WHERE st.trip_id = ?
        ORDER BY st.stop_sequence
        """,
        (row["trip_id"],),
    ).fetchall()
    if not stops:
        return "", ""
    return stops[0]["stop_name"], stops[-1]["stop_name"]


def stops_autocomplete(query, limit=12):
    """Stop-name suggestions for source/destination inputs."""
    q = f"%{query.strip()}%"
    rows = _db().execute(
        """
        SELECT stop_id, stop_name, stop_lat, stop_lon FROM stops
        WHERE stop_name LIKE ?
        ORDER BY LENGTH(stop_name)
        LIMIT ?
        """,
        (q, limit),
    ).fetchall()
    return [dict(r) for r in rows]


def routes_between(source_query, dest_query, limit=15):
    """
    Routes that serve BOTH source and destination (in travel order) —
    the fix for 'no routes found' on source/dest search.
    """
    src_ids = [r["stop_id"] for r in stops_autocomplete(source_query, limit=8)]
    dst_ids = [r["stop_id"] for r in stops_autocomplete(dest_query, limit=8)]
    if not src_ids or not dst_ids:
        return []

    src_ph = ",".join("?" * len(src_ids))
    dst_ph = ",".join("?" * len(dst_ids))
    rows = _db().execute(
        f"""
        SELECT DISTINCT r.route_id, r.route_short_name, r.route_long_name,
               t.direction_id
        FROM stop_times a
        JOIN stop_times b ON a.trip_id = b.trip_id
                         AND a.stop_sequence < b.stop_sequence
        JOIN trips t ON t.trip_id = a.trip_id
        JOIN routes r ON r.route_id = t.route_id
        WHERE a.stop_id IN ({src_ph}) AND b.stop_id IN ({dst_ph})
        ORDER BY r.route_short_name
        LIMIT ?
        """,
        (*src_ids, *dst_ids, limit),
    ).fetchall()

    variants = []
    for row in rows:
        endpoints = _direction_endpoints(row["route_id"], row["direction_id"])
        variants.append({
            "route_id": row["route_id"],
            "direction_id": row["direction_id"],
            "routeno": row["route_short_name"],
            "route_long_name": row["route_long_name"],
            "fromstation": endpoints[0],
            "tostation": endpoints[1],
        })
    return variants


# -------------------------------------------------
# ROUTE DETAIL
# -------------------------------------------------
def route_stops(route_id, direction_id=0, max_times_per_stop=30):
    """
    Ordered stops for a route direction, each with the list of times buses
    depart from it today (across all trips) — the passenger timetable view.
    """
    trips = _db().execute(
        "SELECT trip_id FROM trips WHERE route_id = ? AND direction_id = ?",
        (route_id, direction_id),
    ).fetchall()
    trip_ids = [t["trip_id"] for t in trips]
    if not trip_ids:
        return {"stops": [], "trips": []}

    ph = ",".join("?" * len(trip_ids))
    rows = _db().execute(
        f"""
        SELECT st.trip_id, st.stop_id, st.departure_time, st.stop_sequence,
               s.stop_name, s.stop_lat, s.stop_lon
        FROM stop_times st
        JOIN stops s ON s.stop_id = st.stop_id
        WHERE st.trip_id IN ({ph})
        ORDER BY st.stop_sequence
        """,
        trip_ids,
    ).fetchall()

    # Canonical stop order from the longest trip
    by_trip = {}
    for r in rows:
        by_trip.setdefault(r["trip_id"], []).append(r)
    canonical_trip = max(by_trip.values(), key=len)
    stop_order = [r["stop_id"] for r in canonical_trip]
    stop_info = {r["stop_id"]: r for r in canonical_trip}

    # Departure times per stop across every trip
    times_by_stop = {}
    for r in rows:
        minutes = parse_time(r["departure_time"])
        if minutes is not None:
            times_by_stop.setdefault(r["stop_id"], set()).add(minutes)

    stops = []
    for seq, stop_id in enumerate(stop_order, start=1):
        info = stop_info[stop_id]
        times = sorted(times_by_stop.get(stop_id, set()))
        stops.append({
            "stop_id": stop_id,
            "name": info["stop_name"],
            "lat": info["stop_lat"],
            "lon": info["stop_lon"],
            "sequence": seq,
            "times": [fmt_time(m) for m in times[:max_times_per_stop]],
            "times_truncated": len(times) > max_times_per_stop,
        })

    trip_summaries = []
    for trip_id, trows in by_trip.items():
        start = parse_time(trows[0]["departure_time"])
        end = parse_time(trows[-1]["departure_time"])
        trip_summaries.append({
            "trip_id": trip_id,
            "start": fmt_time(start) if start is not None else None,
            "end": fmt_time(end) if end is not None else None,
        })
    trip_summaries.sort(key=lambda t: t["start"] or "")

    return {"stops": stops, "trips": trip_summaries}


def route_shape(route_id, direction_id=0, max_points=400):
    """Polyline [[lat, lon], ...] for the route direction (downsampled)."""
    row = _db().execute(
        """
        SELECT shape_id FROM trips
        WHERE route_id = ? AND direction_id = ? AND shape_id IS NOT NULL
        LIMIT 1
        """,
        (route_id, direction_id),
    ).fetchone()
    if not row or not row["shape_id"]:
        return []

    points = _db().execute(
        "SELECT lat, lon FROM shapes WHERE shape_id = ? ORDER BY seq",
        (row["shape_id"],),
    ).fetchall()
    coords = [[p["lat"], p["lon"]] for p in points]

    if len(coords) > max_points:
        step = len(coords) / max_points
        downsampled = [coords[int(i * step)] for i in range(max_points)]
        downsampled.append(coords[-1])  # always keep the true endpoint
        coords = downsampled
    return coords


def trip_timeline(trip_id):
    """[(stop_id, arrival_min, departure_min, seq)] for simulation."""
    rows = _db().execute(
        """
        SELECT stop_id, arrival_time, departure_time, stop_sequence
        FROM stop_times WHERE trip_id = ? ORDER BY stop_sequence
        """,
        (trip_id,),
    ).fetchall()
    return [
        (r["stop_id"], parse_time(r["arrival_time"]), parse_time(r["departure_time"]), r["stop_sequence"])
        for r in rows
    ]


def shape_points(shape_id):
    """[(lat, lon, dist)] ordered — for interpolating positions."""
    rows = _db().execute(
        "SELECT lat, lon, dist FROM shapes WHERE shape_id = ? ORDER BY seq",
        (shape_id,),
    ).fetchall()
    return [(r["lat"], r["lon"], r["dist"] or 0.0) for r in rows]


def route_trips(route_id, direction_id=0):
    """All trips with shape ids and start/end minutes."""
    rows = _db().execute(
        "SELECT trip_id, shape_id FROM trips WHERE route_id = ? AND direction_id = ?",
        (route_id, direction_id),
    ).fetchall()
    result = []
    for r in rows:
        tl = trip_timeline(r["trip_id"])
        if not tl:
            continue
        result.append({
            "trip_id": r["trip_id"],
            "shape_id": r["shape_id"],
            "start_min": tl[0][2],
            "end_min": tl[-1][1],
            "timeline": tl,
        })
    return result


def get_stop(stop_id):
    row = _db().execute(
        "SELECT stop_id, stop_name, stop_lat, stop_lon, zone_id FROM stops WHERE stop_id = ?",
        (stop_id,),
    ).fetchone()
    return dict(row) if row else None


def lookup_fare(route_id, origin_stop_id, dest_stop_id):
    """
    Real BMTC fare from fare_rules (matched via stop zones).
    Tries a route-specific rule first, then the network-wide OD fare table
    (most rules have route_id NULL). Returns None when no rule exists.
    """
    origin = get_stop(origin_stop_id)
    dest = get_stop(dest_stop_id)
    if not origin or not dest or not origin["zone_id"] or not dest["zone_id"]:
        return None

    for scope, params in (
        ("route", (route_id, origin["zone_id"], dest["zone_id"])),
        ("global", (origin["zone_id"], dest["zone_id"])),
    ):
        if scope == "route":
            row = _db().execute(
                """
                SELECT fa.price FROM fare_rules fr
                JOIN fare_attributes fa ON fa.fare_id = fr.fare_id
                WHERE fr.route_id = ? AND fr.origin_id = ? AND fr.destination_id = ?
                LIMIT 1
                """,
                params,
            ).fetchone()
        else:
            row = _db().execute(
                """
                SELECT fa.price FROM fare_rules fr
                JOIN fare_attributes fa ON fa.fare_id = fr.fare_id
                WHERE fr.route_id IS NULL AND fr.origin_id = ? AND fr.destination_id = ?
                LIMIT 1
                """,
                params,
            ).fetchone()
        if row:
            return float(row["price"])
    return None
