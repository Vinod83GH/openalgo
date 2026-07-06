# blueprints/paper_journal.py

import os
from datetime import datetime

from flask import Blueprint, jsonify, request

from database.auth_db import verify_api_key
from limiter import limiter
from services.paper_trade_journal_service import (
    close_trade,
    get_journal_status,
    get_summary,
    list_strategies,
    list_trades,
    open_trade,
)
from utils.logging import get_logger

logger = get_logger(__name__)

API_RATE_LIMIT = os.getenv("API_RATE_LIMIT", "50 per second")

paper_journal_bp = Blueprint(
    "paper_journal_bp", __name__, url_prefix="/api/v1/paperjournal"
)


def _validate_api_key_from_body():
    """Extract and validate API key from JSON request body (POST/PATCH)."""
    data = request.get_json(silent=True) or {}
    api_key = data.get("apikey")
    if not api_key or not verify_api_key(api_key):
        return None, data
    return api_key, data


def _validate_api_key_from_params():
    """Extract and validate API key from query parameters (GET)."""
    api_key = request.args.get("apikey")
    if not api_key or not verify_api_key(api_key):
        return None
    return api_key


def _parse_date(value):
    """Parse a date string in YYYY-MM-DD format. Returns date or None."""
    if not value:
        return None
    return datetime.strptime(value, "%Y-%m-%d").date()


# ---------------------------------------------------------------------------
# POST /trade — Open a new trade
# ---------------------------------------------------------------------------


@paper_journal_bp.route("/trade", methods=["POST"])
@limiter.limit(API_RATE_LIMIT)
def create_trade_route():
    """POST /api/v1/paperjournal/trade — create a new trade record."""
    try:
        api_key, data = _validate_api_key_from_body()
        if not api_key:
            return jsonify({"status": "error", "message": "Invalid API key"}), 401

        # Remove apikey from data before passing to service
        trade_data = {k: v for k, v in data.items() if k != "apikey"}

        result = open_trade(trade_data)

        if result.get("status") == "error":
            return jsonify(result), 400

        return jsonify(result), 201

    except Exception as e:
        logger.exception(f"Error creating trade: {e}")
        return jsonify({"status": "error", "message": "Internal server error"}), 500


# ---------------------------------------------------------------------------
# PATCH /trade/<trade_id> — Close or update a trade
# ---------------------------------------------------------------------------


@paper_journal_bp.route("/trade/<int:trade_id>", methods=["PATCH"])
@limiter.limit(API_RATE_LIMIT)
def update_trade_route(trade_id):
    """PATCH /api/v1/paperjournal/trade/<id> — update/close a trade."""
    try:
        api_key, data = _validate_api_key_from_body()
        if not api_key:
            return jsonify({"status": "error", "message": "Invalid API key"}), 401

        # Remove apikey from data before passing to service
        update_data = {k: v for k, v in data.items() if k != "apikey"}

        result = close_trade(trade_id, update_data)

        if result.get("status") == "error":
            if "not found" in result.get("message", "").lower():
                return jsonify(result), 404
            return jsonify(result), 400

        return jsonify(result), 200

    except Exception as e:
        logger.exception(f"Error updating trade {trade_id}: {e}")
        return jsonify({"status": "error", "message": "Internal server error"}), 500


# ---------------------------------------------------------------------------
# GET /strategies — List distinct strategy names
# ---------------------------------------------------------------------------


@paper_journal_bp.route("/strategies", methods=["GET"])
@limiter.limit(API_RATE_LIMIT)
def list_strategies_route():
    """GET /api/v1/paperjournal/strategies — list distinct strategy names."""
    try:
        api_key = _validate_api_key_from_params()
        if not api_key:
            return jsonify({"status": "error", "message": "Invalid API key"}), 401

        strategies = list_strategies()

        return jsonify({"status": "success", "data": strategies}), 200

    except Exception as e:
        logger.exception(f"Error listing strategies: {e}")
        return jsonify({"status": "error", "message": "Internal server error"}), 500


# ---------------------------------------------------------------------------
# GET /trades — List trades with filters
# ---------------------------------------------------------------------------


@paper_journal_bp.route("/trades", methods=["GET"])
@limiter.limit(API_RATE_LIMIT)
def list_trades_route():
    """GET /api/v1/paperjournal/trades — list trades with optional filters."""
    try:
        api_key = _validate_api_key_from_params()
        if not api_key:
            return jsonify({"status": "error", "message": "Invalid API key"}), 401

        # Parse date filters
        try:
            start_date = _parse_date(request.args.get("start_date"))
            end_date = _parse_date(request.args.get("end_date"))
        except ValueError:
            return jsonify(
                {"status": "error", "message": "Invalid date format. Use YYYY-MM-DD"}
            ), 400

        strategy_name = request.args.get("strategy_name")

        trades = list_trades(
            start_date=start_date, end_date=end_date, strategy_name=strategy_name
        )

        return jsonify({"status": "success", "data": trades}), 200

    except Exception as e:
        logger.exception(f"Error listing trades: {e}")
        return jsonify({"status": "error", "message": "Internal server error"}), 500


# ---------------------------------------------------------------------------
# GET /summary — Get trade summary statistics
# ---------------------------------------------------------------------------


@paper_journal_bp.route("/summary", methods=["GET"])
@limiter.limit(API_RATE_LIMIT)
def get_summary_route():
    """GET /api/v1/paperjournal/summary — get trade summary stats."""
    try:
        api_key = _validate_api_key_from_params()
        if not api_key:
            return jsonify({"status": "error", "message": "Invalid API key"}), 401

        # Parse date filters
        try:
            start_date = _parse_date(request.args.get("start_date"))
            end_date = _parse_date(request.args.get("end_date"))
        except ValueError:
            return jsonify(
                {"status": "error", "message": "Invalid date format. Use YYYY-MM-DD"}
            ), 400

        strategy_name = request.args.get("strategy_name")

        summary = get_summary(
            start_date=start_date, end_date=end_date, strategy_name=strategy_name
        )

        return jsonify({"status": "success", "data": summary}), 200

    except Exception as e:
        logger.exception(f"Error getting summary: {e}")
        return jsonify({"status": "error", "message": "Internal server error"}), 500


# ---------------------------------------------------------------------------
# GET /status — Get journal/mode status
# ---------------------------------------------------------------------------


@paper_journal_bp.route("/status", methods=["GET"])
@limiter.limit(API_RATE_LIMIT)
def get_status_route():
    """GET /api/v1/paperjournal/status — check journal mode status."""
    try:
        api_key = _validate_api_key_from_params()
        if not api_key:
            return jsonify({"status": "error", "message": "Invalid API key"}), 401

        status = get_journal_status()

        return jsonify({"status": "success", "data": status}), 200

    except Exception as e:
        logger.exception(f"Error getting journal status: {e}")
        return jsonify({"status": "error", "message": "Internal server error"}), 500
