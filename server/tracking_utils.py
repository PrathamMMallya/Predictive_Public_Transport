"""
Shared helpers for mutating a route's live tracking state.

Both the manual conductor flow (ticket_collector.update_passenger) and the
ticket system (ticketing.py) MUST update crowding the same way — otherwise
the OCI time series that ARIMA trains on would diverge depending on which
flow wrote it.
"""

from datetime import datetime

from db import passenger_tracking_collection, oci_timeseries_collection


def calculate_overcrowding_index(current_passengers, capacity):
    """OCI (%) = (Current Passengers / Bus Capacity) * 100"""
    if capacity <= 0:
        return 0
    return int((current_passengers / capacity) * 100)


def classify_overcrowding(oci):
    if oci <= 50:
        return "LOW"
    elif oci <= 75:
        return "MEDIUM"
    elif oci <= 100:
        return "HIGH"
    else:
        return "SEVERE"


def typical_oci(hour, rng=None):
    """
    Typical-day OCI profile (Bangalore commute peaks) with optional jitter.
    Used wherever a route has no measured history yet.
    """
    import random as _random

    rng = rng or _random
    if 8 <= hour <= 10:      # morning peak
        base = rng.gauss(85, 8)
    elif 17 <= hour <= 19:   # evening peak
        base = rng.gauss(92, 8)
    elif 12 <= hour <= 13:   # lunch bump
        base = rng.gauss(58, 8)
    else:
        base = rng.gauss(42, 8)
    return max(5, min(130, int(base)))


def recompute_and_persist(routeparentid, stops, tracking, now=None):
    """
    Recompute current passengers + OCI from the stop counters, persist to
    passenger_tracking, and upsert the hourly OCI sample that feeds the
    ARIMA forecasts.

    Returns (current_passengers, oci, oci_level).
    """
    now = now or datetime.now()
    routeparentid = str(routeparentid)

    total_boarded = sum(s["boarded"] for s in stops)
    total_departed = sum(s["departed"] for s in stops)
    current_passengers = total_boarded - total_departed

    capacity = int(tracking.get("capacity", 80))
    oci = calculate_overcrowding_index(current_passengers, capacity)
    oci_level = classify_overcrowding(oci)

    hour_bucket = now.strftime("%Y-%m-%d %H:00")
    oci_timeseries_collection.update_one(
        {"routeparentid": routeparentid, "hour": hour_bucket},
        {
            "$set": {
                "routeparentid": routeparentid,
                "routeno": tracking.get("routeno", ""),
                "hour": hour_bucket,
                "oci": oci,
                "timestamp": now,
            }
        },
        upsert=True,
    )

    passenger_tracking_collection.update_one(
        {"routeparentid": routeparentid},
        {"$set": {
            "stops": stops,
            "currentPassengers": current_passengers,
            "overcrowdingIndex": oci,
            "overcrowdingLevel": oci_level,
            "updatedAt": now,
        }},
    )

    return current_passengers, oci, oci_level
