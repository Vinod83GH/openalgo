# test/test_tv_integration.py
# Integration tests for end-to-end TV Signal Trade Monitor pipeline
# Feature: tv-signal-trade-monitor
# Tests: Full pipeline (webhook → option resolve → order → monitor spawn),
#         RUNNING_STRATEGIES registration, SIGTERM handling
# Validates: Requirements 4.3, 7.1, 7.3

import os
import sys
import threading
from unittest.mock import MagicMock, patch, mock_open

import pytest

# Ensure project root is importable
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def app():
    """Create a minimal Flask app with the TV webhook blueprint."""
    from flask import Flask
    from blueprints.tv_webhook import tv_webhook_bp

    app = Flask(__name__)
    app.config["TESTING"] = True
    app.register_blueprint(tv_webhook_bp)
    return app


@pytest.fixture
def client(app):
    """Create a Flask test client."""
    return app.test_client()


@pytest.fixture(autouse=True)
def clear_cooldown():
    """Clear cooldown state between tests."""
    from blueprints.tv_webhook import _last_signal_time
    _last_signal_time.clear()
    yield
    _last_signal_time.clear()


@pytest.fixture
def valid_payload():
    """A valid TradingView webhook payload."""
    return {
        "apikey": "integration-test-key",
        "action": "BUY",
        "symbol": "NIFTY",
        "spot_price": 23500.50,
    }


@pytest.fixture
def mocked_pipeline(client):
    """Mock all external dependencies for a full pipeline test."""
    mock_process = MagicMock()
    mock_process.pid = 12345

    mock_ist = MagicMock()
    mock_ist.strftime = MagicMock(return_value="20240101_120000")

    mock_log_path = MagicMock()
    mock_log_path.parent = MagicMock()
    mock_log_path.parent.mkdir = MagicMock()
    mock_log_path.__str__ = MagicMock(return_value="/fake/tv_monitor_20240101_120000_IST.log")

    mock_script = MagicMock()
    mock_script.exists.return_value = True
    mock_script.absolute.return_value = "/fake/tv_trade_monitor.py"

    # Mock openalgo module
    mock_client_instance = MagicMock()
    mock_client_instance.placesmartorder.return_value = {"status": "success", "orderid": "ORD123"}
    mock_client_instance.quotes.return_value = {"ltp": 150.0}

    mock_openalgo_module = MagicMock()
    mock_openalgo_module.api = MagicMock(return_value=mock_client_instance)

    running_strategies = {}

    with patch("blueprints.tv_webhook.get_auth_token_broker", return_value=("token", "dhan")), \
         patch("blueprints.tv_webhook._resolve_option", return_value=("NIFTY24JUN23500CE", "NFO", 75)), \
         patch("blueprints.tv_webhook.subprocess.Popen", return_value=mock_process) as mock_popen, \
         patch("blueprints.tv_webhook.build_subprocess_env", return_value=os.environ.copy()), \
         patch("blueprints.tv_webhook.get_ist_time", return_value=mock_ist), \
         patch("blueprints.tv_webhook.create_subprocess_args", return_value={}), \
         patch("blueprints.tv_webhook.get_python_executable", return_value="python"), \
         patch("blueprints.tv_webhook.LOGS_DIR", MagicMock(__truediv__=MagicMock(return_value=mock_log_path))), \
         patch("blueprints.tv_webhook.PROCESS_LOCK", threading.Lock()), \
         patch("blueprints.tv_webhook.RUNNING_STRATEGIES", running_strategies), \
         patch("builtins.open", mock_open()), \
         patch("blueprints.tv_webhook.Path") as mock_path_cls, \
         patch.dict("sys.modules", {"openalgo": mock_openalgo_module}):

        # Setup Path mock so monitor script "exists"
        mock_path_cls.return_value.parent.parent.__truediv__.return_value.__truediv__.return_value.__truediv__.return_value = mock_script
        # Also mock Path.cwd() for subprocess cwd arg
        mock_path_cls.cwd.return_value = "/fake/workdir"

        yield {
            "mock_popen": mock_popen,
            "mock_process": mock_process,
            "running_strategies": running_strategies,
            "mock_client": mock_client_instance,
            "mock_openalgo_module": mock_openalgo_module,
        }


# ===========================================================================
# Test 1: Full pipeline — webhook receive → option resolve → order → monitor spawn
# Validates: Requirements 4.3, 7.1
# ===========================================================================


def test_full_pipeline_webhook_to_monitor_spawn(client, valid_payload, mocked_pipeline):
    """
    Integration test: Full flow from webhook receive through monitor spawn.

    Verifies:
    - HTTP 200 response with orderid, symbol, quantity
    - subprocess.Popen was called (monitor spawned)
    - Process registered in RUNNING_STRATEGIES
    """
    response = client.post("/tv/webhook", json=valid_payload)

    # Verify HTTP 200 success response
    assert response.status_code == 200, (
        f"Expected HTTP 200, got {response.status_code}. "
        f"Response: {response.get_json()}"
    )

    data = response.get_json()
    assert data["status"] == "success"
    assert data["orderid"] == "ORD123"
    assert data["symbol"] == "NIFTY24JUN23500CE"
    assert data["quantity"] == 75

    # Verify subprocess.Popen was called (monitor was spawned)
    mocked_pipeline["mock_popen"].assert_called_once()

    # Verify the spawned command includes python and the monitor script
    call_args = mocked_pipeline["mock_popen"].call_args
    cmd = call_args[0][0]  # First positional arg is the command list
    assert "python" in cmd[0]
    assert "tv_trade_monitor.py" in cmd[-1]


# ===========================================================================
# Test 2: Monitor registered in RUNNING_STRATEGIES after successful spawn
# Validates: Requirements 4.3
# ===========================================================================


def test_monitor_registered_in_running_strategies(client, valid_payload, mocked_pipeline):
    """
    After a successful webhook call, verify the monitor appears in
    RUNNING_STRATEGIES dict with the expected keys.
    """
    response = client.post("/tv/webhook", json=valid_payload)
    assert response.status_code == 200

    running = mocked_pipeline["running_strategies"]

    # There should be exactly one strategy registered
    assert len(running) == 1, f"Expected 1 running strategy, got {len(running)}: {list(running.keys())}"

    # Get the registered strategy
    strategy_id = list(running.keys())[0]
    strategy_info = running[strategy_id]

    # Verify expected keys are present
    assert "process" in strategy_info, "Missing 'process' key in RUNNING_STRATEGIES entry"
    assert "pid" in strategy_info, "Missing 'pid' key in RUNNING_STRATEGIES entry"
    assert "log_file" in strategy_info, "Missing 'log_file' key in RUNNING_STRATEGIES entry"
    assert "log_handle" in strategy_info, "Missing 'log_handle' key in RUNNING_STRATEGIES entry"
    assert "started_at" in strategy_info, "Missing 'started_at' key in RUNNING_STRATEGIES entry"

    # Verify PID matches the mocked process
    assert strategy_info["pid"] == 12345

    # Verify strategy_id follows expected naming pattern
    assert strategy_id.startswith("tv_monitor_"), (
        f"Strategy ID should start with 'tv_monitor_', got '{strategy_id}'"
    )


# ===========================================================================
# Test 3: SIGTERM handler places SELL order when position is open
# Validates: Requirements 7.1, 7.3
# ===========================================================================


def test_sigterm_handler_calls_place_exit_order():
    """
    Verify SIGTERM handling logic exits position by calling place_exit_order.

    Tests place_exit_order directly (the function invoked by the SIGTERM handler)
    with a mock client and config, verifying a SELL order is placed.
    """
    sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "strategies", "scripts"))
    from tv_trade_monitor import place_exit_order, MonitorConfig

    config = MonitorConfig(
        option_symbol="NIFTY24JUN23500CE",
        option_exchange="NFO",
        entry_price=100.0,
        quantity=75,
        order_id="ORD123",
        sl_pct=15.0,
        trail_activate_pct=20.0,
        trail_step_pct=5.0,
        exit_time="15:15",
        poll_interval=5,
        product="MIS",
        api_key="test-key",
        host="http://127.0.0.1:5000",
    )

    mock_client = MagicMock()
    mock_client.placesmartorder.return_value = {"status": "success", "orderid": "EXIT1"}

    result = place_exit_order(mock_client, config, "SIGTERM shutdown", 95.0)

    # Verify exit order was placed successfully
    assert result is True, "place_exit_order should return True on successful exit"

    # Verify placesmartorder was called exactly once (no retry needed)
    mock_client.placesmartorder.assert_called_once()

    # Verify the call parameters
    call_kwargs = mock_client.placesmartorder.call_args[1]
    assert call_kwargs["action"] == "SELL", f"Expected action='SELL', got '{call_kwargs['action']}'"
    assert call_kwargs["quantity"] == 75, f"Expected quantity=75, got {call_kwargs['quantity']}"
    assert call_kwargs["symbol"] == "NIFTY24JUN23500CE"
    assert call_kwargs["exchange"] == "NFO"
    assert call_kwargs["price_type"] == "MARKET"
    assert call_kwargs["product"] == "MIS"
    assert call_kwargs["position_size"] == 0  # Full exit
