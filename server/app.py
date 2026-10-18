
import os
import re
import secrets
import datetime

from flask import Flask, request, jsonify
from flask_cors import CORS
from dotenv import load_dotenv
from werkzeug.security import generate_password_hash, check_password_hash

# -------------------------------
# App Initialization
# -------------------------------
load_dotenv()

app = Flask(__name__)
CORS(app)

if not os.getenv("SECRET_KEY"):
    print("WARNING: SECRET_KEY not set in .env — using insecure dev default")

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
# Register Blueprints
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
    return bool(
        isinstance(name, str)
        and re.fullmatch(r"[A-Za-z ]{3,}", name.strip())
    )


def valid_phone(phone):
    return bool(
        isinstance(phone, str)
        and re.fullmatch(r"[6-9]\d{9}", phone)
    )


def valid_email(email):
    return bool(
        isinstance(email, str)
        and re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", email)
    )


# =====================================================
# OTP
# =====================================================
OTP_EXPIRY_MINUTES = 5


def generate_otp():
    # Generate a six-digit OTP using a cryptographically secure generator.
    return str(secrets.randbelow(900000) + 100000)


def send_otp(destination, otp):
    print("\n========== OTP DEBUG ==========", flush=True)
    print(f"Destination: {destination}", flush=True)
    print(f"Generated OTP: {otp}", flush=True)
    print("================================\n", flush=True)


def otp_query_for(role, phone, email=None, otp=None):
    query = {
        "role": role,
        "phone": phone,
    }

    if role in ("conductor", "admin"):
        query["email"] = email

    if otp is not None:
        query["otp"] = otp

    return query


# =====================================================
# REQUEST OTP
# =====================================================
@app.route("/api/auth/request-otp", methods=["POST"])
def request_otp():
    data = request.get_json(silent=True) or {}

    role = data.get("role")
    phone = data.get("phone")
    email = (data.get("email") or "").strip().lower()

    if role not in ("passenger", "conductor", "admin"):
        return jsonify({"error": "Invalid role"}), 400

    if not valid_phone(phone):
        return jsonify({"error": "Invalid Indian phone number"}), 400

    if role in ("conductor", "admin") and not valid_email(email):
        return jsonify({"error": "Invalid email"}), 400

    # Only one current OTP per role/phone/email combination.
    otp_query = otp_query_for(role, phone, email if email else None)
    otp_collection.delete_many(otp_query)

    otp = generate_otp()

    now = datetime.datetime.now()
    expires_at = now + datetime.timedelta(minutes=OTP_EXPIRY_MINUTES)

    otp_collection.insert_one({
        "role": role,
        "phone": phone,
        "email": email,
        "otp": otp,
        "created_at": now,
        "expires_at": expires_at,
    })

    # Demo mode: prints the OTP in the Flask terminal.
    destination = phone[-4:]
    if role in ("conductor", "admin"):
        destination = f"phone ending {phone[-4:]}, email {email}"

    send_otp(destination, otp)

    return jsonify({
        "message": "OTP generated. Check the backend terminal in development."
    }), 200


# =====================================================
# SIGNUP
# =====================================================
@app.route("/api/auth/signup", methods=["POST"])
def signup():
    data = request.get_json(silent=True) or {}

    role = data.get("role")
    name = data.get("name")
    phone = data.get("phone")
    email = (data.get("email") or "").strip().lower()
    badge_id = data.get("badge_id")
    depot = data.get("depot")
    password = data.get("password")
    otp = str(data.get("otp") or "").strip()

    # Validate role and basic fields first.
    if role not in ("passenger", "conductor", "admin"):
        return jsonify({"error": "Invalid role"}), 400

    if not valid_name(name):
        return jsonify({"error": "Invalid name. Use at least 3 letters."}), 400

    name = name.strip()

    if not valid_phone(phone):
        return jsonify({"error": "Invalid phone number"}), 400

    if not isinstance(password, str) or not password:
        return jsonify({"error": "Password required"}), 400

    if not re.fullmatch(r"\d{6}", otp):
        return jsonify({"error": "Enter the six-digit OTP"}), 400

    if role in ("conductor", "admin") and not valid_email(email):
        return jsonify({"error": "Invalid email"}), 400

    # Check for existing accounts before consuming the OTP.
    if role == "passenger":
        if passengers_collection.find_one({"phone": phone}):
            return jsonify({"error": "Phone already registered"}), 409

    elif role == "conductor":
        if conductors_collection.find_one({"email": email}):
            return jsonify({"error": "Email already registered"}), 409

    elif role == "admin":
        if admins_collection.find_one({"email": email}):
            return jsonify({"error": "Email already registered"}), 409

    # The OTP must match the same role, phone, and (when applicable) email.
    query = otp_query_for(role, phone, email if email else None, otp)
    otp_doc = otp_collection.find_one(query)

    if not otp_doc:
        return jsonify({
            "error": "Invalid OTP, or no OTP was requested for these details."
        }), 401

    expires_at = otp_doc.get("expires_at")

    if not expires_at:
        otp_collection.delete_many(query)
        return jsonify({"error": "OTP has no expiry. Request a new OTP."}), 401

    if expires_at < datetime.datetime.now():
        otp_collection.delete_many(query)
        return jsonify({"error": "OTP expired. Please request a new one."}), 401

    # Hash the password before storing it.
    password_hash = generate_password_hash(password)

    # Create the account.
    if role == "passenger":
        passengers_collection.insert_one({
            "name": name,
            "phone": phone,
            "password_hash": password_hash,
        })

    elif role == "conductor":
        conductors_collection.insert_one({
            "name": name,
            "phone": phone,
            "email": email,
            "badge_id": badge_id,
            "depot": depot,
            "password_hash": password_hash,
        })

    else:  # admin
        admins_collection.insert_one({
            "name": name,
            "phone": phone,
            "email": email,
            "password_hash": password_hash,
        })

    # Consume the OTP only after successful account creation.
    otp_collection.delete_many(query)

    return jsonify({
        "message": f"{role.capitalize()} registered successfully."
    }), 201


# =====================================================
# LOGIN
# =====================================================
@app.route("/api/auth/login", methods=["POST"])
def login():
    data = request.get_json(silent=True) or {}

    role = data.get("role")
    phone = data.get("phone")
    email = (data.get("email") or "").strip().lower()
    password = data.get("password")

    if not isinstance(password, str) or not password:
        return jsonify({"error": "Password required"}), 400

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


# =====================================================
# HEALTH CHECK
# =====================================================
@app.route("/api/health", methods=["GET"])
def health():
    return jsonify({
        "status": "ok",
        "time": datetime.datetime.now().isoformat(),
    }), 200


# =====================================================
# RUN
# =====================================================
if __name__ == "__main__":
    USE_DEBUG = True

    # Start the scheduler only in the reloader's child process.
    if os.environ.get("WERKZEUG_RUN_MAIN") == "true" or not USE_DEBUG:
        from scheduler import start_scheduler
        start_scheduler()

    app.run(debug=USE_DEBUG, port=5000)
