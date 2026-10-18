import math
from datetime import datetime, timedelta

import requests
from flask import Blueprint, jsonify, request

from arima_predictor import predict_full_day, predict_next_hour
from bmtc_data import search_catalog
from db import (
    passenger_tracking_collection,
    oci_timeseries_collection,
    oci_daily_snapshots_collection,
)
from tracking_utils import classify_overcrowding

passenger_dashboard_bp = Blueprint("passenger_dashboard", __name__)

SERVICE_START_HOUR = 8   # 08:00
SERVICE_END_HOUR = 20    # 20:00
DEFAULT_CAPACITY = 80

# How many OCI points an hour of waiting is "worth" when scoring departure
# times. 5 ⇒ you'd wait 1 extra hour only if it makes the bus >5% emptier.
# Tune this to change how strongly recommendations prefer sooner departures.
WAIT_PENALTY_PER_HOUR = 5


# -------------------------------------------------
# HELPER: Robust Route Number Extraction
# -------------------------------------------------
def _extract_routeno(item):
    keys = [
        "routeno", "route_no", "routeNo", "routecode", "routeCode",
        "ROUTE_NO", "routenumber", "route_no_text", "RouteNo", "routeNoDisplay",
    ]
    for k in keys:
        val = item.get(k)
        if val and str(val).strip():
            return str(val).strip()
    return ""


# -------------------------------------------------
# HELPER: Typical crowding profile (fallback only)
# -------------------------------------------------
def _typical_oci(hour):
    """Deterministic typical-day OCI used ONLY when a route has no history yet."""
    if 8 <= hour <= 10:
        return 85   # morning peak
    if 17 <= hour <= 19:
        return 90   # evening peak
    if 12 <= hour <= 13:
        return 55   # lunch bump
    return 40


# -------------------------------------------------
# HELPER: Historical hourly series for a route
# -------------------------------------------------
def _hourly_history(routeparentid, days=7):
    """
    Returns [(hour_bucket_str, oci), ...] as a CONTIGUOUS hourly series over
    the last `days` days, built from daily snapshots (past days) plus today's
    live samples. Missing hours (nights, no-service gaps) are filled with the
    route's own hour-of-day average — ARIMA and Prophet both assume evenly
    spaced series, and a 23h hole otherwise wrecks the fit.
    """
    raw = {}
    cutoff = str(datetime.now().date() - timedelta(days=days))

    for snap in oci_daily_snapshots_collection.find(
        {"routeparentid": routeparentid, "date": {"$gte": cutoff}},
        {"_id": 0, "hourlyOCI": 1},
    ):
        for h in snap.get("hourlyOCI", []):
            raw[h["hour"]] = h["oci"]

    today_str = str(datetime.now().date())
    for doc in oci_timeseries_collection.find(
        {"routeparentid": routeparentid, "hour": {"$regex": f"^{today_str}"}},
        {"_id": 0, "hour": 1, "oci": 1},
    ):
        raw[doc["hour"]] = doc["oci"]  # today's live values win

    if not raw:
        return []

    # hour-of-day profile from observed values (for gap filling)
    hod_sum, hod_cnt = {}, {}
    for hour_str, oci in raw.items():
        h = int(hour_str.split(" ")[1].split(":")[0])
        hod_sum[h] = hod_sum.get(h, 0) + oci
        hod_cnt[h] = hod_cnt.get(h, 0) + 1
    hod_avg = {h: hod_sum[h] / hod_cnt[h] for h in hod_sum}
    overall = sum(hod_sum.values()) / max(1, sum(hod_cnt.values()))

    series = []
    t = datetime.now().replace(minute=0, second=0, microsecond=0) - timedelta(days=days)
    end = datetime.now().replace(minute=0, second=0, microsecond=0)
    while t <= end:
        key = t.strftime("%Y-%m-%d %H:00")
        oci = raw.get(key)
        if oci is None:
            oci = round(hod_avg.get(t.hour, overall))
        series.append((key, int(oci)))
        t += timedelta(hours=1)
    return series


def _hour_of_day_profile(routeparentid, days=7):
    """Average OCI per hour-of-day over recent history: {hour_int: avg_oci}."""
    totals, counts = {}, {}
    for hour_bucket, oci in _hourly_history(routeparentid, days):
        hour = int(hour_bucket.split(" ")[1].split(":")[0])
        totals[hour] = totals.get(hour, 0) + oci
        counts[hour] = counts.get(hour, 0) + 1
    return {h: totals[h] / counts[h] for h in totals}


# -------------------------------------------------
# API 1: SEARCH ROUTE VARIANTS (BMTC) + source/dest filter
# -------------------------------------------------
@passenger_dashboard_bp.route("/api/passenger/search-routes", methods=["GET"])
def search_routes_for_passenger():
    routetext = request.args.get("routetext")
    source = (request.args.get("source") or "").strip().lower()
    dest = (request.args.get("dest") or "").strip().lower()

    if not routetext and not (source and dest):
        return jsonify({"error": "routetext or source+dest required"}), 400

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
        "Content-Type": "application/json",
    }

    try:
        # BMTC searches by route text; with only source/dest we probe with the
        # source text so the API still returns candidate routes to filter.
        payload = {"routetext": routetext or source}
        response = requests.post(url, json=payload, headers=headers, timeout=10)
        response.raise_for_status()

        data = response.json()
        items = data.get("data") or data.get("Data") or []

        routes = []
        for item in items:
            if item.get("responsecode") == 200:
                routes.append({
                    "routeno": _extract_routeno(item),
                    "routeparentid": str(item.get("routeparentid", "")),
                    "fromstation": item.get("fromstation") or item.get("from", ""),
                    "tostation": item.get("tostation") or item.get("to", ""),
                    "servicetype": item.get("servicetype", ""),
                })

        # Filter by source/destination station names when provided
        if source:
            routes = [r for r in routes if source in r["fromstation"].lower()] or routes
        if dest:
            routes = [r for r in routes if dest in r["tostation"].lower()] or routes

        return jsonify({"routes": routes[:10], "fallback": False})

    except Exception as e:
        # Live API unreachable (network block / downtime) → offline catalog
        print(f"BMTC API unavailable ({e}) — serving offline fallback catalog", flush=True)
        return jsonify({
            "routes": search_catalog(routetext=routetext, source=source, dest=dest),
            "fallback": True,
        })


# -------------------------------------------------
# API 2: GET CROWDING DATA (real history, synthetic fallback)
# -------------------------------------------------
@passenger_dashboard_bp.route("/api/passenger/crowding", methods=["POST"])
def passenger_crowding():
    data = request.get_json()
    routeno = data.get("routeno")
    routeparentid = data.get("routeparentid")

    if not routeparentid:
        return jsonify({"error": "routeparentid required"}), 400

    tracking = passenger_tracking_collection.find_one({"routeparentid": str(routeparentid)})
    capacity = int(tracking.get("capacity", DEFAULT_CAPACITY)) if tracking else DEFAULT_CAPACITY

    today_str = str(datetime.now().date())
    today_samples = {
        int(d["hour"].split(" ")[1].split(":")[0]): d["oci"]
        for d in oci_timeseries_collection.find(
            {"routeparentid": str(routeparentid), "hour": {"$regex": f"^{today_str}"}}
        )
    }
    history_profile = _hour_of_day_profile(str(routeparentid))

    dataset = []
    used_fallback_only = not today_samples and not history_profile

    for hour in range(SERVICE_START_HOUR, SERVICE_END_HOUR + 1):
        if hour in today_samples:
            oci = today_samples[hour]                 # observed today (live)
        elif hour in history_profile:
            oci = round(history_profile[hour])        # historical average
        else:
            oci = _typical_oci(hour)                  # typical-day fallback

        dataset.append({
            "time": f"{hour:02d}:00",
            "passengers": int(round(oci * capacity / 100)),
            "oci": oci,
        })

    current_oci = tracking.get("overcrowdingIndex", 0) if tracking else 0

    return jsonify({
        "routeno": routeno,
        "routeparentid": routeparentid,
        "dataset": dataset,
        "synthetic": used_fallback_only,
        "current": {
            "passengers": tracking.get("currentPassengers", 0) if tracking else 0,
            "capacity": capacity,
            "oci": current_oci,
            "level": classify_overcrowding(current_oci),
        },
    })


# -------------------------------------------------
# API 3: FORECAST (ARIMA on real history)
# -------------------------------------------------
@passenger_dashboard_bp.route("/api/passenger/forecast", methods=["POST"])
def passenger_forecast():
    payload = request.get_json()
    routeparentid = payload.get("routeparentid")
    dataset = payload.get("dataset")
    steps = int(payload.get("steps", 13))

    # Preferred: forecast from the stored hourly history for this route
    if routeparentid:
        series = [oci for _, oci in _hourly_history(str(routeparentid), days=7)]
        if len(series) >= 2:
            return jsonify({"forecast": predict_full_day(series, steps=steps)})

    # Backward compatible: forecast from a client-supplied dataset
    if dataset and isinstance(dataset, list):
        values = [d.get("oci", d.get("passengers")) for d in dataset]
        return jsonify({"forecast": predict_full_day(values, steps=steps)})

    return jsonify({"error": "routeparentid or dataset required"}), 400


# -------------------------------------------------
# API 4: BOARDING RECOMMENDATION — the core feature
# -------------------------------------------------
def _score_departure(predicted_oci, hours_ahead):
    """
    Score one departure option: lower is better.

    predicted_oci : forecast crowding (%) at that hour
    hours_ahead   : how long the passenger must wait until that departure

    Default policy: crowding + a small penalty per hour of waiting.
    """
    return predicted_oci + WAIT_PENALTY_PER_HOUR * hours_ahead


@passenger_dashboard_bp.route("/api/passenger/recommend", methods=["POST"])
def passenger_recommend():
    """
    Body: { "routeparentids": ["123", "124"], "horizon_hours": 6 }

    For each route variant: current crowding, per-hour forecast, and the best
    time to board. Variants are ranked best-first, so the passenger knows
    WHICH bus and AT WHAT TIME to board for the least congestion.
    """
    payload = request.get_json()
    routeparentids = payload.get("routeparentids") or []
    horizon = int(payload.get("horizon_hours", 6))
    horizon = max(1, min(12, horizon))

    if not routeparentids:
        return jsonify({"error": "routeparentids required"}), 400

    now = datetime.now()
    options = []

    for rpid in routeparentids:
        rpid = str(rpid)
        tracking = passenger_tracking_collection.find_one({"routeparentid": rpid})
        routeno = (tracking or {}).get("routeno", "")
        capacity = int((tracking or {}).get("capacity", DEFAULT_CAPACITY))
        current_oci = (tracking or {}).get("overcrowdingIndex", 0)
        scheduled_trips = (tracking or {}).get("trips", []) or []

        history = [oci for _, oci in _hourly_history(rpid, days=7)]

        if len(history) >= 2:
            forecast = predict_full_day(history, steps=horizon)
        else:
            # No history: use the typical profile for the upcoming hours
            forecast = [_typical_oci((now.hour + i) % 24) for i in range(1, horizon + 1)]

        # Hourly candidates (always available)
        hourly = []
        for i, oci in enumerate(forecast):
            depart_at = (now + timedelta(hours=i + 1)).replace(minute=0, second=0, microsecond=0)
            hourly.append({
                "departAt": depart_at.strftime("%H:%M"),
                "hoursAhead": i + 1,
                "predictedOci": oci,
                "predictedLevel": classify_overcrowding(oci),
                "score": _score_departure(oci, i + 1),
                "scheduled": False,
            })

        # Scheduled-trip candidates from the real timetable (when the route
        # has one) — snapped to the forecast of the hour they depart in
        scheduled = []
        for trip in scheduled_trips:
            try:
                hh, mm = int(trip.split(":")[0]), int(trip.split(":")[1])
            except (ValueError, IndexError):
                continue
            depart_dt = now.replace(hour=hh, minute=mm, second=0, microsecond=0)
            if depart_dt <= now:
                continue  # only future departures
            hours_ahead = max(1, math.ceil((depart_dt - now).total_seconds() / 3600))
            if hours_ahead > horizon:
                continue
            idx = min(hours_ahead - 1, len(forecast) - 1)
            oci = forecast[idx] if forecast else _typical_oci(depart_dt.hour)
            scheduled.append({
                "departAt": trip,
                "hoursAhead": hours_ahead,
                "predictedOci": oci,
                "predictedLevel": classify_overcrowding(oci),
                "score": _score_departure(oci, hours_ahead),
                "scheduled": True,
            })

        # Prefer real scheduled trips; fall back to hourly when none exist
        candidates = scheduled if scheduled else hourly
        best = min(candidates, key=lambda c: c["score"]) if candidates else None

        options.append({
            "routeparentid": rpid,
            "routeno": routeno,
            "vehicle": (tracking or {}).get("vehicle", ""),
            "currentOci": current_oci,
            "currentLevel": classify_overcrowding(current_oci),
            "currentPassengers": (tracking or {}).get("currentPassengers", 0),
            "capacity": capacity,
            "hourlyForecast": hourly,
            "scheduledTrips": scheduled,
            "best": best,
        })

    # Rank: lowest best-score first (least crowded option overall)
    options.sort(key=lambda o: o["best"]["score"] if o["best"] else 9999)

    suggestion = None
    if options and options[0]["best"]:
        top = options[0]
        trip_note = " (scheduled trip)" if top["best"].get("scheduled") else ""
        vehicle_note = f" · {top['vehicle']}" if top.get("vehicle") else ""
        suggestion = (
            f"Board bus {top['routeno'] or top['routeparentid']}{vehicle_note} at "
            f"{top['best']['departAt']}{trip_note} — expected crowding "
            f"{top['best']['predictedLevel']} (~{top['best']['predictedOci']}%)."
        )

    return jsonify({"options": options, "suggestion": suggestion})


# -------------------------------------------------
# API 5: LIVE OVERCROWDING + next-hour prediction
# -------------------------------------------------
@passenger_dashboard_bp.route("/api/passenger/overcrowding", methods=["GET"])
def passenger_overcrowding():
    routeparentid = request.args.get("routeparentid")

    if not routeparentid:
        return jsonify({"error": "routeparentid required"}), 400

    series = _hourly_history(str(routeparentid), days=2)
    if not series:
        return jsonify({"error": "No data yet for this route"}), 404

    values = [oci for _, oci in series]
    tracking = passenger_tracking_collection.find_one({"routeparentid": str(routeparentid)})

    return jsonify({
        "routeno": (tracking or {}).get("routeno", ""),
        "timeseries": values,
        "predicted_next_hour": predict_next_hour(values),
    })
