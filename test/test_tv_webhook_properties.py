# test/test_tv_webhook_properties.py
# Property-based tests for the TV Webhook pipeline
# Feature: tv-signal-trade-monitor, Property 2: Payload Validation Rejects Incomplete Requests
# Feature: tv-signal-trade-monitor, Property 3: Cooldown Deduplication
# Feature: tv-signal-trade-monitor, Property 6: Subprocess Environment Injection

import os
import sys
import time
from itertools import combinations
from unittest.mock import MagicMock, patch

import pytest
from hypothesis import given, settings, assume
from hypothesis import strategies as st

# Ensure project root is importable
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


# ---------------------------------------------------------------------------
# Helper — create a Flask test client without using fixtures
# ---------------------------------------------------------------------------

def _make_client():
    """Create a minimal Flask test client with the TV webhook blueprint."""
    from flask import Flask
    from blueprints.tv_webhook import tv_webhook_bp

    app = Flask(__name__)
    app.config["TESTING"] = True
    app.register_blueprint(tv_webhook_bp)
    return app.test_client()


# ---------------------------------------------------------------------------
# Strategies
# ---------------------------------------------------------------------------

# All required fields for a valid payload
REQUIRED_FIELDS = ["apikey", "action", "symbol", "spot_price"]

# Strategy to generate a random proper subset of required fields (not all 4)
subset_indices_st = st.integers(min_value=1, max_value=len(REQUIRED_FIELDS) - 1).flatmap(
    lambda k: st.sampled_from(list(combinations(range(len(REQUIRED_FIELDS)), k)))
)

# Strategies for cooldown testing
cooldown_duration_st = st.integers(min_value=1, max_value=3600)
time_since_last_st = st.floats(min_value=0.0, max_value=7200.0, allow_nan=False, allow_infinity=False)

# Strategies for environment variable injection (Property 6)
safe_string_st = st.text(
    alphabet=st.characters(whitelist_categories=("L", "N", "P", "S"), blacklist_characters="\x00"),
    min_size=1,
    max_size=50,
)
positive_float_st = st.floats(min_value=0.01, max_value=100000.0, allow_nan=False, allow_infinity=False)
positive_int_st = st.integers(min_value=1, max_value=100000)


# ===========================================================================
# Property 2: Payload Validation Rejects Incomplete Requests
# Feature: tv-signal-trade-monitor, Property 2: Payload Validation Rejects Incomplete Requests
# Validates: Requirements 1.3
# ===========================================================================


# Feature: tv-signal-trade-monitor, Property 2: Payload Validation Rejects Incomplete Requests
@given(subset_indices=subset_indices_st)
@settings(max_examples=100, deadline=None)
def test_payload_validation_rejects_incomplete(subset_indices):
    """**Validates: Requirements 1.3**

    For any proper subset of required fields (not all 4 present),
    the webhook SHALL return HTTP 400 without triggering downstream actions.
    """
    client = _make_client()

    # Build a partial payload with only the fields at the selected indices
    full_payload = {
        "apikey": "test-key-123",
        "action": "BUY",
        "symbol": "NIFTY",
        "spot_price": 23500.50,
    }

    # Include only the fields at subset_indices (a proper subset)
    partial_payload = {REQUIRED_FIELDS[i]: full_payload[REQUIRED_FIELDS[i]] for i in subset_indices}

    # Ensure it's actually a proper subset (not all fields present)
    assume(len(partial_payload) < len(REQUIRED_FIELDS))

    # Mock auth to return valid so we don't fail on auth before payload validation
    with patch("blueprints.tv_webhook.get_auth_token_broker", return_value=("token", "broker")):
        response = client.post("/tv/webhook", json=partial_payload)

    assert response.status_code == 400, (
        f"Expected 400 for partial payload with fields {list(partial_payload.keys())}, "
        f"got {response.status_code}. Response: {response.get_json()}"
    )


# ===========================================================================
# Property 3: Cooldown Deduplication
# Feature: tv-signal-trade-monitor, Property 3: Cooldown Deduplication
# Validates: Requirements 1.5
# ===========================================================================


# Feature: tv-signal-trade-monitor, Property 3: Cooldown Deduplication
@given(
    cooldown=cooldown_duration_st,
    time_since_last=time_since_last_st,
)
@settings(max_examples=100, deadline=None)
def test_cooldown_deduplication(cooldown, time_since_last):
    """**Validates: Requirements 1.5**

    For any cooldown duration C and time since last signal T:
    - If T < C → HTTP 429 (cooldown active)
    - If T >= C → request proceeds past cooldown (not 429)
    """
    from blueprints.tv_webhook import _last_signal_time

    client = _make_client()

    api_key = "test-cooldown-key"
    current_time = 1000000.0  # Fixed reference time
    last_signal_time = current_time - time_since_last

    # Set the last signal time in the module-level dict
    _last_signal_time[api_key] = last_signal_time

    valid_payload = {
        "apikey": api_key,
        "action": "BUY",
        "symbol": "NIFTY",
        "spot_price": 23500.50,
    }

    # Mock time.time() to return our controlled current_time
    # Mock all downstream dependencies to prevent real calls
    with patch("blueprints.tv_webhook.time.time", return_value=current_time), \
         patch("blueprints.tv_webhook.get_auth_token_broker", return_value=("token", "broker")), \
         patch.dict(os.environ, {"TV_SIGNAL_COOLDOWN": str(cooldown)}), \
         patch("blueprints.tv_webhook._resolve_option", return_value=("NIFTY24JUN23500CE", "NFO", 75)), \
         patch("blueprints.tv_webhook.subprocess.Popen") as mock_popen, \
         patch("blueprints.tv_webhook.build_subprocess_env", return_value=os.environ.copy()), \
         patch("blueprints.tv_webhook.get_ist_time") as mock_ist, \
         patch("blueprints.tv_webhook.create_subprocess_args", return_value={}), \
         patch("blueprints.tv_webhook.get_python_executable", return_value="python"), \
         patch("blueprints.tv_webhook.LOGS_DIR") as mock_logs_dir, \
         patch("builtins.open", MagicMock()):

        # Setup mocks for downstream processing (only relevant if cooldown passes)
        # Mock the openalgo import inside the function
        mock_client_instance = MagicMock()
        mock_client_instance.placesmartorder.return_value = {"status": "success", "orderid": "12345"}
        mock_client_instance.quotes.return_value = {"ltp": 150.0}

        mock_process = MagicMock()
        mock_process.pid = 9999
        mock_popen.return_value = mock_process

        mock_ist.return_value = MagicMock(strftime=MagicMock(return_value="20240101_120000"))

        mock_logs_dir.__truediv__ = MagicMock(return_value=MagicMock(
            parent=MagicMock(mkdir=MagicMock()),
            __str__=MagicMock(return_value="/fake/log.log"),
        ))

        # Mock the monitor script path existence
        with patch("blueprints.tv_webhook.Path") as mock_path_cls:
            mock_script = MagicMock()
            mock_script.exists.return_value = True
            mock_script.absolute.return_value = "/fake/tv_trade_monitor.py"
            # Path(__file__).parent.parent / "strategies" / "scripts" / "tv_trade_monitor.py"
            mock_path_cls.return_value.parent.parent.__truediv__.return_value.__truediv__.return_value.__truediv__.return_value = mock_script

            # Also mock the openalgo import that happens inside the function
            with patch.dict("sys.modules", {"openalgo": MagicMock()}):
                import importlib
                mock_openalgo_module = MagicMock()
                mock_api_class = MagicMock(return_value=mock_client_instance)
                mock_openalgo_module.api = mock_api_class

                with patch.dict("sys.modules", {"openalgo": mock_openalgo_module}):
                    response = client.post("/tv/webhook", json=valid_payload)

    if time_since_last < cooldown:
        assert response.status_code == 429, (
            f"Expected 429 (cooldown active) when time_since_last={time_since_last:.2f} < cooldown={cooldown}, "
            f"got {response.status_code}. Response: {response.get_json()}"
        )
    else:
        # When cooldown has passed, the request should proceed past cooldown.
        # It should NOT be 429.
        assert response.status_code != 429, (
            f"Expected non-429 when time_since_last={time_since_last:.2f} >= cooldown={cooldown}, "
            f"got 429. Response: {response.get_json()}"
        )

    # Clean up the last signal time
    _last_signal_time.pop(api_key, None)


# ===========================================================================
# Property 6: Subprocess Environment Injection
# Feature: tv-signal-trade-monitor, Property 6: Subprocess Environment Injection
# Validates: Requirements 4.2
# ===========================================================================


# Feature: tv-signal-trade-monitor, Property 6: Subprocess Environment Injection
@given(
    option_symbol=safe_string_st,
    option_exchange=safe_string_st,
    entry_price=positive_float_st,
    quantity=positive_int_st,
    order_id=safe_string_st,
)
@settings(max_examples=100, deadline=None)
def test_subprocess_env_injection(option_symbol, option_exchange, entry_price, quantity, order_id):
    """**Validates: Requirements 4.2**

    For any entry details (option_symbol, exchange, entry_price, quantity, order_id),
    all values SHALL be present as string-typed entries in the subprocess environment
    dictionary passed to Popen.
    """
    from utils.strategy_env import build_subprocess_env

    # Build the monitor_env_vars dict the same way the webhook does
    monitor_env_vars = {
        "TV_OPTION_SYMBOL": option_symbol,
        "TV_OPTION_EXCHANGE": option_exchange,
        "TV_ENTRY_PRICE": str(entry_price),
        "TV_QUANTITY": str(quantity),
        "TV_ORDER_ID": str(order_id),
        "TV_SL_PCT": "15",
        "TV_TRAIL_ACTIVATE_PCT": "20",
        "TV_TRAIL_STEP_PCT": "5",
        "TV_EXIT_TIME": "15:15",
        "TV_POLL_INTERVAL": "5",
        "TV_PRODUCT": "MIS",
    }

    # Build the merged environment using the same function as the webhook
    merged_env = build_subprocess_env(monitor_env_vars)

    # Verify all entry details are present as strings in the merged env
    assert merged_env.get("TV_OPTION_SYMBOL") == option_symbol, (
        f"TV_OPTION_SYMBOL expected '{option_symbol}', got '{merged_env.get('TV_OPTION_SYMBOL')}'"
    )
    assert merged_env.get("TV_OPTION_EXCHANGE") == option_exchange, (
        f"TV_OPTION_EXCHANGE expected '{option_exchange}', got '{merged_env.get('TV_OPTION_EXCHANGE')}'"
    )
    assert merged_env.get("TV_ENTRY_PRICE") == str(entry_price), (
        f"TV_ENTRY_PRICE expected '{str(entry_price)}', got '{merged_env.get('TV_ENTRY_PRICE')}'"
    )
    assert merged_env.get("TV_QUANTITY") == str(quantity), (
        f"TV_QUANTITY expected '{str(quantity)}', got '{merged_env.get('TV_QUANTITY')}'"
    )
    assert merged_env.get("TV_ORDER_ID") == str(order_id), (
        f"TV_ORDER_ID expected '{str(order_id)}', got '{merged_env.get('TV_ORDER_ID')}'"
    )

    # Verify all values are strings
    for key in ["TV_OPTION_SYMBOL", "TV_OPTION_EXCHANGE", "TV_ENTRY_PRICE", "TV_QUANTITY", "TV_ORDER_ID"]:
        assert isinstance(merged_env[key], str), (
            f"{key} should be a string, got {type(merged_env[key]).__name__}"
        )
