"""
GTFS-backed API: route search, source→destination search, stop timetables,
route shapes, live (simulated) tracking, predict-at-time, admin insights.

Tracking docs for GTFS routes use routeparentid = "gtfs:{route_id}:{direction}"
so they coexist with the sample-catalog routes.
"""

import math
from datetime import datetime, timedelta

from flask import Blueprint, jsonify, request

import gtfs_data as g
import simulator
from arima_predictor import predict_full_day
from auth_utils import require_role
from db import (
    passenger_tracking_collection,
    oci_timeseries_collection,
    ticketing_logs_collection,
)
from history_seed import ensure_history
from officer_dashboard import _recommend_trips
from passenger_dashboard import _hourly_history, _hour_of_day_profile
from prophet_predictor import predict_prophet
from tracking_utils import classify_overcrowding

gtfs_bp = Blueprint("gtfs", __name__)

DEFAULT_CAPACITY = 80


def rpid_for(route_id, direction_id):
    return f"gtfs:{route_id}:{direction_id}"


def _real_oci_for(rpid):
    """Real conductor-driven OCI when today's ticketing exists, else None."""
    today = datetime.now().strftime("%Y-%m-%d")
    if not ticketing_logs_collection.find_one({"routeparentid": rpid, "date": today}):
        return None
    tracking = passenger_tracking_collection.find_one({"routeparentid": rpid})
    if not tracking:
        return None
    return tracking.get("overcrowdingIndex", 0)


# -------------------------------------------------
# SEARCH
# -------------------------------------------------
@gtfs_bp.route("/api/gtfs/search", methods=["GET"])
def gtfs_search():
    routetext = request.args.get("routetext", "").strip()
    if not routetext:
        return jsonify({"error": "routetext required"}), 400
    return jsonify({"routes": g.search_routes(routetext), "source": "gtfs"})


@gtfs_bp.route("/api/gtfs/stops-autocomplete", methods=["GET"])
def gtfs_stops_autocomplete():
    q = request.args.get("q", "").strip()
    if len(q) < 2:
        return jsonify({"stops": []})
    return jsonify({"stops": g.stops_autocomplete(q)})


@gtfs_bp.route("/api/gtfs/routes-between", methods=["GET"])
def gtfs_routes_between():
    source = request.args.get("source", "").strip()
    dest = request.args.get("dest", "").strip()
    if not source or not dest:
        return jsonify({"error": "source and dest required"}), 400
    routes = g.routes_between(source, dest)
    return jsonify({"routes": routes, "source": "gtfs", "count": len(routes)})


# -------------------------------------------------
# ROUTE DETAIL
# -------------------------------------------------
@gtfs_bp.route("/api/gtfs/route-stops", methods=["GET"])
def gtfs_route_stops():
    route_id = request.args.get("route_id")
    direction = int(request.args.get("direction", 0))
    if not route_id:
        return jsonify({"error": "route_id required"}), 400

    data = g.route_stops(route_id, direction)
    if not data["stops"]:
        return jsonify({"error": "No stops found for this route/direction"}), 404

    rpid = rpid_for(route_id, direction)
    tracking = passenger_tracking_collection.find_one({"routeparentid": rpid})
    current_oci = tracking.get("overcrowdingIndex", 0) if tracking else 0

    return jsonify({
        **data,
        "route_id": route_id,
        "direction": direction,
        "current": {
            "oci": current_oci,
            "level": classify_overcrowding(current_oci),
            "passengers": tracking.get("currentPassengers", 0) if tracking else 0,
            "capacity": DEFAULT_CAPACITY,
        },
    })


@gtfs_bp.route("/api/gtfs/route-shape", methods=["GET"])
def gtfs_route_shape():
    route_id = request.args.get("route_id")
    direction = int(request.args.get("direction", 0))
    if not route_id:
        return jsonify({"error": "route_id required"}), 400
    return jsonify({"shape": g.route_shape(route_id, direction)})


# -------------------------------------------------
# LIVE (SIMULATED) TRACKING
# -------------------------------------------------
@gtfs_bp.route("/api/gtfs/live", methods=["GET"])
def gtfs_live():
    route_id = request.args.get("route_id")
    direction = int(request.args.get("direction", 0))
    if not route_id:
        return jsonify({"error": "route_id required"}), 400

    real_oci = _real_oci_for(rpid_for(route_id, direction))
    return jsonify({
        "route_id": route_id,
        "direction": direction,
        "server_time": datetime.now().strftime("%H:%M:%S"),
        "realTracking": real_oci is not None,
        **simulator.live_buses(route_id, direction, include_real_oci=real_oci),
    })


# -------------------------------------------------
# CONDUCTOR: load a GTFS route for ticketing
# -------------------------------------------------
@gtfs_bp.route("/api/conductor/load-gtfs-route", methods=["POST"])
@require_role("conductor", "admin")
def load_gtfs_route():
    data = request.get_json()
    route_id = data.get("route_id")
    direction = int(data.get("direction", 0))
    if not route_id:
        return jsonify({"error": "route_id required"}), 400

    stops_data = g.route_stops(route_id, direction)
    if not stops_data["stops"]:
        return jsonify({"error": "No stops found for this route/direction"}), 404

    rpid = rpid_for(route_id, direction)
    routeno = stops_data["stops"][0] and (data.get("routeno") or "")

    # Scheduled start times of today's trips (for the passenger view)
    _, trips = simulator.scheduled_trips_today(route_id, direction)
    trip_times = [t["start"] for t in trips if t.get("start")]

    # Vehicle: first live trip's vehicle, else a deterministic one
    vehicle = None
    live = simulator.live_buses(route_id, direction)
    if live["buses"]:
        vehicle = live["buses"][0]["vehicle"]
    elif trips:
        vehicle = simulator.vehicle_for_trip(trips[0]["trip_id"])

    stop_docs = [
        {
            "name": s["name"],
            "stop_id": s["stop_id"],
            "boarded": 0,
            "departed": 0,
            "crowding": 0,
            "time": "Not yet tracked",
        }
        for s in stops_data["stops"]
    ]

    passenger_tracking_collection.update_one(
        {"routeparentid": rpid},
        {
            "$set": {
                "routeno": routeno,
                "routeparentid": rpid,
                "gtfs_route_id": route_id,
                "direction": direction,
                "stops": stop_docs,
                "vehicle": vehicle or "",
                "trips": trip_times,
                "currentPassengers": 0,
                "capacity": DEFAULT_CAPACITY,
                "overcrowdingIndex": 0,
                "overcrowdingLevel": "LOW",
                "status": "Active",
                "createdAt": datetime.now(),
            }
        },
        upsert=True,
    )

    ensure_history(rpid, routeno)

    return jsonify({
        "stops": [s["name"] for s in stops_data["stops"]],
        "stop_ids": [s["stop_id"] for s in stops_data["stops"]],
        "vehicle": vehicle,
        "trips": trip_times,
        "routeparentid": rpid,
    })


# -------------------------------------------------
# PASSENGER: PREDICT CROWDING AT A SPECIFIC TIME
# -------------------------------------------------
@gtfs_bp.route("/api/passenger/predict", methods=["POST"])
def passenger_predict():
    """
    Body: {route_id, direction, target_time: "HH:MM", model: "arima"|"prophet"}

    Trains the chosen model on the route's hourly OCI history (7 days,
    lazily seeded on first use) and returns the predicted crowding at the
    requested time today, plus scheduled trips around it with their
    predicted crowding — so the passenger can pick a better bus.
    """
    payload = request.get_json()
    route_id = payload.get("route_id")
    direction = int(payload.get("direction", 0))
    target_time = payload.get("target_time")
    model_name = (payload.get("model") or "arima").lower()

    if not route_id or not target_time:
        return jsonify({"error": "route_id and target_time required"}), 400
    if model_name not in ("arima", "prophet"):
        return jsonify({"error": "model must be 'arima' or 'prophet'"}), 400

    try:
        hh, mm = int(target_time.split(":")[0]), int(target_time.split(":")[1])
    except (ValueError, IndexError):
        return jsonify({"error": "target_time must be HH:MM"}), 400

    now = datetime.now()
    target_dt = now.replace(hour=hh, minute=mm, second=0, microsecond=0)
    if target_dt <= now:
        target_dt += timedelta(days=1)  # "at 08:00" at 20:00 means tomorrow

    rpid = rpid_for(route_id, direction)
    tracking = passenger_tracking_collection.find_one({"routeparentid": rpid})
    routeno = (tracking or {}).get("routeno", "")

    ensure_history(rpid, routeno)

    history = _hourly_history(rpid, days=7)
    if len(history) < 2:
        return jsonify({"error": "Not enough history to forecast for this route"}), 400

    hours_ahead = max(1, math.ceil((target_dt - now).total_seconds() / 3600))
    steps = min(hours_ahead + 2, 48)

    if model_name == "prophet":
        series_ts = [
            (datetime.strptime(hour_str, "%Y-%m-%d %H:%M"), oci)
            for hour_str, oci in history
        ]
        forecast = predict_prophet(series_ts, steps, cache_key=f"{rpid}:{steps}")
    else:
        forecast = predict_full_day([oci for _, oci in history], steps=steps)

    predicted_at_target = forecast[hours_ahead - 1] if hours_ahead - 1 < len(forecast) else forecast[-1]

    # Forecast points with clock times (for the chart)
    forecast_points = []
    for i, oci in enumerate(forecast[:hours_ahead + 1]):
        t = now + timedelta(hours=i + 1)
        forecast_points.append({"time": t.strftime("%H:%M"), "oci": oci})

    # Scheduled trips within ±90 min of target, scored by predicted crowding
    trips_near = []
    _, all_trips = simulator.scheduled_trips_today(route_id, direction)
    for trip in all_trips:
        try:
            th, tm = int(trip["start"].split(":")[0]), int(trip["start"].split(":")[1])
        except (ValueError, IndexError, AttributeError):
            continue
        trip_dt = now.replace(hour=th, minute=tm, second=0, microsecond=0)
        if abs((trip_dt - target_dt).total_seconds()) > 90 * 60:
            continue
        t_ahead = max(1, math.ceil((trip_dt - now).total_seconds() / 3600))
        t_oci = forecast[t_ahead - 1] if t_ahead - 1 < len(forecast) else predicted_at_target
        trips_near.append({
            "trip_id": trip["trip_id"],
            "start": trip["start"],
            "predicted_oci": t_oci,
            "level": classify_overcrowding(t_oci),
            "minutes_from_target": round((trip_dt - target_dt).total_seconds() / 60),
        })
    trips_near.sort(key=lambda t: t["predicted_oci"])

    suggestion = None
    if trips_near:
        best_trip = trips_near[0]
        if best_trip["predicted_oci"] < predicted_at_target:
            suggestion = (
                f"Crowding at {target_time} is expected "
                f"{classify_overcrowding(predicted_at_target)} (~{predicted_at_target}%). "
                f"Consider the {best_trip['start']} trip instead — expected "
                f"{best_trip['level']} (~{best_trip['predicted_oci']}%)."
            )
        else:
            suggestion = (
                f"Crowding at {target_time} is expected "
                f"{classify_overcrowding(predicted_at_target)} (~{predicted_at_target}%). "
                f"The {best_trip['start']} trip is your best nearby option."
            )

    history_tail = [
        {"time": hour_str.split(" ")[1], "oci": oci} for _, (hour_str, oci) in enumerate(history[-24:])
    ]

    return jsonify({
        "route_id": route_id,
        "direction": direction,
        "routeno": routeno,
        "model": model_name,
        "target_time": target_time,
        "predicted_oci": predicted_at_target,
        "level": classify_overcrowding(predicted_at_target),
        "forecast": forecast_points,
        "history": history_tail,
        "trips_near": trips_near,
        "suggestion": suggestion,
    })


# -------------------------------------------------
# ADMIN: PER-BUS INSIGHTS
# -------------------------------------------------
@gtfs_bp.route("/api/admin/bus-insights", methods=["GET"])
@require_role("admin")
def admin_bus_insights():
    route_id = request.args.get("route_id")
    direction = int(request.args.get("direction", 0))
    if not route_id:
        return jsonify({"error": "route_id required"}), 400

    rpid = rpid_for(route_id, direction)
    tracking = passenger_tracking_collection.find_one({"routeparentid": rpid})
    routeno = (tracking or {}).get("routeno", "")

    ensure_history(rpid, routeno)

    # live state
    real_oci = _real_oci_for(rpid)
    live = simulator.live_buses(route_id, direction, include_real_oci=real_oci)

    # today's observed OCI
    today_str = datetime.now().strftime("%Y-%m-%d")
    today_series = [
        {"time": d["hour"].split(" ")[1], "oci": d["oci"]}
        for d in oci_timeseries_collection.find(
            {"routeparentid": rpid, "hour": {"$regex": f"^{today_str}"}}
        ).sort("hour", 1)
    ]

    # 7-day hourly profile + frequency comparison
    profile = _hour_of_day_profile(rpid, days=7)
    scheduled_per_hour, trips = simulator.scheduled_trips_today(route_id, direction)

    frequency = []
    total_sched = 0
    total_rec = 0
    for hour in range(6, 23):
        avg_oci = round(profile.get(hour, 0))
        sched = scheduled_per_hour.get(hour, 0)
        rec = _recommend_trips(avg_oci, baseline=max(1, sched or 1))
        frequency.append({
            "hour": f"{hour:02d}:00",
            "avgOci": avg_oci,
            "scheduledTrips": sched,
            "recommendedTrips": rec,
        })
        total_sched += sched
        total_rec += rec

    # ---- decision insights (rule-based, explainable) ----
    insights = []
    if profile:
        peak_hour = max(profile, key=profile.get)
        peak_oci = round(profile[peak_hour])
        if peak_oci >= 90:
            insights.append({
                "type": "critical",
                "text": f"Peak crowding {peak_oci}% at {peak_hour:02d}:00 — buses leaving full. "
                        f"Add {max(1, _recommend_trips(peak_oci) - scheduled_per_hour.get(peak_hour, 0))} trip(s) in this hour.",
            })
        quiet = [h for h in range(6, 23) if profile.get(h, 100) < 30 and scheduled_per_hour.get(h, 0) > 0]
        if quiet:
            insights.append({
                "type": "saving",
                "text": f"Light load (<30% OCI) with scheduled service at "
                        f"{', '.join(f'{h:02d}:00' for h in quiet[:4])} — candidates to trim frequency.",
            })
        avg_daily = round(sum(profile.values()) / len(profile))
        insights.append({
            "type": "info",
            "text": f"Average crowding {avg_daily}% across the service day over the last 7 days; "
                    f"{len(trips)} trips scheduled today ({total_sched} trip-hours vs {total_rec} recommended).",
        })
    if live["buses"]:
        worst = max(live["buses"], key=lambda b: b["oci"])
        insights.append({
            "type": "live",
            "text": f"{len(live['buses'])} bus(es) on the road now; highest crowding "
                    f"{worst['oci']}% on {worst['vehicle']} near {worst.get('next_stop') or 'terminus'}.",
        })
    else:
        insights.append({
            "type": "live",
            "text": "No buses on the road right now per the schedule"
                    + (f"; next departure {live['upcoming'][0]['start']} "
                       f"(in {live['upcoming'][0]['in_min']} min)." if live["upcoming"] else "."),
        })

    shape = g.route_shape(route_id, direction)
    stops_data = g.route_stops(route_id, direction)

    return jsonify({
        "route_id": route_id,
        "direction": direction,
        "routeno": routeno,
        "vehicle": (tracking or {}).get("vehicle", ""),
        "live": live,
        "today_series": today_series,
        "profile_7d": [{"hour": f"{h:02d}:00", "avgOci": round(profile.get(h, 0))} for h in range(6, 23)],
        "frequency": frequency,
        "totals": {"scheduled": total_sched, "recommended": total_rec, "delta": total_rec - total_sched},
        "insights": insights,
        "shape": shape,
        "stops": [
            {"name": s["name"], "lat": s["lat"], "lon": s["lon"]}
            for s in stops_data["stops"]
        ],
    })
