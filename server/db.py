import os
from pymongo import MongoClient, ASCENDING
from dotenv import load_dotenv

load_dotenv()

MONGO_URI = os.getenv("MONGO_URI")
DB_NAME = os.getenv("DB_NAME", "bmtc_db")

if not MONGO_URI:
    raise ValueError("MONGO_URI is not set in .env")

client = MongoClient(MONGO_URI, serverSelectionTimeoutMS=5000)
db = client[DB_NAME]

# === Collections ===
passengers_collection = db["passengers"]
conductors_collection = db["conductors"]
admins_collection = db["admins"]
otp_collection = db["otp"]

# Ticketing / Tracking
passenger_tracking_collection = db["passenger_tracking"]
ticketing_logs_collection = db["ticketing_logs"]
tickets_collection = db["tickets"]
counters_collection = db["counters"]

# Overcrowding time series (hourly) and daily rollups
oci_timeseries_collection = db["oci_timeseries"]
oci_daily_snapshots_collection = db["oci_daily_snapshots"]

# === Indexes ===
passengers_collection.create_index([("phone", ASCENDING)], unique=True)
conductors_collection.create_index([("email", ASCENDING)], unique=True)
admins_collection.create_index([("email", ASCENDING)], unique=True)
otp_collection.create_index([("phone", ASCENDING)])
otp_collection.create_index([("email", ASCENDING)])
passenger_tracking_collection.create_index([("routeparentid", ASCENDING)], unique=True)
# One OCI sample per route per hour bucket
oci_timeseries_collection.create_index(
    [("routeparentid", ASCENDING), ("hour", ASCENDING)], unique=True
)
# One daily snapshot per route per date (makes the reset job idempotent)
oci_daily_snapshots_collection.create_index(
    [("routeparentid", ASCENDING), ("date", ASCENDING)], unique=True
)
ticketing_logs_collection.create_index([("routeparentid", ASCENDING), ("date", ASCENDING)])
tickets_collection.create_index([("ticket_no", ASCENDING)], unique=True)
tickets_collection.create_index([("routeparentid", ASCENDING), ("date", ASCENDING)])
tickets_collection.create_index([("status", ASCENDING)])
# Idempotency key for ticket issue retries (sparse: only docs that carry one)
tickets_collection.create_index([("client_ref", ASCENDING)], unique=True, sparse=True)


def get_mongo_db():
    return db
