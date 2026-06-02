# blueprints/broker_session.py
"""
Broker Session Management API.
Provides endpoints for connecting to a broker, disconnecting, and checking
session status. Enforces the single-active-broker constraint.
All endpoints require an authenticated app session (session["user"]).
"""

import os

from flask import Blueprint, jsonify, request, session
from flask import current_app

from database.auth_db import upsert_auth
from database.broker_credentials_db import get_credentials
from utils.logging import get_logger

logger = get_logger(__name__)

broker_session_bp = Blueprint(
    "broker_session_bp", __name__, url_prefix="/broker-session"
)


def _require_user_session():
    """Check that session['user'] is set. Returns (username, None) on success,
    or (None, error_response_tuple) if not authenticated."""
    username = session.get("user")
    if not username:
        return None, (
            jsonify({"status": "error", "message": "Not authenticated"}),
            401,
        )
    return username, None


def _disconnect_current_broker(username):
    """Disconnect the currently active broker session.

    Revokes the auth token in the database and clears broker-related session keys
    while preserving session['user'].
    """
    # Revoke the token in auth_db
    try:
        upsert_auth(username, "", "", revoke=True)
        logger.info(f"Revoked broker token for user {username}")
    except Exception as e:
        logger.exception(f"Error revoking broker token for {username}: {e}")

    # Clear broker-related session keys, preserve session["user"]
    session.pop("logged_in", None)
    session.pop("broker", None)
    session.pop("AUTH_TOKEN", None)
    session.pop("FEED_TOKEN", None)
    session.pop("login_time", None)


@broker_session_bp.route("/connect", methods=["POST"])
def connect():
    """POST /broker-session/connect

    Initiates broker authentication using stored credentials.
    - Loads credentials from broker_credentials_db
    - Sets environment variables for the broker module
    - Returns redirect info for the frontend to continue the auth flow
      (e.g. OAuth redirect URL or initiate TOTP page)

    Request JSON:
        {"broker": "<broker_name>"}

    Enforces single-active-broker: disconnects existing broker before connecting new one.
    """
    username, err = _require_user_session()
    if err:
        return err

    data = request.get_json() or {}
    broker = data.get("broker", "").strip().lower()

    if not broker:
        return jsonify({"status": "error", "message": "Broker name is required"}), 400

    # Enforce single-active-broker: disconnect old broker if connected
    if session.get("logged_in"):
        old_broker = session.get("broker", "unknown")
        logger.info(f"Disconnecting active broker '{old_broker}' before connecting '{broker}'")
        _disconnect_current_broker(username)

    # Load credentials from DB
    creds = get_credentials(username, broker)
    if not creds:
        return (
            jsonify({"status": "error", "message": f"No credentials found for broker '{broker}'"}),
            404,
        )

    # Set environment variables from stored credentials for the broker module
    api_key = creds.get("api_key") or ""
    api_secret = creds.get("api_secret") or ""
    redirect_url = creds.get("redirect_url") or ""

    os.environ["BROKER_API_KEY"] = api_key
    os.environ["BROKER_API_SECRET"] = api_secret
    os.environ["REDIRECT_URL"] = redirect_url

    logger.info(f"Set env vars from stored credentials for broker '{broker}' (user: {username})")

    # Get the broker auth function from the lazy registry
    broker_auth_functions = current_app.broker_auth_functions
    auth_function = broker_auth_functions.get(f"{broker}_auth")

    if not auth_function:
        return (
            jsonify({"status": "error", "message": f"Broker '{broker}' is not supported"}),
            404,
        )

    # For OAuth-based brokers, we cannot complete auth server-side.
    # Return the broker's login initiation URL for the frontend to redirect to.
    # The actual auth completion happens via the existing brlogin callback route.
    # Store the broker name in session so the callback knows which broker to handle.
    session["broker"] = broker

    return jsonify({
        "status": "success",
        "message": f"Credentials loaded for broker '{broker}'. Proceed with broker auth flow.",
        "data": {
            "broker": broker,
            "redirect_url": f"/{broker}/callback",
        },
    })


@broker_session_bp.route("/disconnect", methods=["POST"])
def disconnect():
    """POST /broker-session/disconnect

    Terminates the active broker session. Revokes the broker auth token
    and clears broker-related session keys while preserving the User_Session.
    """
    username, err = _require_user_session()
    if err:
        return err

    if not session.get("logged_in"):
        return jsonify({
            "status": "success",
            "message": "No active broker session to disconnect",
        })

    broker = session.get("broker", "unknown")
    logger.info(f"Disconnecting broker '{broker}' for user {username}")

    _disconnect_current_broker(username)

    return jsonify({
        "status": "success",
        "message": f"Disconnected from broker '{broker}'",
        "data": {"redirect": "/broker-select"},
    })


@broker_session_bp.route("/status", methods=["GET"])
def status():
    """GET /broker-session/status

    Returns the current broker session status for the authenticated user.
    """
    username, err = _require_user_session()
    if err:
        return err

    connected = session.get("logged_in", False)
    broker = session.get("broker") if connected else None

    return jsonify({
        "status": "success",
        "data": {
            "connected": connected,
            "broker": broker,
        },
    })
