# blueprints/broker_credentials_store.py
"""
Broker Credential Store API.
Provides CRUD endpoints for managing per-user, per-broker credentials
stored in the database. All endpoints require an authenticated app session
(session["user"]) but do NOT require an active broker session.
"""

from flask import Blueprint, jsonify, request, session

from database.broker_credentials_db import (
    delete_credentials,
    get_all_credentials,
    get_credentials,
    mask_secret,
    save_credentials,
)
from utils.logging import get_logger

logger = get_logger(__name__)

broker_credentials_store_bp = Blueprint(
    "broker_credentials_store_bp", __name__, url_prefix="/api/broker-credentials"
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


@broker_credentials_store_bp.route("/list", methods=["GET"])
def list_credentials():
    """GET /api/broker-credentials/list
    Return all saved broker credentials for the current user with secrets masked.
    """
    username, err = _require_user_session()
    if err:
        return err

    try:
        creds = get_all_credentials(username)
        return jsonify({"status": "success", "data": creds})
    except Exception as e:
        logger.exception(f"Error listing broker credentials for {username}: {e}")
        return jsonify({"status": "error", "message": "Database error"}), 500


@broker_credentials_store_bp.route("/<broker>", methods=["GET"])
def get_broker_credentials(broker):
    """GET /api/broker-credentials/<broker>
    Return credentials for a specific broker (masked secrets).
    """
    username, err = _require_user_session()
    if err:
        return err

    try:
        cred = get_credentials(username, broker)
        if not cred:
            return jsonify({"status": "success", "data": None})

        # Mask the api_secret before returning
        cred["api_secret"] = mask_secret(cred.get("api_secret"))
        return jsonify({"status": "success", "data": cred})
    except Exception as e:
        logger.exception(
            f"Error retrieving broker credentials for {username}/{broker}: {e}"
        )
        return jsonify({"status": "error", "message": "Database error"}), 500


@broker_credentials_store_bp.route("/<broker>", methods=["POST"])
def save_broker_credentials(broker):
    """POST /api/broker-credentials/<broker>
    Save or update credentials for a broker. Validates non-empty api_key and api_secret.
    """
    username, err = _require_user_session()
    if err:
        return err

    data = request.get_json() or {}

    api_key = data.get("api_key", "")
    api_secret = data.get("api_secret", "")
    client_id = data.get("client_id", "")
    redirect_url = data.get("redirect_url", "")
    additional_config = data.get("additional_config")

    # Validate required fields
    if not api_key or not api_key.strip():
        return (
            jsonify({"status": "error", "message": "API key is required"}),
            400,
        )

    if not api_secret or not api_secret.strip():
        return (
            jsonify({"status": "error", "message": "API secret is required"}),
            400,
        )

    # If api_secret contains asterisks, it's a masked value from the GET endpoint.
    # Use the existing secret from the DB instead of overwriting with masked string.
    if "*" in api_secret:
        existing = get_credentials(username, broker)
        if existing and existing.get("api_secret"):
            api_secret = existing["api_secret"]
        else:
            return (
                jsonify({"status": "error", "message": "Please enter the actual API secret (not masked value)"}),
                400,
            )

    try:
        success = save_credentials(
            username=username,
            broker_name=broker,
            api_key=api_key.strip(),
            api_secret=api_secret.strip(),
            client_id=client_id.strip() if client_id else "",
            redirect_url=redirect_url.strip() if redirect_url else "",
            additional_config=additional_config,
        )

        if success:
            return jsonify(
                {"status": "success", "message": "Credentials saved successfully"}
            )
        else:
            return (
                jsonify({"status": "error", "message": "Failed to store credentials"}),
                500,
            )
    except Exception as e:
        logger.exception(
            f"Error saving broker credentials for {username}/{broker}: {e}"
        )
        return jsonify({"status": "error", "message": "Failed to store credentials"}), 500


@broker_credentials_store_bp.route("/<broker>", methods=["DELETE"])
def delete_broker_credentials(broker):
    """DELETE /api/broker-credentials/<broker>
    Remove saved credentials for a broker.
    """
    username, err = _require_user_session()
    if err:
        return err

    try:
        deleted = delete_credentials(username, broker)
        if deleted:
            return jsonify(
                {"status": "success", "message": "Credentials deleted successfully"}
            )
        else:
            return jsonify(
                {"status": "success", "message": "No credentials found to delete"}
            )
    except Exception as e:
        logger.exception(
            f"Error deleting broker credentials for {username}/{broker}: {e}"
        )
        return jsonify({"status": "error", "message": "Database error"}), 500
