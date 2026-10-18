import os
import re
import random
import datetime

from flask import Flask, request, jsonify
from flask_cors import CORS
from dotenv import load_dotenv
from werkzeug.security import generate_password_hash, check_password_hash

# -------------------------------
# App Initialization (FIRST!)
# -------------------------------
load_dotenv()
app = Flask(__name__)
CORS(app)

if not os.getenv("SECRET_KEY"):
    print("⚠️  SECRET_KEY not set in .env — using insecure dev default")

# -------------------------------
# DB Imports
# -------------------------------
from db import (
    passengers_collection,
    conductors_collection,
    admins_collection,
    otp_collection,
)

from auth_utils import create_token

# -------------------------------
# Blueprint Imports
# -------------------------------
from passenger_dashboard import passenger_dashboard_bp
from officer_dashboard import officer_dashboard_bp
from ticket_collector import ticket_collector_bp
from ticketing import ticketing_bp
from gtfs_views import gtfs_bp

# -------------------------------
# Register Blueprints (AFTER app)
# -------------------------------
app.register_blueprint(passenger_dashboard_bp)
app.register_blueprint(officer_dashboard_bp)
app.register_blueprint(ticket_collector_bp)
app.register_blueprint(ticketing_bp)
app.register_blueprint(gtfs_bp)

# =====================================================
# VALIDATORS
# =====================================================
def valid_name(name):
    return bool(name and re.fullmatch(r"[A-Za-z ]{3,}", name))

def valid_phone(phone):
    return bool(phone and re.fullmatch(r"[6-9]\d{9}", phone))

def valid_email(email):
    return bool(email and re.fullmatch(r"[\w\.-]+@[\w\.-]+\.\w+", email))

# =====================================================
# OTP
# =====================================================
def generate_otp():
    return str(random.randint(100000, 999999))

def send_otp(destination, otp):
    # Demo: printed to the server console instead of SMS/email
    print(f"🔐 OTP sent to {destination}: {otp}", flush=True)

# =====================================================
# REQUEST OTP
# =====================================================
@app.route("/api/auth/request-otp", methods=["POST"])
def request_otp():
    data = request.json
    role = data.get("role")
    phone = data.get("phone")
    email = data.get("email")

    if role not in ("passenger", "conductor", "admin"):
        return jsonify({"error": "Invalid role"}), 400

    if role == "passenger":
        if not valid_phone(phone):
            return jsonify({"error": "Invalid Indian phone number"}), 400
        destination = phone
    else:
        if not valid_phone(phone) or not valid_email(email):
            return jsonify({"error": "Invalid phone or email"}), 400
        destination = f"{phone} & {email}"

    otp = generate_otp()
    otp_collection.insert_one({
        "role": role,
        "phone": phone,
        "email": email,
        "otp": otp,
        "expires_at": datetime.datetime.now() + datetime.timedelta(minutes=5),
    })

    send_otp(destination, otp)
    return jsonify({"message": "OTP sent"}), 200

# =====================================================
# SIGNUP
# =====================================================
@app.route("/api/auth/signup", methods=["POST"])
def signup():
    data = request.json

    role = data.get("role")
    name = data.get("name")
    phone = data.get("phone")
    email = data.get("email")
    badge_id = data.get("badge_id")
    depot = data.get("depot")
    password = data.get("password")
    otp = data.get("otp")

    if not valid_name(name):
        return jsonify({"error": "Invalid name"}), 400

    if not valid_phone(phone):
        return jsonify({"error": "Invalid phone"}), 400

    if not password:
        return jsonify({"error": "Password required"}), 400

    otp_doc = otp_collection.find_one({"phone": phone, "otp": otp})
    if not otp_doc:
        return jsonify({"error": "Invalid or expired OTP"}), 401

    # Enforce OTP expiry (previously never checked)
    if otp_doc.get("expires_at") and otp_doc["expires_at"] < datetime.datetime.now():
        otp_collection.delete_many({"phone": phone})
        return jsonify({"error": "OTP expired — request a new one"}), 401

    otp_collection.delete_many({"phone": phone})
    password_hash = generate_password_hash(password)

    if role == "passenger":
        if passengers_collection.find_one({"phone": phone}):
            return jsonify({"error": "Phone already registered"}), 409
        passengers_collection.insert_one({
            "name": name,
            "phone": phone,
            "password_hash": password_hash,
        })
        return jsonify({"message": "Passenger registered"}), 201

    if role == "conductor":
        if not valid_email(email):
            return jsonify({"error": "Invalid email"}), 400
        if conductors_collection.find_one({"email": email}):
            return jsonify({"error": "Email already registered"}), 409
        conductors_collection.insert_one({
            "name": name,
            "phone": phone,
            "email": email,
            "badge_id": badge_id,
            "depot": depot,
            "password_hash": password_hash,
        })
        return jsonify({"message": "Conductor registered"}), 201

    if role == "admin":
        if not valid_email(email):
            return jsonify({"error": "Invalid email"}), 400
        if admins_collection.find_one({"email": email}):
            return jsonify({"error": "Email already registered"}), 409
        admins_collection.insert_one({
            "name": name,
            "phone": phone,
            "email": email,
            "password_hash": password_hash,
        })
        return jsonify({"message": "Admin registered"}), 201

    return jsonify({"error": "Invalid role"}), 400

# =====================================================
# LOGIN
# =====================================================
@app.route("/api/auth/login", methods=["POST"])
def login():
    data = request.json
    role = data.get("role")
    phone = data.get("phone")
    email = data.get("email")
    password = data.get("password")

    if role == "passenger":
        user = passengers_collection.find_one({"phone": phone})
    elif role == "conductor":
        user = conductors_collection.find_one({"email": email})
    elif role == "admin":
        user = admins_collection.find_one({"email": email})
    else:
        return jsonify({"error": "Invalid role"}), 400

    if not user or not check_password_hash(user["password_hash"], password):
        return jsonify({"error": "Invalid credentials"}), 401

    token = create_token(user["_id"], role)
    return jsonify({
        "user_id": str(user["_id"]),
        "role": role,
        "name": user["name"],
        "token": token,
    }), 200


@app.route("/api/health", methods=["GET"])
def health():
    return jsonify({"status": "ok", "time": datetime.datetime.now().isoformat()}), 200

# =====================================================
# RUN
# =====================================================
if __name__ == "__main__":
    USE_DEBUG = True

    # Start the scheduler only in the reloader's child process (or when the
    # reloader is off) — otherwise the daily job gets registered TWICE.
    # NOTE: app.debug is only set inside app.run(), so we can't read it here;
    # USE_DEBUG must be decided before the guard.
    if os.environ.get("WERKZEUG_RUN_MAIN") == "true" or not USE_DEBUG:
        from scheduler import start_scheduler
        start_scheduler()

    app.run(debug=USE_DEBUG, port=5000)
