"""
Real-time simulation feed (runs every 5 minutes via the scheduler).

For every tracked route with NO real conductor ticketing today, simulate
boardings matching the typical crowding profile for the current hour and
persist them through the same recompute path conductors use — so the OCI
time series, passenger charts and ARIMA/Prophet forecasts update live.

Routes a conductor is actively working are skipped: real data always wins.
"""

import hashlib
from datetime import datetime

from db import passenger_tracking_collection, ticketing_logs_collection
from tracking_utils import typical_oci, recompute_and_persist


def _route_offset(rpid):
    return int(hashlib.md5(rpid.encode()).hexdigest(), 16) % 21 - 10


def run_sim_feed():
    now = datetime.now()
    today = now.strftime("%Y-%m-%d")

    if not (6 <= now.hour <= 23):
        return  # outside service hours

    updated = 0
    for tracking in passenger_tracking_collection.find({}):
        rpid = tracking["routeparentid"]

        # real conductor activity today? leave the route alone
        if ticketing_logs_collection.find_one({"routeparentid": rpid, "date": today}):
            continue

        stops = tracking.get("stops", [])
        if not stops:
            continue

        capacity = int(tracking.get("capacity", 80))
        target_oci = max(5, min(130, typical_oci(now.hour) + _route_offset(rpid)))
        target_pax = round(target_oci * capacity / 100)

        # Distribute: boardings front-loaded, alightings rear-loaded, with the
        # exact delta so boarded - departed == target_pax
        n = len(stops)
        boarded_total = round(target_pax * 1.6)
        departed_total = boarded_total - target_pax

        for i, stop in enumerate(stops):
            pos = i / max(1, n - 1)
            w_board = max(0.0, 1.2 - pos)        # heavier at the start
            w_depart = max(0.0, pos - 0.25)      # heavier at the end
            stop["_wb"] = w_board
            stop["_wd"] = w_depart

        sum_wb = sum(s["_wb"] for s in stops) or 1
        sum_wd = sum(s["_wd"] for s in stops) or 1
        for stop in stops:
            stop["boarded"] = round(boarded_total * stop["_wb"] / sum_wb)
            stop["departed"] = round(departed_total * stop["_wd"] / sum_wd)
            del stop["_wb"], stop["_wd"]

        # fix rounding drift on the last stop
        drift = target_pax - (sum(s["boarded"] for s in stops) - sum(s["departed"] for s in stops))
        stops[-1]["departed"] = max(0, stops[-1]["departed"] - drift)

        recompute_and_persist(rpid, stops, tracking, now)
        passenger_tracking_collection.update_one(
            {"routeparentid": rpid}, {"$set": {"simulated": True}}
        )
        updated += 1

    if updated:
        print(f"[{now:%H:%M}] sim feed updated {updated} route(s)", flush=True)
