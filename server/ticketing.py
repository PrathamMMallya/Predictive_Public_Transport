"""
Real-world style bus ticketing.

Flow (mirrors a physical bus):
  1. Passenger boards → conductor ISSUES A TICKET (source → destination).
     The ticket auto-boards that many passengers at the source stop.
  2. Bus reaches a stop → conductor hits ARRIVE-AT-STOP.
     Every ON_BUS ticket whose destination is that stop is completed and
     those passengers auto-alight. Counts update themselves.

Every ticket carries: ticket number, timestamp, vehicle (bus) number, route,
source, destination, passenger count and fare — like a real BMTC ticket.

Ticket issuance also upserts the hourly OCI sample (via tracking_utils), so
passenger-side ARIMA forecasts learn from ticket data automatically.
"""

from datetime import datetime

from flask import Blueprint, jsonify, request
from pymongo import ReturnDocument
from pymongo.errors import DuplicateKeyError

from auth_utils import require_role
from db import (
    passenger_tracking_collection,
    tickets_collection,
    counters_collection,
    ticketing_logs_collection,
)
from gtfs_data import lookup_fare as gtfs_fare
from tracking_utils import recompute_and_persist

ticketing_bp = Blueprint("ticketing", __name__)

# ---------------- FARE ----------------
BASE_FARE = 5        # ₹
FARE_PER_STAGE = 5   # ₹ per stop-to-stop stage
MAX_FARE = 60        # ₹ cap per passenger


def calculate_fare(stages):
    """Flat stage-based fare: ₹5 base + ₹5 per stage, capped."""
    return min(BASE_FARE + FARE_PER_STAGE * max(1, stages), MAX_FARE)


def _next_ticket_seq(routeparentid, date_str):
    """Atomic per-route-per-day sequence → human-readable ticket numbers."""
    doc = counters_collection.find_one_and_update(
        {"_id": f"ticket:{routeparentid}:{date_str}"},
        {"$inc": {"seq": 1}},
        upsert=True,
        return_document=ReturnDocument.AFTER,
    )
    return doc["seq"]


def _ticket_response(ticket):
    ticket = dict(ticket)
    ticket["_id"] = str(ticket["_id"])
    for k in ("issued_at", "completed_at"):
        if ticket.get(k):
            ticket[k] = ticket[k].strftime("%Y-%m-%d %H:%M:%S")
    return ticket


# ------------------- ISSUE TICKET ---------------------------
@ticketing_bp.route("/api/conductor/issue-ticket", methods=["POST"])
@require_role("conductor", "admin")
def issue_ticket():
    data = request.get_json()
    routeparentid = data.get("routeparentid")
    source_stop = data.get("source_stop")
    dest_stop = data.get("dest_stop")
    count = data.get("count", 1)
    client_ref = data.get("client_ref")  # optional idempotency key

    if not all([routeparentid, source_stop, dest_stop]):
        return jsonify({"error": "routeparentid, source_stop and dest_stop required"}), 400

    try:
        count = max(1, min(50, int(count)))
    except (TypeError, ValueError):
        return jsonify({"error": "count must be an integer"}), 400

    routeparentid = str(routeparentid)

    # Idempotent retry: same client_ref → return the original ticket
    if client_ref:
        existing = tickets_collection.find_one({"client_ref": client_ref})
        if existing:
            resp = _ticket_response(existing)
            resp["duplicate"] = True
            return jsonify(resp), 200

    tracking = passenger_tracking_collection.find_one({"routeparentid": routeparentid})
    if not tracking:
        return jsonify({"error": "Route not found — load stops first"}), 404

    stops = tracking.get("stops", [])
    stop_names = [s["name"] for s in stops]
    if source_stop not in stop_names:
        return jsonify({"error": f"Source stop '{source_stop}' is not on this route"}), 400
    if dest_stop not in stop_names:
        return jsonify({"error": f"Destination stop '{dest_stop}' is not on this route"}), 400

    source_idx = stop_names.index(source_stop)
    dest_idx = stop_names.index(dest_stop)
    if dest_idx <= source_idx:
        return jsonify({"error": "Destination must come after source on this route"}), 400

    stages = dest_idx - source_idx

    # Real BMTC fare from the GTFS fare rules when stop ids are known
    # (GTFS routes); stage-based estimate otherwise.
    fare_source = "stage-estimate"
    fare_per_pax = None
    if tracking.get("gtfs_route_id"):
        src_id = stops[source_idx].get("stop_id")
        dst_id = stops[dest_idx].get("stop_id")
        if src_id and dst_id:
            fare_per_pax = gtfs_fare(tracking["gtfs_route_id"], src_id, dst_id)
            if fare_per_pax is not None:
                fare_source = "gtfs"
    if fare_per_pax is None:
        fare_per_pax = calculate_fare(stages)
    fare_per_pax = int(round(fare_per_pax))  # BMTC fares are whole rupees

    now = datetime.now()
    date_str = now.strftime("%Y-%m-%d")

    vehicle = tracking.get("vehicle", "KA00F0000")
    seq = _next_ticket_seq(routeparentid, date_str)
    ticket_no = f"{vehicle}-{now.strftime('%Y%m%d')}-{seq:04d}"

    ticket = {
        "ticket_no": ticket_no,
        "routeparentid": routeparentid,
        "routeno": tracking.get("routeno", ""),
        "vehicle_no": vehicle,
        "source_stop": source_stop,
        "dest_stop": dest_stop,
        "stages": stages,
        "count": count,
        "fare_per_pax": fare_per_pax,
        "fare_source": fare_source,
        "total_fare": fare_per_pax * count,
        "status": "ON_BUS",
        "issued_at": now,
        "completed_at": None,
        "issued_by": request.user.get("user_id"),
        "date": date_str,
        "hour": now.strftime("%Y-%m-%d %H:00"),
    }
    if client_ref:
        ticket["client_ref"] = client_ref

    try:
        result = tickets_collection.insert_one(ticket)
    except DuplicateKeyError:
        # Lost a race on client_ref — return the winner
        existing = tickets_collection.find_one({"client_ref": client_ref})
        resp = _ticket_response(existing)
        resp["duplicate"] = True
        return jsonify(resp), 200

    ticket["_id"] = result.inserted_id

    # ---- AUTO-UPDATE PASSENGER COUNTS: board at source ----
    stops[source_idx]["boarded"] += count
    stops[source_idx]["time"] = now.strftime("%I:%M %p")
    current_passengers, oci, oci_level = recompute_and_persist(
        routeparentid, stops, tracking, now
    )

    ticketing_logs_collection.insert_one({
        "routeparentid": routeparentid,
        "routeno": tracking.get("routeno", ""),
        "stop_name": source_stop,
        "action": "ticket",
        "count": count,
        "ticket_no": ticket_no,
        "timestamp": now,
        "date": date_str,
        "time": now.strftime("%H:%M:%S"),
    })

    resp = _ticket_response(ticket)
    resp.update({
        "currentPassengers": current_passengers,
        "overcrowdingIndex": oci,
        "overcrowdingLevel": oci_level,
    })
    return jsonify(resp), 201


# ------------------- ARRIVE AT STOP (auto-alight) ---------------------------
@ticketing_bp.route("/api/conductor/arrive-stop", methods=["POST"])
@require_role("conductor", "admin")
def arrive_stop():
    data = request.get_json()
    routeparentid = data.get("routeparentid")
    stop_name = data.get("stop_name")

    if not all([routeparentid, stop_name]):
        return jsonify({"error": "routeparentid and stop_name required"}), 400

    routeparentid = str(routeparentid)
    tracking = passenger_tracking_collection.find_one({"routeparentid": routeparentid})
    if not tracking:
        return jsonify({"error": "Route not found"}), 404

    stops = tracking.get("stops", [])
    stop_names = [s["name"] for s in stops]
    if stop_name not in stop_names:
        return jsonify({"error": f"Stop '{stop_name}' is not on this route"}), 400

    now = datetime.now()

    # Complete every ON_BUS ticket destined for this stop
    open_tickets = list(tickets_collection.find({
        "routeparentid": routeparentid,
        "dest_stop": stop_name,
        "status": "ON_BUS",
    }))

    alighted = sum(t["count"] for t in open_tickets)
    if open_tickets:
        tickets_collection.update_many(
            {"_id": {"$in": [t["_id"] for t in open_tickets]}},
            {"$set": {"status": "COMPLETED", "completed_at": now}},
        )

    if alighted:
        idx = stop_names.index(stop_name)
        stops[idx]["departed"] += alighted
        stops[idx]["time"] = now.strftime("%I:%M %p")

    current_passengers, oci, oci_level = recompute_and_persist(
        routeparentid, stops, tracking, now
    )

    return jsonify({
        "stop": stop_name,
        "alighted": alighted,
        "ticketsCompleted": [t["ticket_no"] for t in open_tickets],
        "currentPassengers": current_passengers,
        "overcrowdingIndex": oci,
        "overcrowdingLevel": oci_level,
    })


# ------------------- TICKET DASHBOARD DATA ---------------------------
@ticketing_bp.route("/api/conductor/tickets", methods=["GET"])
@require_role("conductor", "admin")
def list_tickets():
    routeparentid = request.args.get("routeparentid")
    date_str = request.args.get("date") or datetime.now().strftime("%Y-%m-%d")

    if not routeparentid:
        return jsonify({"error": "routeparentid required"}), 400

    routeparentid = str(routeparentid)
    tickets = list(
        tickets_collection.find(
            {"routeparentid": routeparentid, "date": date_str},
            {"client_ref": 0, "issued_by": 0},
        ).sort("issued_at", -1).limit(200)
    )

    summary = {
        "issuedToday": len(tickets),
        "passengersToday": sum(t["count"] for t in tickets),
        "onBus": sum(t["count"] for t in tickets if t["status"] == "ON_BUS"),
        "completed": sum(1 for t in tickets if t["status"] == "COMPLETED"),
        "revenueToday": sum(t["total_fare"] for t in tickets),
    }

    # Hourly issue counts for the dashboard chart (demand curve)
    hourly = {}
    for t in tickets:
        hour = t["issued_at"].strftime("%H:00")
        hourly[hour] = hourly.get(hour, 0) + t["count"]

    return jsonify({
        "tickets": [_ticket_response(t) for t in tickets],
        "summary": summary,
        "hourly": [{"time": h, "passengers": c} for h, c in sorted(hourly.items())],
    })
