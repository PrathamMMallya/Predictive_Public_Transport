import os
from functools import wraps

import jwt
from flask import request, jsonify

SECRET_KEY = os.getenv("SECRET_KEY", "dev-secret-key")


def create_token(uid, role):
    import datetime

    payload = {
        "user_id": str(uid),
        "role": role,
        "exp": datetime.datetime.utcnow() + datetime.timedelta(days=1),
    }
    return jwt.encode(payload, SECRET_KEY, algorithm="HS256")


def require_role(*allowed_roles):
    """
    Decorator: requires a valid `Authorization: Bearer <token>` header whose
    JWT role is in allowed_roles. Injects `request.user` = {"user_id", "role"}.
    """

    def decorator(fn):
        @wraps(fn)
        def wrapper(*args, **kwargs):
            auth_header = request.headers.get("Authorization", "")
            if not auth_header.startswith("Bearer "):
                return jsonify({"error": "Missing or malformed Authorization header"}), 401

            token = auth_header.split(" ", 1)[1]
            try:
                payload = jwt.decode(token, SECRET_KEY, algorithms=["HS256"])
            except jwt.ExpiredSignatureError:
                return jsonify({"error": "Token expired, please log in again"}), 401
            except jwt.InvalidTokenError:
                return jsonify({"error": "Invalid token"}), 401

            if allowed_roles and payload.get("role") not in allowed_roles:
                return jsonify({"error": "Forbidden: insufficient role"}), 403

            request.user = {"user_id": payload.get("user_id"), "role": payload.get("role")}
            return fn(*args, **kwargs)

        return wrapper

    return decorator
