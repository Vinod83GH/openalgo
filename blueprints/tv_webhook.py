"""
TradingView Signal Trade Monitor - Webhook Blueprint
Route: /tv
Features: Receive TradingView BUY alerts, resolve ITM option, place entry order, spawn trade monitor
"""

import os
import time
from dataclasses import dataclass
from datetime import datetime, timedelta

import requests

from flask import Blueprint, jsonify, request

from blueprints.python_strategy import (
    RUNNING_STRATEGIES,
)
from database.auth_db import get_auth_token_broker
from utils.logging import get_logger

logger = get_logger(__name__)

# Blueprint registration
tv_webhook_bp = Blueprint("tv_webhook_bp", __name__, url_prefix="/tv")

# In-memory cooldown tracker: apikey -> last signal unix timestamp
_last_signal_time: dict[str, float] = {}


def _get_nearest_weekly_expiry(symbol: str) -> str:
    """Calculate the nearest expiry date in DDMMMYY format based on underlying type.

    Rules:
    - NIFTY: Weekly Tuesday expiry. If today is Tuesday, pick next week.
    - SENSEX: Weekly Thursday expiry. If today is Thursday, pick next week.
    - BANKNIFTY/others: Monthly last Tuesday expiry.
    """
    today = datetime.now().date()
    symbol_upper = symbol.upper()

    if symbol_upper == "NIFTY":
        expiry_weekday = 1  # Tuesday
        days_until = (expiry_weekday - today.weekday()) % 7
        if days_until == 0:
            days_until = 7
        expiry = today + timedelta(days=days_until)

    elif symbol_upper == "SENSEX":
        expiry_weekday = 3  # Thursday
        days_until = (expiry_weekday - today.weekday()) % 7
        if days_until == 0:
            days_until = 7
        expiry = today + timedelta(days=days_until)

    else:
        # BANKNIFTY and others: Monthly last Tuesday expiry
        import calendar

        year, month = today.year, today.month
        last_day = calendar.monthrange(year, month)[1]
        last_date = today.replace(day=last_day)

        while last_date.weekday() != 1:  # Tuesday = 1
            last_date -= timedelta(days=1)

        if today >= last_date:
            if month == 12:
                year += 1
                month = 1
            else:
                month += 1
            last_day = calendar.monthrange(year, month)[1]
            last_date = datetime(year, month, last_day).date()
            while last_date.weekday() != 1:
                last_date -= timedelta(days=1)

        expiry = last_date

    return expiry.strftime("%d%b%y").upper()


def _resolve_option(
    api_key: str, symbol: str, option_type: str, strike_offset: str
) -> tuple[str, str, int] | tuple[None, None, None]:
    """Resolve option symbol via /api/v1/optionsymbol API.

    Returns (symbol, exchange, lotsize) on success, (None, None, None) on failure.
    """
    host = os.environ.get("OPENALGO_HOST", "http://127.0.0.1:5000")
    url = f"{host}/api/v1/optionsymbol"
    expiry_date = _get_nearest_weekly_expiry(symbol)

    payload = {
        "apikey": api_key,
        "underlying": symbol,
        "exchange": "NSE_INDEX",
        "expiry_date": expiry_date,
        "offset": strike_offset,
        "option_type": option_type,
    }

    logger.info(
        f"Resolving option: {symbol} {option_type} {strike_offset} expiry={expiry_date}"
    )

    try:
        resp = requests.post(url, json=payload, timeout=10)
        data = resp.json()

        if data.get("status") == "success":
            resolved_symbol = data.get("symbol")
            exchange = data.get("exchange", "NFO")
            lotsize = int(data.get("lotsize", 75))
            logger.info(
                f"Resolved option: {resolved_symbol} on {exchange} (lot={lotsize})"
            )
            return resolved_symbol, exchange, lotsize
        else:
            logger.error(
                f"Option resolution failed: {data.get('message', 'Unknown error')}"
            )
            return None, None, None
    except requests.exceptions.Timeout:
        logger.error("Option resolution timed out")
        return None, None, None
    except Exception as e:
        logger.error(f"Option resolution error: {e}")
        return None, None, None


@dataclass
class SignalPayload:
    """Incoming TradingView alert JSON payload."""

    apikey: str  # OpenAlgo API key for authentication
    action: str  # "BUY" (only BUY supported initially)
    symbol: str  # Underlying symbol, e.g., "NIFTY"
    spot_price: float  # Current spot price from TradingView alert
    option_type: str  # "CE" or "PE" — determines which option to resolve
    order_type: str  # "LIMIT" or "MARKET"


@dataclass
class WebhookConfig:
    """Webhook configuration parsed from environment variables."""

    signal_cooldown: int  # TV_SIGNAL_COOLDOWN - seconds (default: 60)
    strike_offset: str  # TV_STRIKE_OFFSET - e.g., "ITM1" (default: "ITM1")
    lots: int  # TV_LOTS - number of lots (default: 1)
    product: str  # TV_PRODUCT - product type (default: "MIS")
    order_type: str  # TV_ORDER_TYPE - "MARKET" or "LIMIT" (default: "MARKET")

    @classmethod
    def from_env(cls) -> "WebhookConfig":
        """Parse configuration from environment variables with defaults."""
        try:
            signal_cooldown = int(os.environ.get("TV_SIGNAL_COOLDOWN", "60"))
        except (ValueError, TypeError):
            logger.warning("Invalid TV_SIGNAL_COOLDOWN value, using default: 60")
            signal_cooldown = 60

        try:
            lots = int(os.environ.get("TV_LOTS", "1"))
        except (ValueError, TypeError):
            logger.warning("Invalid TV_LOTS value, using default: 1")
            lots = 1

        return cls(
            signal_cooldown=signal_cooldown,
            strike_offset=os.environ.get("TV_STRIKE_OFFSET", "ITM1"),
            lots=lots,
            product=os.environ.get("TV_PRODUCT", "NRML"),
            order_type=os.environ.get("TV_ORDER_TYPE", "LIMIT").upper(),
        )


@tv_webhook_bp.route("/webhook", methods=["POST"])
def webhook():
    """
    Receive TradingView alert and trigger option trade pipeline.

    Expected JSON payload:
        {
            "apikey": "string",
            "action": "BUY",
            "symbol": "NIFTY",
            "spot_price": 23500.50
        }

    Returns:
        200: {status: "success", orderid: "...", symbol: "...", quantity: ...}
        400: Missing/invalid fields
        401: Invalid API key
        429: Cooldown active
        500: Monitor spawn failure
        502: Option resolution or order placement failure
    """
    # Parse JSON payload
    data = request.get_json(silent=True)
    if not data:
        return jsonify({"status": "error", "message": "Invalid or missing JSON payload"}), 400

    # Validate required fields (reject missing, None, or empty-string values)
    required_fields = ["apikey", "action", "symbol", "spot_price"]
    missing_fields = [
        f for f in required_fields
        if f not in data or data[f] is None or (isinstance(data[f], str) and not data[f].strip())
    ]
    if missing_fields:
        return (
            jsonify({
                "status": "error",
                "message": f"Missing required fields: {', '.join(missing_fields)}",
            }),
            400,
        )

    # Validate spot_price is numeric and positive
    try:
        spot_price = float(data["spot_price"])
    except (ValueError, TypeError):
        return (
            jsonify({"status": "error", "message": "spot_price must be a numeric value"}),
            400,
        )
    if spot_price <= 0:
        return (
            jsonify({"status": "error", "message": "spot_price must be a positive number"}),
            400,
        )

    # Validate action is BUY (only supported action)
    action = data["action"].strip().upper()
    if action != "BUY":
        return (
            jsonify({"status": "error", "message": "Only BUY action is supported"}),
            400,
        )

    # Authenticate API key
    api_key = data["apikey"]
    auth_token, broker = get_auth_token_broker(api_key)
    if auth_token is None:
        logger.warning("Invalid API key received at /tv/webhook")
        return jsonify({"status": "error", "message": "Invalid API key"}), 401

    # Build signal payload
    # option_type from payload (CE/PE), falls back to TV_OPTION_TYPE env var, then "CE"
    option_type = data.get("option_type", os.environ.get("TV_OPTION_TYPE", "CE")).strip().upper()
    if option_type not in ("CE", "PE"):
        return (
            jsonify({"status": "error", "message": "option_type must be 'CE' or 'PE'"}),
            400,
        )
    
    # order_type from payload (LIMIT/MARKET)
    order_type = data.get("order_type", "LIMIT").strip().upper()
    if order_type not in ("LIMIT", "MARKET"):
        return (
            jsonify({"status": "error", "message": "option_type must be 'CE' or 'PE'"}),
            400,
        )

    payload = SignalPayload(
        apikey=api_key,
        action=data["action"].upper(),
        symbol=data["symbol"],
        spot_price=spot_price,
        option_type=option_type,
        order_type=order_type
    )

    # Load webhook configuration
    config = WebhookConfig.from_env()

    # Cooldown check - reject duplicate signals within TV_SIGNAL_COOLDOWN window
    current_time = time.time()
    last_signal = _last_signal_time.get(api_key, 0)
    if (current_time - last_signal) < config.signal_cooldown:
        remaining = config.signal_cooldown - (current_time - last_signal)
        return jsonify({
            "status": "error",
            "message": f"Cooldown active. Try again in {remaining:.0f} seconds"
        }), 429

    # Set cooldown timestamp IMMEDIATELY to block concurrent/rapid signals
    # This prevents duplicate processing even if downstream steps fail
    _last_signal_time[api_key] = time.time()

    # Option resolution - resolve option contract via /api/v1/optionsymbol
    option_symbol, option_exchange, lotsize = _resolve_option(
        api_key, payload.symbol, payload.option_type, config.strike_offset
    )
    if option_symbol is None:
        return jsonify({"status": "error", "message": "Option resolution failure"}), 502

    # Compute quantity
    quantity = config.lots * lotsize
    logger.info(f"Resolved option: {option_symbol} on {option_exchange}, qty={quantity}")

    # Order placement - place BUY order via placesmartorder
    try:
        from openalgo import api as openalgo_api

        host = os.environ.get("OPENALGO_HOST", "http://127.0.0.1:5000")
        client = openalgo_api(api_key=api_key, host=host)

        # Determine price type and fetch LTP for LIMIT orders
        price_type = payload.order_type  # "MARKET" or "LIMIT"
        order_params = {
            "strategy": "TV-Signal",
            "symbol": option_symbol,
            "action": "BUY",
            "exchange": option_exchange,
            "price_type": price_type,
            "product": config.product,
            "quantity": quantity,
            "position_size": quantity,
        }

        if price_type == "LIMIT":
            # Fetch current option premium for limit price
            try:
                quotes_resp = client.quotes(symbol=option_symbol, exchange=option_exchange)
                if quotes_resp and isinstance(quotes_resp, dict):
                    if "ltp" in quotes_resp:
                        limit_price = float(quotes_resp["ltp"])
                    elif "data" in quotes_resp and isinstance(quotes_resp["data"], dict):
                        limit_price = float(quotes_resp["data"].get("ltp", 0))
                    else:
                        limit_price = 0
                else:
                    limit_price = 0
            except Exception as e:
                logger.error(f"Failed to fetch LTP for LIMIT order: {e}")
                limit_price = 0

            if limit_price <= 0:
                logger.error("Cannot place LIMIT order: LTP unavailable, falling back to MARKET")
                order_params["price_type"] = "MARKET"
            else:
                order_params["price"] = limit_price
                logger.info(f"LIMIT order price: {limit_price}")

        order_response = client.placesmartorder(**order_params)

        if (
            not isinstance(order_response, dict)
            or order_response.get("status") != "success"
        ):
            error_msg = (
                order_response.get("message", "Unknown error")
                if isinstance(order_response, dict)
                else str(order_response)
            )
            logger.error(f"Order placement failed: {error_msg}")
            return (
                jsonify({
                    "status": "error",
                    "message": f"Order placement failure: {error_msg}",
                }),
                502,
            )

        order_id = order_response.get("orderid", "")
        logger.info(
            f"Order placed: symbol={option_symbol}, qty={quantity}, orderid={order_id}"
        )
    except Exception as e:
        logger.error(f"Order placement error: {e}")
        return jsonify({"status": "error", "message": "Order placement failure"}), 502

    # Get entry price (current option premium) for monitor
    try:
        quotes_response = client.quotes(symbol=option_symbol, exchange=option_exchange)
        if quotes_response and isinstance(quotes_response, dict):
            if "ltp" in quotes_response:
                entry_price = float(quotes_response["ltp"])
            elif "data" in quotes_response and isinstance(
                quotes_response["data"], dict
            ):
                entry_price = float(quotes_response["data"].get("ltp", 0))
            else:
                entry_price = 0.0
        else:
            entry_price = 0.0
    except Exception:
        entry_price = 0.0

    # Start the trade monitor strategy (must already exist on Strategy Page)
    try:
        from blueprints.python_strategy import (
            STRATEGY_CONFIGS,
            start_strategy_process,
            save_configs,
        )

        # Find the tv_trade_monitor strategy by file name
        monitor_strategy_id = None
        for sid, sconfig in STRATEGY_CONFIGS.items():
            if "tv_trade_monitor" in sconfig.get("file_path", ""):
                monitor_strategy_id = sid
                break

        if not monitor_strategy_id:
            logger.error("TV Monitor strategy not found on Strategy Page. Create it first.")
            return jsonify({"status": "error", "message": "TV Monitor strategy not found. Create tv_trade_monitor.py on Strategy Page first."}), 500

        # Check if already running
        if monitor_strategy_id in RUNNING_STRATEGIES:
            logger.warning(f"TV Monitor '{monitor_strategy_id}' is already running, skipping spawn")
        else:
            # Inject trade-specific env vars into the strategy config
            trade_env_vars = {
                "TV_OPTION_SYMBOL": option_symbol,
                "TV_OPTION_EXCHANGE": option_exchange,
                "TV_ENTRY_PRICE": str(entry_price),
                "TV_QUANTITY": str(quantity),
                "TV_ORDER_ID": str(order_id),
                "TV_SL_PCT": os.environ.get("TV_SL_PCT", "15"),
                "TV_TRAIL_ACTIVATE_PCT": os.environ.get("TV_TRAIL_ACTIVATE_PCT", "20"),
                "TV_TRAIL_POINTS_MOVE": os.environ.get("TV_TRAIL_POINTS_MOVE", "5"),
                "TV_EXIT_TIME": os.environ.get("TV_EXIT_TIME", "15:15"),
                "TV_POLL_INTERVAL": os.environ.get("TV_POLL_INTERVAL", "5"),
                "TV_PRODUCT": config.product,
            }

            # Merge with existing env vars on the strategy (preserves any user-set vars)
            existing_env = STRATEGY_CONFIGS[monitor_strategy_id].get("env_vars", {})
            if not isinstance(existing_env, dict):
                existing_env = {}
            existing_env.update(trade_env_vars)
            STRATEGY_CONFIGS[monitor_strategy_id]["env_vars"] = existing_env
            save_configs()

            # Start the strategy using the standard mechanism
            success, message = start_strategy_process(monitor_strategy_id)
            if success:
                logger.info(f"TV Monitor started: {monitor_strategy_id} — {message}")
            else:
                logger.error(f"TV Monitor start failed: {message}")
                return jsonify({"status": "error", "message": f"Monitor start failed: {message}"}), 500

    except Exception as e:
        logger.error(f"Monitor start error: {e}")
        return jsonify({"status": "error", "message": f"Monitor start failure: {str(e)}"}), 500

    logger.info(
        f"TV webhook received: action={payload.action}, symbol={payload.symbol}, "
        f"spot_price={payload.spot_price}"
    )

    return jsonify({
        "status": "success",
        "orderid": order_id,
        "symbol": option_symbol,
        "quantity": quantity,
    }), 200
