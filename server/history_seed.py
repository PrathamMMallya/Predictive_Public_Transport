"""
On-demand history seeding.

ARIMA/Prophet need historic trends. A GTFS route the user opens for the
first time has none — so we backfill 7 days of realistic hourly OCI the
first time it's requested, into the same collections conductor data lands
in. Real conductor updates then overwrite live hours naturally.
"""

import random
from datetime import datetime, timedelta

from db import oci_timeseries_collection, oci_daily_snapshots_collection
from tracking_utils import typical_oci

SERVICE_START_HOUR = 8
SERVICE_END_HOUR = 22


def has_history(routeparentid, min_samples=24):
    return (
        oci_timeseries_collection.count_documents(
            {"routeparentid": routeparentid}, limit=min_samples
        )
        >= min_samples
    )


def seed_route_history(routeparentid, routeno="", days=7):
    """Idempotent 7-day hourly OCI backfill for one route."""
    rng = random.Random(f"{routeparentid}-{days}")
    today = datetime.now().date()

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
                "seeded": True,
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
                    "hourlyOCI": hourly_docs,
                    "createdAt": datetime.now(),
                    "seeded": True,
                }
            },
            upsert=True,
        )


def ensure_history(routeparentid, routeno="", days=7):
    """Seed only when the route has little/no history. Returns True if seeded."""
    if has_history(routeparentid):
        return False
    seed_route_history(routeparentid, routeno, days)
    return True
