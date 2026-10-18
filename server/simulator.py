"""
Real-time bus simulation.

Positions: for every trip that is active *right now* (per the GTFS
timetable), we interpolate the bus along its route shape between the two
stops it is currently between. Refreshing the endpoint gives a moving bus —
a faithful stand-in while the live BMTC tracking API is unreachable.

Crowding: each simulated bus carries an OCI that follows the typical daily
profile (peaks 8–10 / 17–19), a stable per-trip offset, and slow-drifting
noise. When a conductor is REALLY issuing tickets on the route, the real
value wins (see passenger_dashboard / admin insights).
"""

import hashlib
import math
from bisect import bisect_right
from datetime import datetime

import gtfs_data as g
from tracking_utils import classify_overcrowding, typical_oci

# Caches — GTFS data is static, so these live for the process lifetime
_ROUTE_TRIPS_CACHE = {}   # (route_id, direction) -> [trip dicts]
_SHAPE_CACHE = {}         # shape_id -> [(lat, lon, dist)]
_STOP_DISTS_CACHE = {}    # trip_id -> [shape dist at each timeline stop]
_STOP_COORDS_CACHE = {}   # stop_id -> (lat, lon)


def _stable_int(text, mod):
    return int(hashlib.md5(text.encode()).hexdigest(), 16) % mod


def vehicle_for_trip(trip_id):
    """Deterministic KSRTC-style registration per trip."""
    return f"KA{_stable_int(trip_id, 50) + 1:02d}F{_stable_int(trip_id[::-1], 9000) + 1000:04d}"


def _shape(shape_id):
    if shape_id not in _SHAPE_CACHE:
        _SHAPE_CACHE[shape_id] = g.shape_points(shape_id)
    return _SHAPE_CACHE[shape_id]


def _stop_coords(stop_id):
    if stop_id not in _STOP_COORDS_CACHE:
        stop = g.get_stop(stop_id)
        _STOP_COORDS_CACHE[stop_id] = (
            (stop["stop_lat"], stop["stop_lon"]) if stop else (None, None)
        )
    return _STOP_COORDS_CACHE[stop_id]


def _route_trips(route_id, direction_id):
    key = (route_id, direction_id)
    if key not in _ROUTE_TRIPS_CACHE:
        _ROUTE_TRIPS_CACHE[key] = g.route_trips(route_id, direction_id)
    return _ROUTE_TRIPS_CACHE[key]


def _stop_dists(trip):
    """
    Cumulative shape distance at each stop of the trip (monotonic), found by
    snapping each stop's coordinates to the nearest shape point.
    """
    trip_id = trip["trip_id"]
    if trip_id in _STOP_DISTS_CACHE:
        return _STOP_DISTS_CACHE[trip_id]

    shape = _shape(trip["shape_id"])
    dists = []
    if not shape:
        _STOP_DISTS_CACHE[trip_id] = dists
        return dists

    last_idx = 0
    for stop_id, _, _, _ in trip["timeline"]:
        lat, lon = _stop_coords(stop_id)
        if lat is None:
            dists.append(dists[-1] if dists else 0.0)
            continue
        # search forward from the previous match (stops are ordered)
        best_idx, best_d = last_idx, float("inf")
        for i in range(last_idx, len(shape)):
            d = (shape[i][0] - lat) ** 2 + (shape[i][1] - lon) ** 2
            if d < best_d:
                best_d, best_idx = d, i
        last_idx = best_idx
        dists.append(shape[best_idx][2])
    # enforce monotonicity
    for i in range(1, len(dists)):
        dists[i] = max(dists[i], dists[i - 1])

    _STOP_DISTS_CACHE[trip_id] = dists
    return dists


def simulated_oci(trip_id, when=None):
    """Smooth pseudo-random OCI for a trip at a time — deterministic per minute."""
    when = when or datetime.now()
    hour = when.hour + when.minute / 60
    base = typical_oci(when.hour)
    offset = _stable_int(trip_id, 21) - 10                     # stable ±10 per trip
    drift = int(8 * math.sin((when.hour * 60 + when.minute + _stable_int(trip_id, 60)) / 25.0))
    return max(5, min(130, base + offset + drift))


def _position_on_shape(shape, dist):
    """(lat, lon, bearing) at a cumulative distance along the shape."""
    dists = [p[2] for p in shape]
    i = bisect_right(dists, dist)
    if i <= 0:
        lat, lon = shape[0][0], shape[0][1]
        nxt = shape[1] if len(shape) > 1 else shape[0]
    elif i >= len(shape):
        lat, lon = shape[-1][0], shape[-1][1]
        nxt = shape[-1]
    else:
        p0, p1 = shape[i - 1], shape[i]
        span = (p1[2] - p0[2]) or 1.0
        frac = (dist - p0[2]) / span
        lat = p0[0] + frac * (p1[0] - p0[0])
        lon = p0[1] + frac * (p1[1] - p0[1])
        nxt = p1
    bearing = math.degrees(math.atan2(nxt[1] - lon, nxt[0] - lat)) % 360
    return round(lat, 6), round(lon, 6), round(bearing, 1)


def trip_position(trip, now_min):
    """
    Where is this trip at minute-of-day `now_min`?
    Returns dict(lat, lon, bearing, status, next_stop, eta_min) or None if
    the trip isn't running at that time.
    """
    timeline = trip["timeline"]
    if not timeline or now_min < trip["start_min"] or now_min > trip["end_min"]:
        return None

    stop_dists = _stop_dists(trip)
    shape = _shape(trip["shape_id"])
    if not shape or len(stop_dists) != len(timeline):
        return None

    total_dist = stop_dists[-1] or 1.0

    # dwelling at a stop?
    for i, (stop_id, arr, dep, _seq) in enumerate(timeline):
        if arr is not None and dep is not None and arr <= now_min <= dep:
            lat, lon, bearing = _position_on_shape(shape, stop_dists[i])
            return {
                "lat": lat, "lon": lon, "bearing": bearing,
                "status": "AT_STOP",
                "current_stop": g.get_stop(stop_id)["stop_name"] if g.get_stop(stop_id) else None,
                "next_stop": _next_stop_name(timeline, i + 1),
                "eta_min": max(0, round((timeline[i + 1][1] - now_min))) if i + 1 < len(timeline) else 0,
                "progress": round(stop_dists[i] / total_dist * 100, 1),
            }

    # between stops?
    for i in range(len(timeline) - 1):
        dep_i = timeline[i][2]
        arr_next = timeline[i + 1][1]
        if dep_i is None or arr_next is None:
            continue
        if dep_i <= now_min <= arr_next:
            span = (arr_next - dep_i) or 1.0
            frac = (now_min - dep_i) / span
            dist = stop_dists[i] + frac * (stop_dists[i + 1] - stop_dists[i])
            lat, lon, bearing = _position_on_shape(shape, dist)
            return {
                "lat": lat, "lon": lon, "bearing": bearing,
                "status": "EN_ROUTE",
                "current_stop": None,
                "next_stop": _next_stop_name(timeline, i + 1),
                "eta_min": max(0, round(arr_next - now_min)),
                "progress": round(dist / total_dist * 100, 1),
            }

    return None


def _next_stop_name(timeline, idx):
    if idx >= len(timeline):
        return None
    stop = g.get_stop(timeline[idx][0])
    return stop["stop_name"] if stop else None


def live_buses(route_id, direction_id=0, now=None, include_real_oci=None):
    """
    All buses of a route direction on the road right now.
    include_real_oci: optional real OCI from conductor ticketing — when
    present it replaces the simulated value (real data wins).
    """
    now = now or datetime.now()
    now_min = now.hour * 60 + now.minute + now.second / 60

    buses = []
    for trip in _route_trips(route_id, direction_id):
        pos = trip_position(trip, now_min)
        if not pos:
            continue
        oci = include_real_oci if include_real_oci is not None else simulated_oci(trip["trip_id"], now)
        buses.append({
            "trip_id": trip["trip_id"],
            "vehicle": vehicle_for_trip(trip["trip_id"]),
            "oci": oci,
            "level": classify_overcrowding(oci),
            "simulated": include_real_oci is None,
            **pos,
        })

    # upcoming departures in the next 90 minutes
    upcoming = []
    for trip in _route_trips(route_id, direction_id):
        if trip["start_min"] and now_min < trip["start_min"] <= now_min + 90:
            upcoming.append({
                "trip_id": trip["trip_id"],
                "vehicle": vehicle_for_trip(trip["trip_id"]),
                "start": g.fmt_time(trip["start_min"]),
                "in_min": round(trip["start_min"] - now_min),
            })
    upcoming.sort(key=lambda u: u["in_min"])

    return {"buses": buses, "upcoming": upcoming[:8]}


def scheduled_trips_today(route_id, direction_id=0):
    """Trips per hour histogram for the frequency view."""
    per_hour = {}
    trips = []
    for trip in _route_trips(route_id, direction_id):
        if trip["start_min"] is None:
            continue
        per_hour[trip["start_min"] // 60] = per_hour.get(trip["start_min"] // 60, 0) + 1
        trips.append({
            "trip_id": trip["trip_id"],
            "start": g.fmt_time(trip["start_min"]),
            "end": g.fmt_time(trip["end_min"]) if trip["end_min"] else None,
        })
    trips.sort(key=lambda t: t["start"])
    return per_hour, trips
