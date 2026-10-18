from datetime import datetime, timedelta

from db import get_mongo_db

mongo = get_mongo_db()

passenger_tracking = mongo["passenger_tracking"]
oci_timeseries = mongo["oci_timeseries"]
oci_daily_snapshots = mongo["oci_daily_snapshots"]
tickets = mongo["tickets"]


def run_daily_reset():
    """
    Runs once a day just after midnight (Asia/Kolkata).

    1. Rolls up *yesterday's* hourly OCI samples into a daily snapshot
       (upsert — safe to re-run, won't duplicate).
    2. Resets the live tracking counters so a new service day starts clean.
    """
    today = datetime.now().date()
    yesterday = today - timedelta(days=1)
    yesterday_str = str(yesterday)

    for bus in passenger_tracking.find({}):
        routeparentid = bus["routeparentid"]

        # Hour buckets are stored as "YYYY-MM-DD HH:00" — prefix match = that day
        hourly_data = list(
            oci_timeseries.find(
                {"routeparentid": routeparentid, "hour": {"$regex": f"^{yesterday_str}"}},
                {"_id": 0},
            ).sort("hour", 1)
        )

        if hourly_data:
            avg_oci = int(sum(h["oci"] for h in hourly_data) / len(hourly_data))
            oci_daily_snapshots.update_one(
                {"routeparentid": routeparentid, "date": yesterday_str},
                {
                    "$set": {
                        "date": yesterday_str,
                        "routeparentid": routeparentid,
                        "routeno": bus.get("routeno", ""),
                        "dailyOCI": avg_oci,
                        "hourlyOCI": hourly_data,
                        "createdAt": datetime.now(),
                    }
                },
                upsert=True,
            )

        # Reset live data — a single $set (the old code had two $set keys in
        # one dict, so Python silently dropped the first and counts never reset)
        passenger_tracking.update_one(
            {"routeparentid": routeparentid},
            {
                "$set": {
                    "currentPassengers": 0,
                    "overcrowdingIndex": 0,
                    "overcrowdingLevel": "LOW",
                    "updatedAt": datetime.now(),
                    "stops.$[].boarded": 0,
                    "stops.$[].departed": 0,
                    "stops.$[].crowding": 0,
                }
            },
        )

    # Close out any tickets still ON_BUS from before — their trip is over
    stale = tickets.update_many(
        {"status": "ON_BUS"},
        {"$set": {"status": "COMPLETED", "completed_at": datetime.now(), "auto_closed": True}},
    )
    if stale.modified_count:
        print(f"Auto-closed {stale.modified_count} stale ON_BUS tickets")

    print(f"[{datetime.now()}] DAILY OCI RESET COMPLETED for {yesterday_str}")
