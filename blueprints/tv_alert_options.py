# blueprints/tv_alert_options.py

import re
from datetime import datetime

from flask import Blueprint, request
from flask_restx import Namespace, Resource
from sqlalchemy import distinct

from database.apilog_db import async_log_order, executor
from database.auth_db import get_auth_token_broker, verify_api_key
from database.settings_db import get_tv_alert_config
from database.strategy_db import Strategy, db_session as strategy_db_session
from database.symbol import SymToken, db_session as symbol_db_session
from events import OrderFailedEvent, OrderPlacedEvent
from services.option_symbol_service import get_option_symbol
from services.place_order_service import place_order as place_order_via_service
from utils.event_bus import bus
from utils.logging import get_logger

logger = get_logger(__name__)

tv_alert_options_bp = Blueprint("tv_alert_options", __name__)
api = Namespace("tv_alert_options", description="TradingView Alert Options Trading API")

# Required fields for the TV alert payload (apikey handled separately in auth step)
REQUIRED_FIELDS = ["cmp", "symbol", "charttype", "signal", "option_type", "sl", "target"]

# Valid enum values (stored uppercase for case-insensitive comparison)
VALID_SIGNALS = {"BUY", "SELL"}
VALID_CHARTTYPES = {"SPOT_OPTIONS", "SPOT_FUTURE", "OPTIONS"}
VALID_OPTION_TYPES = {"CE", "PE"}


def validate_tv_alert_payload(data: dict) -> tuple:
    """
    Validate the incoming TV alert payload for required fields and enum values.

    This is a pure function with no Flask request context dependency,
    making it independently unit-testable.

    Args:
        data: Raw JSON payload from the webhook

    Returns:
        Tuple of (is_valid, error_message)
        - (True, None) if valid
        - (False, "Missing required fields: ...") if fields are missing
        - (False, "Invalid <field>: ...") if enum values are invalid
    """
    if not data or not isinstance(data, dict):
        return False, "Invalid payload: expected a JSON object"

    # Check for missing required fields
    missing_fields = [field for field in REQUIRED_FIELDS if field not in data or data[field] is None]
    if missing_fields:
        return False, f"Missing required fields: {', '.join(missing_fields)}"

    # Validate signal enum (case-insensitive)
    signal = str(data["signal"]).strip().upper()
    if signal not in VALID_SIGNALS:
        return False, f"Invalid signal value: '{data['signal']}'. Must be one of: BUY, SELL"

    # Validate charttype enum (case-insensitive)
    charttype = str(data["charttype"]).strip().upper()
    if charttype not in VALID_CHARTTYPES:
        return False, f"Invalid charttype value: '{data['charttype']}'. Must be one of: SPOT_OPTIONS, SPOT_FUTURE, OPTIONS"

    # Validate option_type enum (only required for SPOT_OPTIONS)
    if charttype == "SPOT_OPTIONS":
        option_type = str(data["option_type"]).strip().upper()
        if option_type not in VALID_OPTION_TYPES:
            return False, f"Invalid option_type value: '{data['option_type']}'. Must be one of: CE, PE"

    return True, None


def authenticate_api_key(api_key: str) -> tuple:
    """
    Authenticate an API key using the existing auth infrastructure.

    Args:
        api_key: The API key from the webhook payload

    Returns:
        Tuple of (success, auth_token, error_message)
        - (True, auth_token, None) if authentication succeeds
        - (False, None, "Invalid API key") if authentication fails
    """
    if not api_key:
        return False, None, "Invalid API key"

    auth_token, broker = get_auth_token_broker(api_key)

    if auth_token is None:
        return False, None, "Invalid API key"

    return True, auth_token, None


def check_feature_enabled() -> tuple:
    """
    Check if the TV Alert Options trading feature is enabled in settings.

    Returns:
        Tuple of (is_enabled, error_message)
        - (True, None) if feature is enabled
        - (False, "TV Alert Options trading is disabled") if disabled
    """
    config = get_tv_alert_config()
    if not config.get("enabled", True):
        return False, "TV Alert Options trading is disabled"

    return True, None


def check_strategy_active(strategy_name: str, user_id: str) -> tuple:
    """
    Check if the named strategy exists and is active for the given user.

    Uses the existing Strategy model from strategy_db. The strategy_name is
    configured via the TV alert settings (e.g., "TV-Alert-Options").

    Args:
        strategy_name: Name of the strategy to check
        user_id: The authenticated user ID

    Returns:
        Tuple of (is_active, message)
        - (True, None) if strategy exists and is_active=True
        - (False, "Strategy 'X' not found for user") if not found
        - (False, "Strategy 'X' is inactive, alert ignored") if found but inactive
    """
    try:
        strategy = strategy_db_session.query(Strategy).filter_by(
            name=strategy_name, user_id=user_id
        ).first()
    except Exception as e:
        logger.error(f"Error querying strategy '{strategy_name}' for user '{user_id}': {e}")
        return False, f"Strategy '{strategy_name}' not found for user"

    if not strategy:
        return False, f"Strategy '{strategy_name}' not found for user"

    if not strategy.is_active:
        return False, f"Strategy '{strategy_name}' is inactive, alert ignored"

    return True, None


def get_nearest_expiry(symbol: str, exchange: str) -> str | None:
    """
    Query SymToken table for the nearest future expiry of the given symbol.

    Finds all distinct expiry dates for the symbol on the given exchange,
    then returns the one that is nearest to (but not before) today's date,
    converted to DDMMMYY format (e.g., "28NOV25").

    Args:
        symbol: Underlying symbol (e.g., "NIFTY")
        exchange: Options exchange (e.g., "NFO")

    Returns:
        Expiry date in DDMMMYY format (e.g., "28NOV25") or None if not found
    """
    try:
        # Query distinct expiries for the symbol on the exchange
        # The 'name' column holds the underlying name (e.g., "NIFTY")
        results = (
            symbol_db_session.query(distinct(SymToken.expiry))
            .filter(
                SymToken.name.ilike(symbol.strip().upper()),
                SymToken.exchange == exchange.upper(),
                SymToken.expiry.isnot(None),
                SymToken.expiry != "",
            )
            .all()
        )

        if not results:
            logger.warning(f"No expiry dates found for {symbol} on {exchange}")
            return None

        expiries = [r[0] for r in results if r[0]]
        if not expiries:
            logger.warning(f"No valid expiry dates found for {symbol} on {exchange}")
            return None

        # Parse expiry dates and find the nearest future one
        today = datetime.now().date()
        nearest_expiry = None
        nearest_date = None

        for expiry_str in expiries:
            try:
                # Database stores expiry in DD-MMM-YY format (e.g., "28-Nov-25")
                exp_date = datetime.strptime(expiry_str, "%d-%b-%y").date()
            except ValueError:
                try:
                    # Fallback: try DD-MMM-YYYY format
                    exp_date = datetime.strptime(expiry_str, "%d-%b-%Y").date()
                except ValueError:
                    continue

            # Only consider expiries that are today or in the future
            if exp_date >= today:
                if nearest_date is None or exp_date < nearest_date:
                    nearest_date = exp_date
                    nearest_expiry = expiry_str

        if nearest_expiry is None:
            logger.warning(f"No future expiry dates found for {symbol} on {exchange}")
            return None

        # Convert from DD-MMM-YY (e.g., "28-Nov-25") to DDMMMYY (e.g., "28NOV25")
        # Remove hyphens and uppercase
        parts = nearest_expiry.split("-")
        if len(parts) == 3:
            ddmmmyy = f"{parts[0]}{parts[1].upper()}{parts[2]}"
        else:
            # Fallback: try to format from the parsed date
            ddmmmyy = nearest_date.strftime("%d%b%y").upper()

        logger.info(f"Nearest expiry for {symbol} on {exchange}: {ddmmmyy}")
        return ddmmmyy

    except Exception as e:
        logger.error(f"Error resolving nearest expiry for {symbol} on {exchange}: {e}")
        return None


def resolve_option_symbol(
    symbol: str,
    cmp: float,
    option_type: str,
    api_key: str,
    exchange: str,
) -> tuple:
    """
    Resolve the ITM2 option symbol for a SPOT alert.

    For charttype "SPOT", this function:
    1. Determines the nearest available expiry for the symbol
    2. Calls option_symbol_service.get_option_symbol() with offset "ITM2"
       and uses ltp_override=cmp to avoid redundant quote API calls

    For charttype "OPTION", the caller should bypass this function entirely
    and use the symbol field directly.

    Args:
        symbol: Underlying symbol (e.g., "NIFTY")
        cmp: Current Market Price from the alert
        option_type: "CE" or "PE"
        api_key: User's API key
        exchange: Options exchange (e.g., "NFO")

    Returns:
        Tuple of (success, resolved_symbol, error_message)
        - (True, "NIFTY28NOV2523500CE", None) on success
        - (False, None, "descriptive error message") on failure
    """
    # Step 1: Resolve nearest expiry
    expiry = get_nearest_expiry(symbol, exchange)
    if not expiry:
        error_msg = f"No expiry dates found for {symbol} on {exchange}. Please check symbol or update master contract."
        logger.error(error_msg)
        return False, None, error_msg

    # Step 2: Call option_symbol_service.get_option_symbol() with ITM2 offset
    # strike_int=None uses the new actual-strikes method (recommended)
    # underlying_ltp=cmp avoids a redundant quote API call
    success, response_data, status_code = get_option_symbol(
        underlying=symbol.upper(),
        exchange=exchange.upper(),
        expiry_date=expiry,
        strike_int=None,
        offset="ITM2",
        option_type=option_type.upper(),
        api_key=api_key,
        underlying_ltp=cmp,
    )

    if not success:
        # Extract descriptive error from the response
        error_msg = response_data.get("message", "Unknown error during option symbol resolution")
        logger.error(f"Option symbol resolution failed for {symbol}: {error_msg}")
        return False, None, error_msg

    # Extract the resolved symbol
    resolved_symbol = response_data.get("symbol")
    if not resolved_symbol:
        error_msg = f"Option symbol resolution returned empty symbol for {symbol}"
        logger.error(error_msg)
        return False, None, error_msg

    logger.info(
        f"Resolved option symbol: {resolved_symbol} "
        f"(underlying={symbol}, cmp={cmp}, option_type={option_type}, expiry={expiry})"
    )
    return True, resolved_symbol, None


def resolve_future_symbol(symbol: str, exchange: str) -> tuple:
    """
    Resolve the current month future symbol for a given underlying.

    Queries the SymToken table for FUT entries of the symbol on the given exchange
    and returns the nearest-expiry future contract symbol.

    Args:
        symbol: Underlying symbol (e.g., "NIFTY")
        exchange: Futures exchange (e.g., "NFO")

    Returns:
        Tuple of (success, resolved_symbol, error_message)
        - (True, "NIFTY26JUNFUT", None) on success
        - (False, None, "descriptive error") on failure
    """
    try:
        today = datetime.now().date()

        # Query SymToken for FUT instruments matching this symbol
        # Try multiple instrument types: FUTIDX (index), FUTSTK (stock), FUT (MCX/generic)
        fut_types = ["FUTIDX", "FUTSTK", "FUT", "FUTCOM", "FUTCUR"]
        results = []

        for fut_type in fut_types:
            results = (
                symbol_db_session.query(SymToken)
                .filter(
                    SymToken.name.ilike(symbol.strip().upper()),
                    SymToken.exchange == exchange.upper(),
                    SymToken.instrumenttype == fut_type,
                    SymToken.expiry.isnot(None),
                    SymToken.expiry != "",
                )
                .all()
            )
            if results:
                break

        if not results:
            error_msg = f"No future contracts found for {symbol} on {exchange}"
            logger.error(error_msg)
            return False, None, error_msg

        # Find the nearest future expiry (current month or next available)
        nearest_future = None
        nearest_date = None

        for row in results:
            try:
                exp_date = datetime.strptime(row.expiry, "%d-%b-%y").date()
            except ValueError:
                try:
                    exp_date = datetime.strptime(row.expiry, "%d-%b-%Y").date()
                except ValueError:
                    continue

            if exp_date >= today:
                if nearest_date is None or exp_date < nearest_date:
                    nearest_date = exp_date
                    nearest_future = row

        if not nearest_future:
            error_msg = f"No current/future month contracts found for {symbol} on {exchange}"
            logger.error(error_msg)
            return False, None, error_msg

        # Use the symbol field from SymToken (the broker trading symbol)
        resolved_symbol = nearest_future.symbol
        logger.info(
            f"Resolved future symbol: {resolved_symbol} "
            f"(underlying={symbol}, expiry={nearest_future.expiry})"
        )
        return True, resolved_symbol, None

    except Exception as e:
        error_msg = f"Error resolving future symbol for {symbol} on {exchange}: {e}"
        logger.error(error_msg)
        return False, None, error_msg


def build_order_data(
    api_key: str,
    resolved_symbol: str,
    signal: str,
    sl: float,
    target: float,
    exchange: str,
) -> dict:
    """
    Construct the order data dictionary for place_order_service.

    Uses get_tv_alert_config() to retrieve the configured quantity, product type,
    and exchange. The signal ("BUY" or "SELL") is passed directly as the order action.

    Args:
        api_key: User's API key
        resolved_symbol: Resolved option symbol (e.g., "NIFTY28NOV2523500CE")
        signal: "BUY" or "SELL" — used directly as order action
        sl: Stop-loss points from the alert
        target: Target points from the alert
        exchange: Trading exchange (e.g., "NFO") — override from alert or config

    Returns:
        Order data dictionary compatible with place_order_service
    """
    config = get_tv_alert_config()

    # Use configured values from settings
    configured_quantity = config.get("quantity", 1)
    configured_product = config.get("product", "MIS")
    configured_exchange = exchange or config.get("exchange", "NFO")

    order_data = {
        "apikey": api_key,
        "strategy": "TV Alert Options",
        "symbol": resolved_symbol,
        "exchange": configured_exchange,
        "action": signal.upper(),
        "quantity": str(configured_quantity),
        "pricetype": "MARKET",
        "product": configured_product,
        "price": "0",
        "trigger_price": "0",
        "disclosed_quantity": "0",
        "target": str(target),
        "stoploss": str(sl),
    }

    return order_data


def place_tv_alert_order(order_data: dict) -> tuple:
    """
    Place an order via place_order_service, handling bracket order support.

    Attempts to place the order with stoploss and target fields. Since the
    current place_order_service pipeline does not support bracket orders
    (stoploss/target as bracket legs), this function:
    1. Logs a warning that bracket orders are not supported
    2. Strips the stoploss/target fields from the order data
    3. Places a plain MARKET order without SL/target attached

    Args:
        order_data: Complete order data dictionary (from build_order_data)

    Returns:
        Tuple of (success, response_data, error_message)
        - (True, response_dict, None) on success
        - (False, response_dict_or_None, "error description") on failure
    """
    api_key = order_data.get("apikey", "")
    sl_value = order_data.get("stoploss", "0")
    target_value = order_data.get("target", "0")

    # Check if bracket order fields are present (SL or target > 0)
    has_bracket_fields = False
    try:
        has_bracket_fields = float(sl_value) > 0 or float(target_value) > 0
    except (ValueError, TypeError):
        pass

    if has_bracket_fields:
        logger.warning(
            f"Bracket orders (SL={sl_value}, Target={target_value}) not supported "
            f"by current broker pipeline. Placing plain MARKET order without SL/Target attached. "
            f"Symbol: {order_data.get('symbol')}, Action: {order_data.get('action')}"
        )

    # Strip bracket order fields that are not supported by the order schema
    plain_order_data = {k: v for k, v in order_data.items() if k not in ("stoploss", "target")}

    # Place the order via place_order_service
    success, response_data, status_code = place_order_via_service(
        order_data=plain_order_data,
        api_key=api_key,
    )

    if success:
        logger.info(
            f"TV Alert order placed successfully: "
            f"symbol={order_data.get('symbol')}, action={order_data.get('action')}, "
            f"order_id={response_data.get('orderid', 'N/A')}"
        )
        return True, response_data, None
    else:
        error_message = response_data.get("message", "Unknown error during order placement")
        logger.error(
            f"TV Alert order placement failed: "
            f"symbol={order_data.get('symbol')}, action={order_data.get('action')}, "
            f"error={error_message}"
        )
        return False, response_data, error_message


def log_tv_alert(request_data: dict, response_data: dict) -> None:
    """
    Submit async_log_order to the ThreadPoolExecutor (fire-and-forget).

    Logs both successful and failed TV alert requests to the existing order_logs
    table using the "tv_alert_options" api_type identifier.

    Args:
        request_data: The incoming alert payload (should have apikey stripped)
        response_data: The response returned to the caller
    """
    executor.submit(async_log_order, "tv_alert_options", request_data, response_data)


def emit_order_event(
    success: bool,
    order_data: dict,
    response_data: dict,
    error_message: str | None = None,
) -> None:
    """
    Emit OrderPlacedEvent on success or OrderFailedEvent on failure via the event bus.

    Args:
        success: Whether the order was placed successfully
        order_data: The order data dict (contains symbol, exchange, action, quantity, apikey, etc.)
        response_data: The response from the order placement (contains orderid on success)
        error_message: Error description (used only on failure)
    """
    # Build request_data without the apikey for logging safety
    safe_request = {k: v for k, v in order_data.items() if k != "apikey"}
    api_key = order_data.get("apikey", "")

    if success:
        bus.publish(OrderPlacedEvent(
            mode="live",
            api_type="tv_alert_options",
            strategy=order_data.get("strategy", ""),
            symbol=order_data.get("symbol", ""),
            exchange=order_data.get("exchange", ""),
            action=order_data.get("action", ""),
            quantity=int(order_data.get("quantity", 0)),
            pricetype=order_data.get("pricetype", ""),
            product=order_data.get("product", ""),
            orderid=response_data.get("orderid", response_data.get("order_id", "")),
            request_data=safe_request,
            response_data=response_data,
            api_key=api_key,
        ))
    else:
        bus.publish(OrderFailedEvent(
            mode="live",
            api_type="tv_alert_options",
            request_data=safe_request,
            response_data=response_data or {},
            api_key=api_key,
            symbol=order_data.get("symbol", ""),
            exchange=order_data.get("exchange", ""),
            error_message=error_message or "Unknown error",
        ))


def process_tv_alert(data: dict) -> tuple:
    """
    Main processing function for a TV alert webhook.

    Orchestrates the full flow:
    1. Authenticate API key
    2. Check feature enabled
    3. Validate payload
    4. Check strategy is_active flag (gate)
    5. Resolve option symbol (if SPOT charttype)
    6. Build and place order
    7. Log via async_log_order
    8. Emit event bus event

    Args:
        data: Raw JSON payload from the webhook

    Returns:
        Tuple of (response_dict, http_status_code)
    """
    # Log incoming alert payload at INFO level (Req 1.4)
    logger.info(f"TV Alert received: {data}")

    # Step 1: Extract and authenticate API key
    api_key = data.get("apikey", "")
    success, auth_token, error_msg = authenticate_api_key(api_key)
    if not success:
        response = {"status": "error", "message": error_msg}
        log_tv_alert(data, response)
        return response, 403

    # Get user_id from the API key for strategy gate check
    user_id = verify_api_key(api_key)

    # Step 2: Check feature enabled
    enabled, error_msg = check_feature_enabled()
    if not enabled:
        response = {"status": "error", "message": error_msg}
        log_tv_alert(data, response)
        return response, 403

    # Step 3: Validate payload
    is_valid, error_msg = validate_tv_alert_payload(data)
    if not is_valid:
        response = {"status": "error", "message": error_msg}
        log_tv_alert(data, response)
        return response, 400

    # Step 4: Get TV alert config and check strategy gate
    config = get_tv_alert_config()
    strategy_name = config.get("strategy", "TV-Alert-Options")

    is_active, message = check_strategy_active(strategy_name, user_id)
    if not is_active:
        response = {"status": "ignored", "message": message}
        log_tv_alert(data, response)
        return response, 200

    # Normalize input values
    charttype = str(data["charttype"]).strip().upper()
    signal = str(data["signal"]).strip().upper()
    option_type = str(data["option_type"]).strip().upper()
    symbol = str(data["symbol"]).strip()
    # Strip TradingView continuous contract suffixes (e.g., "1!", "2!")
    symbol = re.sub(r'\d+!$', '', symbol)
    cmp = float(data["cmp"])
    sl = float(data["sl"])
    target = float(data["target"])
    exchange = str(data.get("exchange", "")).strip().upper() or config.get("exchange", "NFO")

    # Step 5: Resolve symbol based on chart_type
    if charttype == "SPOT_OPTIONS":
        success, resolved_symbol, error_msg = resolve_option_symbol(
            symbol=symbol,
            cmp=cmp,
            option_type=option_type,
            api_key=api_key,
            exchange=exchange,
        )
        if not success:
            response = {"status": "error", "message": error_msg}
            log_tv_alert(data, response)
            return response, 500
    elif charttype == "SPOT_FUTURE":
        success, resolved_symbol, error_msg = resolve_future_symbol(
            symbol=symbol,
            exchange=exchange,
        )
        if not success:
            response = {"status": "error", "message": error_msg}
            log_tv_alert(data, response)
            return response, 500
    elif charttype == "OPTIONS":
        # Use symbol directly as the option symbol
        resolved_symbol = symbol
    else:
        response = {"status": "error", "message": f"Invalid charttype: {charttype}"}
        log_tv_alert(data, response)
        return response, 400

    # Step 6: Build order data and place order
    order_data = build_order_data(
        api_key=api_key,
        resolved_symbol=resolved_symbol,
        signal=signal,
        sl=sl,
        target=target,
        exchange=exchange,
    )

    order_success, response_data, error_msg = place_tv_alert_order(order_data)

    # Step 7: Emit event
    emit_order_event(
        success=order_success,
        order_data=order_data,
        response_data=response_data or {},
        error_message=error_msg,
    )

    # Step 8: Build response and log
    if order_success:
        response = {
            "status": "success",
            "order_id": response_data.get("orderid", response_data.get("order_id", "")),
            "resolved_symbol": resolved_symbol,
            "action": signal,
            "message": "Order placed successfully",
        }
        log_tv_alert(data, response)
        return response, 200
    else:
        response = {
            "status": "error",
            "message": error_msg or "Order placement failed",
        }
        log_tv_alert(data, response)
        return response, 500


@api.route("/", strict_slashes=False)
class TvAlertOptionsResource(Resource):
    """TradingView Alert Options Trading endpoint"""

    def post(self):
        """Process a TradingView alert for options trading"""
        try:
            data = request.json
            if not data:
                return {"status": "error", "message": "Invalid payload: expected a JSON object"}, 400

            response, status_code = process_tv_alert(data)
            return response, status_code

        except Exception:
            logger.exception("An unexpected error occurred in TvAlertOptions endpoint.")
            error_response = {
                "status": "error",
                "message": "An unexpected error occurred while processing the TV alert",
            }
            return error_response, 500
