import math
import time
from datetime import datetime

import requests
from flask import Blueprint, request, jsonify

from auth_utils import require_role
from bmtc_data import search_catalog, catalog_stops, catalog_route
from db import (
    passenger_tracking_collection,
    ticketing_logs_collection,
    oci_timeseries_collection,
)
from tracking_utils import (
    calculate_overcrowding_index,
    classify_overcrowding,
    recompute_and_persist,
)

ticket_collector_bp = Blueprint("ticket_collector", __name__)

# ---------------- HELPER FUNCTIONS --------------------

def calculate_distance(lat1, lon1, lat2, lon2):
    R = 6371
    lat1_rad = math.radians(float(lat1))
    lat2_rad = math.radians(float(lat2))
    delta_lat = math.radians(float(lat2) - float(lat1))
    delta_lon = math.radians(float(lon2) - float(lon1))
    a = math.sin(delta_lat / 2) ** 2 + math.cos(lat1_rad) * math.cos(lat2_rad) * math.sin(delta_lon / 2) ** 2
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
    return R * c

def geocode_coordinates(lat, lon):
    try:
        url = "https://nominatim.openstreetmap.org/reverse"
        params = {"lat": lat, "lon": lon, "format": "json", "addressdetails": 1}
        headers = {"User-Agent": "BMTC-Bus-Tracker/1.0"}
        response = requests.get(url, params=params, headers=headers, timeout=5)
        if response.status_code == 200:
            data = response.json()
            address = data.get("address", {})
            parts = []
            if address.get("road"):
                parts.append(address["road"])
            if address.get("neighbourhood"):
                parts.append(address["neighbourhood"])
            elif address.get("suburb"):
                parts.append(address["suburb"])
            if address.get("city"):
                parts.append(address["city"])
            elif address.get("town"):
                parts.append(address["town"])
            if not parts and data.get("display_name"):
                return ", ".join(data["display_name"].split(",")[0:2])
            return ", ".join(parts) if parts else f"Location ({float(lat):.4f}, {float(lon):.4f})"
        else:
            return f"Location ({float(lat):.4f}, {float(lon):.4f})"
    except Exception as e:
        print(f"Geocoding error: {str(e)}")
        return f"Location ({float(lat):.4f}, {float(lon):.4f})"

def filter_points_by_distance(points, min_distance_km=2.0):
    if not points:
        return []
    filtered = [points[0]]
    for point in points[1:]:
        last_point = filtered[-1]
        distance = calculate_distance(
            last_point["latitude"],
            last_point["longitude"],
            point["latitude"],
            point["longitude"]
        )
        if distance >= min_distance_km:
            filtered.append(point)
    return filtered

def _extract_routeno(item):
    keys = ["routeno", "route_no", "routeNo", "routecode", "routeCode", "ROUTE_NO", "routenumber", "route_no_text", "RouteNo", "routeNoDisplay"]
    for k in keys:
        val = item.get(k)
        if val and str(val).strip():
            return str(val).strip()
    return ""

# ------------------- SEARCH ROUTES ---------------------------
@ticket_collector_bp.route("/api/search-routes", methods=["GET"])
def search_routes():
    routetext = request.args.get("routetext")
    if not routetext:
        return jsonify({"error": "routetext required"}), 400

    url = "https://bmtcmobileapi.karnataka.gov.in/WebAPI/SearchRoute_v2"
    headers = {
        "Host": "bmtcmobileapi.karnataka.gov.in",
        "Connection": "keep-alive",
        "Accept": "application/json, text/plain, */*",
        "User-Agent": "Mozilla/5.0",
        "lan": "en",
        "deviceType": "WEB",
        "Origin": "https://www.mybmtc.com",
        "Referer": "https://www.mybmtc.com/",
        "Accept-Language": "en-US,en;q=0.9",
        "Content-Type": "application/json"
    }
    payload = {"routetext": routetext}

    try:
        response = requests.post(url, json=payload, headers=headers, timeout=10)
        response.raise_for_status()
        data = response.json()
        routes = []
        items = data.get("data", data.get("Data", [])) or []

        for item in items:
            if item.get("responsecode") == 200:
                routes.append({
                    "routeno": _extract_routeno(item),
                    "routeparentid": str(item.get("routeparentid", "")),
                    "fromstation": item.get("fromstation") or item.get("from") or "",
                    "tostation": item.get("tostation") or item.get("to") or "",
                    "servicetype": item.get("servicetype", "")
                })

        if not routes:
            # API reachable but nothing matched — nothing to fall back to
            return jsonify({"routes": [], "fallback": False})

        return jsonify({"routes": routes[:10], "fallback": False})

    except Exception as e:
        # Live API unreachable (network block / downtime) → offline catalog
        print(f"BMTC API unavailable ({e}) — serving offline fallback catalog", flush=True)
        return jsonify({
            "routes": search_catalog(routetext=routetext),
            "fallback": True,
        })

# ------------------- GET ROUTE STOPS ---------------------------
@ticket_collector_bp.route("/api/get-route-stops", methods=["GET"])
@require_role("conductor", "admin")
def get_route_stops():
    """
    Query params:
      - routeparentid (required)
      - routeno (optional, stored on the tracking doc for display)

    Side effect: creates the passenger_tracking document for this route
    variant the first time a conductor loads it.
    """
    routeparentid = request.args.get("routeparentid")
    routeno = request.args.get("routeno")

    if not routeparentid:
        return jsonify({"error": "routeparentid required"}), 400

    routeparentid_str = str(routeparentid)

    # If tracking already exists, serve its stops without re-geocoding
    existing_tracking = passenger_tracking_collection.find_one({"routeparentid": routeparentid_str})
    if existing_tracking and existing_tracking.get("stops"):
        if (not existing_tracking.get("routeno")) and routeno:
            passenger_tracking_collection.update_one(
                {"routeparentid": routeparentid_str},
                {"$set": {"routeno": routeno, "updatedAt": datetime.now()}},
            )
        return jsonify({
            "stops": [s["name"] for s in existing_tracking["stops"]],
            "cached": True,
            "vehicle": existing_tracking.get("vehicle", ""),
            "trips": existing_tracking.get("trips", []),
        })

    # Catalog routes (real BMTC sample data): no GPS/geocoding pipeline needed
    canned_stops = catalog_stops(routeparentid_str)
    if canned_stops is not None:
        catalog_entry = catalog_route(routeparentid_str) or {}
        stop_data = [
            {"name": name, "boarded": 0, "departed": 0, "crowding": 0, "time": "Not yet tracked"}
            for name in canned_stops
        ]
        passenger_tracking_collection.update_one(
            {"routeparentid": routeparentid_str},
            {
                "$set": {
                    "routeno": routeno or catalog_entry.get("routeno", ""),
                    "routeparentid": routeparentid_str,
                    "stops": stop_data,
                    "vehicle": catalog_entry.get("vehicle", ""),
                    "trips": catalog_entry.get("trips", []),
                    "currentPassengers": 0,
                    "capacity": 80,
                    "overcrowdingIndex": 0,
                    "overcrowdingLevel": "LOW",
                    "status": "Active",
                    "createdAt": datetime.now(),
                }
            },
            upsert=True,
        )
        return jsonify({
            "stops": canned_stops,
            "cached": False,
            "fallback": True,
            "vehicle": catalog_entry.get("vehicle", ""),
            "trips": catalog_entry.get("trips", []),
        })

    url = "https://bmtcmobileapi.karnataka.gov.in/WebAPI/RoutePoints"
    headers = {
        "Host": "bmtcmobileapi.karnataka.gov.in",
        "Connection": "keep-alive",
        "Accept": "application/json, text/plain, */*",
        "User-Agent": "Mozilla/5.0",
        "lan": "en",
        "deviceType": "WEB",
        "Origin": "https://www.mybmtc.com",
        "Referer": "https://www.mybmtc.com/",
        "Accept-Language": "en-US,en;q=0.9",
        "Content-Type": "application/json"
    }
    payload = {"routeid": int(routeparentid)}

    try:
        print(f"Fetching route points for routeid: {routeparentid_str}, routeno: {routeno}")
        response = requests.post(url, json=payload, headers=headers, timeout=15)
        response.raise_for_status()
        data = response.json()

        points = []
        items = data.get("data", data.get("Data", [])) or []
        for item in items:
            if item.get("responsecode") == 200:
                lat = item.get("latitude")
                lon = item.get("longitude")
                if lat and lon:
                    points.append({"latitude": lat, "longitude": lon})

        if not points:
            return jsonify({"error": "No GPS points found"}), 404

        filtered_points = filter_points_by_distance(points, min_distance_km=2.0)

        stops_for_collector = []
        for idx, point in enumerate(filtered_points):
            stops_for_collector.append(geocode_coordinates(point["latitude"], point["longitude"]))
            # Nominatim rate limit: max 1 req/sec
            if idx < len(filtered_points) - 1:
                time.sleep(1.1)

        stop_data = [
            {"name": name, "boarded": 0, "departed": 0, "crowding": 0, "time": "Not yet tracked"}
            for name in stops_for_collector
        ]

        passenger_tracking_collection.update_one(
            {"routeparentid": routeparentid_str},
            {
                "$set": {
                    "routeno": routeno or "",
                    "routeparentid": routeparentid_str,
                    "stops": stop_data,
                    "vehicle": "",
                    "trips": [],
                    "currentPassengers": 0,
                    "capacity": 80,
                    "overcrowdingIndex": 0,
                    "overcrowdingLevel": "LOW",
                    "status": "Active",
                    "createdAt": datetime.now(),
                }
            },
            upsert=True,
        )
        print(f"Created tracking document for route {routeno or '(empty)'} / variant {routeparentid_str}")

        return jsonify({"stops": stops_for_collector, "cached": False})

    except Exception as e:
        print(f"Error in get_route_stops: {str(e)}")
        return jsonify({"error": "BMTC API failed", "details": str(e)}), 500

# ------------------- UPDATE PASSENGER COUNT ---------------------------
@ticket_collector_bp.route("/api/update-passenger", methods=["POST"])
@require_role("conductor", "admin")
def update_passenger():
    data = request.get_json()
    routeparentid = data.get("routeparentid")
    stop_name = data.get("stop_name")
    action = data.get("action")
    count = data.get("count", 1)

    if not all([routeparentid, stop_name, action]):
        return jsonify({"error": "Missing required fields"}), 400

    if action not in ("board", "depart"):
        return jsonify({"error": "Invalid action"}), 400

    try:
        count = max(1, min(50, int(count)))
    except (TypeError, ValueError):
        return jsonify({"error": "count must be an integer"}), 400

    routeparentid_str = str(routeparentid)
    now = datetime.now()

    try:
        tracking = passenger_tracking_collection.find_one({"routeparentid": routeparentid_str})
        if not tracking:
            return jsonify({"error": "Route not found — load stops first"}), 404

        stops = tracking.get("stops", [])
        stop = next((s for s in stops if s["name"] == stop_name), None)
        if stop is None:
            return jsonify({"error": "Stop not found"}), 404

        if action == "board":
            stop["boarded"] += count
        else:
            # Server-side guard: can't depart more people than are on the bus
            # from this stop (frontend checks too, but never trust the client)
            onboard_here = stop["boarded"] - stop["departed"]
            if onboard_here <= 0:
                return jsonify({"error": "No passengers from this stop to depart"}), 400
            count = min(count, onboard_here)
            stop["departed"] += count

        stop["time"] = now.strftime("%I:%M %p")

        current_passengers, oci, oci_level = recompute_and_persist(
            routeparentid_str, stops, tracking, now
        )

        ticketing_logs_collection.insert_one({
            "routeparentid": routeparentid_str,
            "routeno": tracking.get("routeno", ""),
            "stop_name": stop_name,
            "action": action,
            "count": count,
            "timestamp": now,
            "date": now.strftime("%Y-%m-%d"),
            "time": now.strftime("%H:%M:%S"),
        })

        return jsonify({
            "success": True,
            "appliedCount": count,
            "currentPassengers": current_passengers,
            "overcrowdingIndex": oci,
            "overcrowdingLevel": oci_level,
        })

    except Exception as e:
        return jsonify({"error": str(e)}), 500


# ------------------- GET CURRENT TRACKING DATA ---------------------------
@ticket_collector_bp.route("/api/get-tracking", methods=["GET"])
def get_tracking():
    routeparentid = request.args.get("routeparentid")

    if not routeparentid:
        return jsonify({"error": "routeparentid required"}), 400

    try:
        tracking = passenger_tracking_collection.find_one(
            {"routeparentid": str(routeparentid)},
            {"_id": 0}
        )
        if not tracking:
            return jsonify({"error": "No tracking data found"}), 404
        return jsonify(tracking)
    except Exception as e:
        print(f"Error getting tracking: {str(e)}")
        return jsonify({"error": str(e)}), 500
