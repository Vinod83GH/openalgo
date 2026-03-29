# blueprints/kill_switch.py

import os

from flask import Blueprint, jsonify, request, session

from database.auth_db import get_auth_token
from database.kill_switch_db import is_kill_switch_active
from limiter import limiter
from services.kill_switch_service import (
    activate_kill_switch,
    get_kill_switch_status,
    update_kill_switch_config,
)
from utils.logging import get_logger
from utils.session import check_session_validity

logger = get_logger(__name__)

API_RATE_LIMIT = os.getenv("API_RATE_LIMIT", "50 per second")

kill_switch_bp = Blueprint("kill_switch_bp", __name__, url_prefix="/admin")


# ---------------------------------------------------------------------------
# Order middleware helper
# ---------------------------------------------------------------------------

def check_kill_switch_active(broker_name: str) -> tuple:
    """Return (is_blocked, error_response).

    If the kill switch is ACTIVATED for the given broker, returns
    (True, error_dict) so the caller can immediately return the error.
    Otherwise returns (False, None).
    """
    if is_kill_switch_active(broker_name):
        return True, {"status": "error", "message": "Order blocked: Kill Switch is ACTIVATED"}
    return False, None


# ---------------------------------------------------------------------------
# API endpoints
# ---------------------------------------------------------------------------

@kill_switch_bp.route("/api/kill-switch")
@check_session_validity
@limiter.limit(API_RATE_LIMIT)
def api_get_kill_switch_status():
    """GET /admin/api/kill-switch — return current kill switch status and config."""
    try:
        login_username = session["user"]
        auth_token = get_auth_token(login_username)
        broker = session.get("broker")

        if not auth_token or not broker:
            return jsonify({"status": "error", "message": "Authentication error"}), 401

        data = get_kill_switch_status(
            broker_name=broker,
            auth_token=auth_token,
            broker=broker,
        )
        return jsonify({"status": "success", "data": data})
    except NotImplementedError as e:
        logger.warning(f"Kill switch: broker not supported: {e}")
        return jsonify({"status": "error", "message": str(e)}), 400
    except Exception as e:
        logger.exception(f"Error fetching kill switch status: {e}")
        return jsonify({"status": "error", "message": str(e)}), 500


@kill_switch_bp.route("/api/kill-switch/config", methods=["POST"])
@check_session_validity
@limiter.limit(API_RATE_LIMIT)
def api_update_kill_switch_config():
    """POST /admin/api/kill-switch/config — update enabled flag and P&L thresholds."""
    try:
        login_username = session["user"]
        auth_token = get_auth_token(login_username)
        broker = session.get("broker")

        if not auth_token or not broker:
            return jsonify({"status": "error", "message": "Authentication error"}), 401

        body = request.get_json() or {}
        enabled = body.get("enabled", False)
        profit_threshold = body.get("profit_threshold", 0)
        loss_threshold = body.get("loss_threshold", 0)

        data = update_kill_switch_config(
            broker_name=broker,
            enabled=bool(enabled),
            profit_threshold=profit_threshold,
            loss_threshold=loss_threshold,
            auth_token=auth_token,
            broker=broker,
        )
        return jsonify({"status": "success", "data": data})
    except ValueError as e:
        logger.warning(f"Kill switch config validation error: {e}")
        return jsonify({"status": "error", "message": str(e)}), 400
    except NotImplementedError as e:
        logger.warning(f"Kill switch: broker not supported: {e}")
        return jsonify({"status": "error", "message": str(e)}), 400
    except Exception as e:
        logger.exception(f"Error updating kill switch config: {e}")
        return jsonify({"status": "error", "message": str(e)}), 500


@kill_switch_bp.route("/api/kill-switch/activate", methods=["POST"])
@check_session_validity
@limiter.limit(API_RATE_LIMIT)
def api_activate_kill_switch():
    """POST /admin/api/kill-switch/activate — immediately activate the broker kill switch."""
    try:
        login_username = session["user"]
        auth_token = get_auth_token(login_username)
        broker = session.get("broker")

        if not auth_token or not broker:
            return jsonify({"status": "error", "message": "Authentication error"}), 401

        response = activate_kill_switch(
            broker_name=broker,
            auth_token=auth_token,
            broker=broker,
        )
        return jsonify({"status": "success", "data": response})
    except NotImplementedError as e:
        logger.warning(f"Kill switch: broker not supported: {e}")
        return jsonify({"status": "error", "message": str(e)}), 400
    except Exception as e:
        logger.exception(f"Error activating kill switch: {e}")
        return jsonify({"status": "error", "message": str(e)}), 500
