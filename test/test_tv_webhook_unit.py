# test/test_tv_webhook_unit.py
# Unit tests for the TV Webhook endpoint
# Tests: valid payload, auth failure, missing fields, cooldown, option resolution, order placement
# Validates: Requirements 1.1, 1.2, 1.3, 1.4, 1.5, 2.3, 3.3

import os
import sys
import time
from unittest.mock import MagicMock, patch

import pytest

# Ensure project root is importable
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from flask import Flask
from blueprints.tv_webhook import tv_webhook_bp, _last_signal_time


@pytest.fixture
def client():
    """Create a minimal Flask test client with the TV webhook blueprint."""
    app = Flask(__name__)
    app.config["TESTING"] = True
    app.register_blueprint(tv_webhook_bp)
    return app.test_client()


@pytest.fixture(autouse=True)
def clear_cooldown():
    """Clear cooldown state before and after each test."""
    _last_signal_time.clear()
    yield
    _last_signal_time.clear()


def _valid_payload():
    """Return a complete valid payload for testing."""
    return {
        "apikey": "test-api-key-123",
        "action": "BUY",
        "symbol": "NIFTY",
        "spot_price": 23500.50,
    }


def _mock_full_pipeline():
    """Return a context manager that mocks all downstream dependencies for a successful pipeline."""
    mock_client_instance = MagicMock()
    mock_client_instance.placesmartorder.return_value = {"status": "success", "orderid": "12345"}
    mock_client_instance.quotes.return_value = {"ltp": 150.0}

    mock_process = MagicMock()
    mock_process.pid = 9999

    mock_openalgo_module = MagicMock()
    mock_openalgo_module.api = MagicMock(return_value=mock_client_instance)

    mock_ist_time = MagicMock()
    mock_ist_time.strftime = MagicMock(return_value="20240101_120000")

    mock_script = MagicMock()
    mock_script.exists.return_value = True
    mock_script.absolute.return_value = "/fake/tv_trade_monitor.py"

    mock_log_path = MagicMock()
    mock_log_path.parent = MagicMock()
    mock_log_path.parent.mkdir = MagicMock()
    mock_log_path.__str__ = MagicMock(return_value="/fake/logs/tv_monitor.log")

    return mock_client_instance, mock_process, mock_openalgo_module, mock_ist_time, mock_script, mock_log_path


# ===========================================================================
# Test 1: Valid payload processing returns HTTP 200
# Validates: Requirements 1.1, 1.4
# ===========================================================================


def test_valid_payload_returns_200(client):
    """A complete valid payload with all dependencies mocked should return HTTP 200
    with orderid, symbol, and quantity in the response."""
    (mock_client, mock_process, mock_openalgo, mock_ist, mock_script, mock_log_path) = _mock_full_pipeline()

    with patch("blueprints.tv_webhook.get_auth_token_broker", return_value=("token", "broker")), \
         patch("blueprints.tv_webhook._resolve_option", return_value=("NIFTY24JUN23500CE", "NFO", 75)), \
         patch.dict("sys.modules", {"openalgo": mock_openalgo}), \
         patch("blueprints.tv_webhook.subprocess.Popen", return_value=mock_process), \
         patch("blueprints.tv_webhook.build_subprocess_env", return_value=os.environ.copy()), \
         patch("blueprints.tv_webhook.get_ist_time", return_value=mock_ist), \
         patch("blueprints.tv_webhook.create_subprocess_args", return_value={}), \
         patch("blueprints.tv_webhook.get_python_executable", return_value="python"), \
         patch("blueprints.tv_webhook.LOGS_DIR", mock_log_path), \
         patch("blueprints.tv_webhook.PROCESS_LOCK", MagicMock()), \
         patch("blueprints.tv_webhook.RUNNING_STRATEGIES", {}), \
         patch("blueprints.tv_webhook.Path") as mock_path_cls, \
         patch("builtins.open", MagicMock()):

        # Setup Path mock to return the mock script for monitor path check
        mock_path_cls.return_value.parent.parent.__truediv__.return_value.__truediv__.return_value.__truediv__.return_value = mock_script

        response = client.post("/tv/webhook", json=_valid_payload())

    assert response.status_code == 200
    data = response.get_json()
    assert data["status"] == "success"
    assert data["orderid"] == "12345"
    assert data["symbol"] == "NIFTY24JUN23500CE"
    assert data["quantity"] == 75  # 1 lot × 75 lotsize


# ===========================================================================
# Test 2: Invalid API key returns HTTP 401
# Validates: Requirements 1.2
# ===========================================================================


def test_invalid_api_key_returns_401(client):
    """When get_auth_token_broker returns (None, None), the endpoint should return HTTP 401."""
    with patch("blueprints.tv_webhook.get_auth_token_broker", return_value=(None, None)):
        response = client.post("/tv/webhook", json=_valid_payload())

    assert response.status_code == 401
    data = response.get_json()
    assert data["status"] == "error"
    assert "Invalid API key" in data["message"]


# ===========================================================================
# Test 3: Missing apikey field returns HTTP 400
# Validates: Requirements 1.3
# ===========================================================================


def test_missing_apikey_returns_400(client):
    """Payload without the apikey field should return HTTP 400."""
    payload = _valid_payload()
    del payload["apikey"]

    response = client.post("/tv/webhook", json=payload)

    assert response.status_code == 400
    data = response.get_json()
    assert data["status"] == "error"
    assert "apikey" in data["message"]


# ===========================================================================
# Test 4: Missing symbol field returns HTTP 400
# Validates: Requirements 1.3
# ===========================================================================


def test_missing_symbol_returns_400(client):
    """Payload without the symbol field should return HTTP 400."""
    payload = _valid_payload()
    del payload["symbol"]

    response = client.post("/tv/webhook", json=payload)

    assert response.status_code == 400
    data = response.get_json()
    assert data["status"] == "error"
    assert "symbol" in data["message"]


# ===========================================================================
# Test 5: Missing spot_price field returns HTTP 400
# Validates: Requirements 1.3
# ===========================================================================


def test_missing_spot_price_returns_400(client):
    """Payload without the spot_price field should return HTTP 400."""
    payload = _valid_payload()
    del payload["spot_price"]

    response = client.post("/tv/webhook", json=payload)

    assert response.status_code == 400
    data = response.get_json()
    assert data["status"] == "error"
    assert "spot_price" in data["message"]


# ===========================================================================
# Test 6: Non-numeric spot_price returns HTTP 400
# Validates: Requirements 1.3
# ===========================================================================


def test_non_numeric_spot_price_returns_400(client):
    """Payload with non-numeric spot_price (e.g. 'abc') should return HTTP 400."""
    payload = _valid_payload()
    payload["spot_price"] = "abc"

    # Mock auth so we don't fail on auth before validation
    with patch("blueprints.tv_webhook.get_auth_token_broker", return_value=("token", "broker")):
        response = client.post("/tv/webhook", json=payload)

    assert response.status_code == 400
    data = response.get_json()
    assert data["status"] == "error"
    assert "numeric" in data["message"].lower() or "spot_price" in data["message"]


# ===========================================================================
# Test 7: Negative spot_price returns HTTP 400
# Validates: Requirements 1.3
# ===========================================================================


def test_negative_spot_price_returns_400(client):
    """Payload with negative spot_price should return HTTP 400."""
    payload = _valid_payload()
    payload["spot_price"] = -100

    # Mock auth so we don't fail on auth before validation
    with patch("blueprints.tv_webhook.get_auth_token_broker", return_value=("token", "broker")):
        response = client.post("/tv/webhook", json=payload)

    assert response.status_code == 400
    data = response.get_json()
    assert data["status"] == "error"
    assert "positive" in data["message"].lower() or "spot_price" in data["message"]


# ===========================================================================
# Test 8: Non-BUY action returns HTTP 400
# Validates: Requirements 1.3
# ===========================================================================


def test_non_buy_action_returns_400(client):
    """Payload with action='SELL' should return HTTP 400 since only BUY is supported."""
    payload = _valid_payload()
    payload["action"] = "SELL"

    # Mock auth so we reach action validation
    with patch("blueprints.tv_webhook.get_auth_token_broker", return_value=("token", "broker")):
        response = client.post("/tv/webhook", json=payload)

    assert response.status_code == 400
    data = response.get_json()
    assert data["status"] == "error"
    assert "BUY" in data["message"]


# ===========================================================================
# Test 9: Duplicate signal within cooldown returns HTTP 429
# Validates: Requirements 1.5
# ===========================================================================


def test_cooldown_returns_429(client):
    """Setting _last_signal_time to current time and sending immediately should return 429."""
    api_key = "test-api-key-123"
    _last_signal_time[api_key] = time.time()

    # Mock auth so we get past authentication
    with patch("blueprints.tv_webhook.get_auth_token_broker", return_value=("token", "broker")):
        response = client.post("/tv/webhook", json=_valid_payload())

    assert response.status_code == 429
    data = response.get_json()
    assert data["status"] == "error"
    assert "cooldown" in data["message"].lower() or "Cooldown" in data["message"]


# ===========================================================================
# Test 10: Option resolution failure returns HTTP 502
# Validates: Requirements 2.3
# ===========================================================================


def test_option_resolution_failure_returns_502(client):
    """When _resolve_option returns (None, None, None), endpoint should return HTTP 502."""
    with patch("blueprints.tv_webhook.get_auth_token_broker", return_value=("token", "broker")), \
         patch("blueprints.tv_webhook._resolve_option", return_value=(None, None, None)):
        response = client.post("/tv/webhook", json=_valid_payload())

    assert response.status_code == 502
    data = response.get_json()
    assert data["status"] == "error"
    assert "option resolution" in data["message"].lower() or "Option resolution" in data["message"]


# ===========================================================================
# Test 11: Order placement failure returns HTTP 502
# Validates: Requirements 3.3
# ===========================================================================


def test_order_placement_failure_returns_502(client):
    """When placesmartorder returns an error status, endpoint should return HTTP 502."""
    mock_client_instance = MagicMock()
    mock_client_instance.placesmartorder.return_value = {
        "status": "error",
        "message": "Insufficient margin",
    }

    mock_openalgo_module = MagicMock()
    mock_openalgo_module.api = MagicMock(return_value=mock_client_instance)

    with patch("blueprints.tv_webhook.get_auth_token_broker", return_value=("token", "broker")), \
         patch("blueprints.tv_webhook._resolve_option", return_value=("NIFTY24JUN23500CE", "NFO", 75)), \
         patch.dict("sys.modules", {"openalgo": mock_openalgo_module}):
        response = client.post("/tv/webhook", json=_valid_payload())

    assert response.status_code == 502
    data = response.get_json()
    assert data["status"] == "error"
    assert "order placement" in data["message"].lower() or "Order placement" in data["message"]
