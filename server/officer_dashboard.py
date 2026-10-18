from datetime import datetime, timedelta

from flask import Blueprint, jsonify, request

from auth_utils import require_role
from db import get_mongo_db
from passenger_dashboard import _hour_of_day_profile, SERVICE_START_HOUR, SERVICE_END_HOUR

mongo = get_mongo_db()
passenger_tracking_col = mongo["passenger_tracking"]
ticketing_logs = mongo["ticketing_logs"]
oci_daily_snapshots = mongo["oci_daily_snapshots"]

officer_dashboard_bp = Blueprint("officer_dashboard", __name__)

BASELINE_TRIPS_PER_HOUR = 2  # what the depot currently runs per route


@officer_dashboard_bp.route("/api/admin/dashboard", methods=["GET"])
@require_role("admin")
def admin_dashboard():
    """Admin view of all active buses and system-level stats."""
    buses = []
    total_passengers_system = 0

    for tracking in passenger_tracking_col.find({}):
        stops = tracking.get("stops", []) or []
        capacity = int(tracking.get("capacity", 80))

        total_boarded = sum(int(s.get("boarded", 0)) for s in stops)
        total_departed = sum(int(s.get("departed", 0)) for s in stops)
        current_passengers = total_boarded - total_departed
        total_passengers_system += current_passengers

        buses.append({
            "routeno": tracking.get("routeno", ""),
            "routeparentid": tracking.get("routeparentid"),
            "stops": stops,
            "currentPassengers": current_passengers,
            "capacity": capacity,
            "overcrowdingIndex": tracking.get("overcrowdingIndex", 0),
            "overcrowdingLevel": tracking.get("overcrowdingLevel", "LOW"),
            "status": tracking.get("status", "Active"),
        })

    buses.sort(key=lambda b: b["overcrowdingIndex"], reverse=True)

    return jsonify({
        "buses": buses,
        "totalBuses": len(buses),
        "totalPassengers": total_passengers_system,
    })


@officer_dashboard_bp.route("/api/admin/reports", methods=["GET"])
@require_role("admin")
def admin_reports():
    period = request.args.get("period", "daily")

    today = datetime.now().date()
    if period == "weekly":
        start = today - timedelta(days=7)
    elif period == "biweekly":
        start = today - timedelta(days=14)
    else:
        start = today

    records = list(oci_daily_snapshots.find(
        {"date": {"$gte": str(start), "$lte": str(today)}},
        {"_id": 0},
    ))

    top_buses = list(oci_daily_snapshots.aggregate([
        {"$match": {"date": {"$gte": str(start), "$lte": str(today)}}},
        {"$group": {
            "_id": "$routeparentid",
            "routeno": {"$first": "$routeno"},
            "avgOCI": {"$avg": "$dailyOCI"},
        }},
        {"$sort": {"avgOCI": -1}},
        {"$limit": 10},
    ]))

    return jsonify({
        "period": period,
        "from": str(start),
        "to": str(today),
        "records": records,
        "topBuses": top_buses,
    })


def _recommend_trips(avg_oci, baseline=BASELINE_TRIPS_PER_HOUR):
    """
    Frequency policy: map average crowding (OCI %) for an hour to how many
    trips per hour should run in that hour.

    Default policy:
        >= 90%  → 4 trips/hr (every 15 min)
        70–89%  → 3 trips/hr (every 20 min)
        45–69%  → keep baseline
        25–44%  → 1 trip/hr
        < 25%   → 1 trip/hr (minimum viable service)

    Tune these bands to match depot policy / fleet size.
    """
    if avg_oci >= 90:
        return 4
    if avg_oci >= 70:
        return 3
    if avg_oci >= 45:
        return baseline
    return 1


@officer_dashboard_bp.route("/api/admin/frequency-plan", methods=["GET"])
@require_role("admin")
def admin_frequency_plan():
    """
    For every tracked route: recommended trips/hour per service hour, derived
    from the last 7 days of observed crowding. This is the admin's input for
    deciding bus frequency — add buses where OCI stays high, cut where empty.
    """
    days = int(request.args.get("days", 7))
    plan = []

    for tracking in passenger_tracking_col.find({}):
        rpid = tracking["routeparentid"]
        profile = _hour_of_day_profile(rpid, days=days)

        hours = []
        current_total = 0
        recommended_total = 0
        for hour in range(SERVICE_START_HOUR, SERVICE_END_HOUR + 1):
            avg_oci = round(profile.get(hour, 0))
            recommended = _recommend_trips(avg_oci)
            hours.append({
                "hour": f"{hour:02d}:00",
                "avgOci": avg_oci,
                "currentTrips": BASELINE_TRIPS_PER_HOUR,
                "recommendedTrips": recommended,
            })
            current_total += BASELINE_TRIPS_PER_HOUR
            recommended_total += recommended

        plan.append({
            "routeno": tracking.get("routeno", ""),
            "routeparentid": rpid,
            "hasHistory": bool(profile),
            "hours": hours,
            "currentDailyTrips": current_total,
            "recommendedDailyTrips": recommended_total,
            "tripDelta": recommended_total - current_total,
        })

    # Routes that need the most extra service first
    plan.sort(key=lambda p: p["tripDelta"], reverse=True)

    return jsonify({
        "baselineTripsPerHour": BASELINE_TRIPS_PER_HOUR,
        "days": days,
        "plan": plan,
    })
