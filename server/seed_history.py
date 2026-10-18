"""
Seed 7 days of realistic hourly crowding history for every tracked route.

Why: the forecasting and admin reports learn from *historic* OCI trends. On a
fresh install there is no history yet (conductors create it over time), so the
demo would have nothing to predict from. This script backfills the same
collections the live conductor flow writes to:

    oci_timeseries       (one doc per route per hour bucket)
    oci_daily_snapshots  (one doc per route per day)

It is idempotent: re-running replaces previously seeded days, and it never
touches hour buckets from TODAY (where live conductor data may exist).

Usage:
    python seed_history.py            # seed all tracked routes (+ demo route)
    python seed_history.py --days 14  # seed more history
"""

import argparse
import random
from datetime import datetime, timedelta

from bmtc_data import CATALOG
from db import (
    passenger_tracking_collection,
    oci_timeseries_collection,
    oci_daily_snapshots_collection,
)

SERVICE_START_HOUR = 8
SERVICE_END_HOUR = 20


def typical_oci(hour, rng):
    """Realistic Bangalore-style crowding curve with jitter."""
    if 8 <= hour <= 10:      # morning peak
        base = rng.gauss(85, 8)
    elif 17 <= hour <= 19:   # evening peak
        base = rng.gauss(92, 8)
    elif 12 <= hour <= 13:   # lunch bump
        base = rng.gauss(58, 8)
    else:
        base = rng.gauss(42, 8)
    return max(5, min(130, int(base)))


def seed_route(routeparentid, routeno, days):
    # Deterministic per route so re-seeds produce stable data
    rng = random.Random(f"{routeparentid}-{days}")
    today = datetime.now().date()
    seeded_days = 0

    for day_offset in range(days, 0, -1):
        date = today - timedelta(days=day_offset)
        date_str = str(date)

        hourly_docs = []
        for hour in range(SERVICE_START_HOUR, SERVICE_END_HOUR + 1):
            hour_bucket = f"{date_str} {hour:02d}:00"
            oci = typical_oci(hour, rng)
            doc = {
                "routeparentid": routeparentid,
                "routeno": routeno,
                "hour": hour_bucket,
                "oci": oci,
                "timestamp": datetime.combine(date, datetime.min.time()).replace(hour=hour),
            }
            oci_timeseries_collection.update_one(
                {"routeparentid": routeparentid, "hour": hour_bucket},
                {"$set": doc},
                upsert=True,
            )
            hourly_docs.append(doc)

        avg_oci = int(sum(d["oci"] for d in hourly_docs) / len(hourly_docs))
        oci_daily_snapshots_collection.update_one(
            {"routeparentid": routeparentid, "date": date_str},
            {
                "$set": {
                    "date": date_str,
                    "routeparentid": routeparentid,
                    "routeno": routeno,
                    "dailyOCI": avg_oci,
                    "hourlyOCI": [{k: v for k, v in d.items() if k != "_id"} for d in hourly_docs],
                    "createdAt": datetime.now(),
                    "seeded": True,
                }
            },
            upsert=True,
        )
        seeded_days += 1

    print(f"  ✓ {routeno or routeparentid}: seeded {seeded_days} days "
          f"({SERVICE_START_HOUR}:00–{SERVICE_END_HOUR}:00 hourly)")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--days", type=int, default=7)
    args = parser.parse_args()

    routes = list(passenger_tracking_collection.find({}))

    # Ensure every catalog route has a tracking doc, so passenger and admin
    # flows work out of the box even when the live BMTC API is blocked.
    existing_ids = {r["routeparentid"] for r in routes}
    for entry in CATALOG:
        if entry["routeparentid"] in existing_ids:
            continue
        doc = {
            "routeno": entry["routeno"],
            "routeparentid": entry["routeparentid"],
            "stops": [
                {"name": s, "boarded": 0, "departed": 0, "crowding": 0, "time": "Not yet tracked"}
                for s in entry["stops"]
            ],
            "vehicle": entry.get("vehicle", ""),
            "trips": entry.get("trips", []),
            "currentPassengers": 0,
            "capacity": 80,
            "overcrowdingIndex": 0,
            "overcrowdingLevel": "LOW",
            "status": "Active",
            "createdAt": datetime.now(),
        }
        passenger_tracking_collection.update_one(
            {"routeparentid": doc["routeparentid"]}, {"$set": doc}, upsert=True
        )
        routes.append(doc)
        print(f"Created tracking doc for catalog route {entry['routeno']} ({entry['routeparentid']})")

    print(f"Seeding {args.days} days of history for {len(routes)} route(s)…")
    for route in routes:
        seed_route(route["routeparentid"], route.get("routeno", ""), args.days)
    print("Done. Forecasts and admin reports now have history to learn from.")


if __name__ == "__main__":
    main()
