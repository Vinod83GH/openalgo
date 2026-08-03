# test/test_tv_monitor_unit.py
# Unit tests for TV Trade Monitor (strategies/scripts/tv_trade_monitor.py)
# Validates: Requirements 6.1, 6.2, 7.1, 7.2, 8.1, 8.3

import os
import sys
from unittest.mock import MagicMock, patch

import pytest

# ---------------------------------------------------------------------------
# Import functions under test
# ---------------------------------------------------------------------------
sys.path.insert(0, "strategies/scripts")
from tv_trade_monitor import (
    MonitorConfig,
    compute_sl_floor,
    place_exit_order,
    log,
    _parse_float,
    _parse_int,
)


# ---------------------------------------------------------------------------
# Helper: create a MonitorConfig with sensible defaults
# ---------------------------------------------------------------------------
def _make_config(**overrides):
    defaults = {
        "option_symbol": "NIFTY24JUN23500CE",
        "option_exchange": "NFO",
        "entry_price": 100.0,
        "quantity": 75,
        "order_id": "ORD123",
        "sl_pct": 15.0,
        "trail_activate_pct": 20.0,
        "trail_step_pct": 5.0,
        "exit_time": "15:15",
        "poll_interval": 5,
        "product": "MIS",
        "api_key": "test_key",
        "host": "http://127.0.0.1:5000",
    }
    defaults.update(overrides)
    return MonitorConfig(**defaults)


# ===========================================================================
# Test: place_exit_order returns True on success
# Validates: Requirements 6.1, 6.2
# ===========================================================================
class TestPlaceExitOrder:
    """Tests for the place_exit_order function with retry logic."""

    def test_place_exit_order_success(self, capsys):
        """Mock openalgo client returns success on first call.
        Verify place_exit_order returns True and logs the success message.
        """
        client = MagicMock()
        client.placesmartorder.return_value = {
            "status": "success",
            "orderid": "EXIT_ORD_001",
        }
        config = _make_config()

        result = place_exit_order(client, config, "Stop-loss hit", current_premium=85.0)

        assert result is True
        # Verify client was called exactly once (no retry needed)
        assert client.placesmartorder.call_count == 1
        # Verify success log message
        captured = capsys.readouterr()
        assert "Exit order placed successfully" in captured.out
        assert "EXIT_ORD_001" in captured.out

    def test_place_exit_order_retry_on_failure(self, capsys):
        """Mock first call to fail, second to succeed.
        Verify returns True after retry.
        """
        client = MagicMock()
        client.placesmartorder.side_effect = [
            {"status": "error", "message": "Broker timeout"},
            {"status": "success", "orderid": "EXIT_ORD_002"},
        ]
        config = _make_config()

        with patch("tv_trade_monitor.time.sleep"):  # skip actual sleep
            result = place_exit_order(client, config, "Time exit", current_premium=110.0)

        assert result is True
        assert client.placesmartorder.call_count == 2
        captured = capsys.readouterr()
        assert "Exit order placed successfully" in captured.out
        assert "EXIT_ORD_002" in captured.out

    def test_place_exit_order_exhausts_retries(self, capsys):
        """Mock both calls to fail.
        Verify returns False and logs critical message.
        """
        client = MagicMock()
        client.placesmartorder.return_value = {
            "status": "error",
            "message": "Broker rejected",
        }
        config = _make_config()

        with patch("tv_trade_monitor.time.sleep"):  # skip actual sleep
            result = place_exit_order(client, config, "SL hit", current_premium=80.0)

        assert result is False
        assert client.placesmartorder.call_count == 2
        captured = capsys.readouterr()
        assert "CRITICAL" in captured.out
        assert "failed after 2 attempts" in captured.out


# ===========================================================================
# Test: Product type from env var vs default
# Validates: Requirements 8.1
# ===========================================================================
class TestProductTypeConfig:
    """Tests for TV_PRODUCT environment variable handling."""

    def test_product_type_from_env(self):
        """Set TV_PRODUCT='NRML' via env, verify MonitorConfig.from_env().product == 'NRML'."""
        env = {
            "TV_OPTION_SYMBOL": "NIFTY24JUN23500CE",
            "TV_OPTION_EXCHANGE": "NFO",
            "TV_ENTRY_PRICE": "100.0",
            "TV_QUANTITY": "75",
            "TV_ORDER_ID": "ORD123",
            "TV_PRODUCT": "NRML",
            "OPENALGO_APIKEY": "test_key",
            "OPENALGO_HOST": "http://127.0.0.1:5000",
        }
        with patch.dict(os.environ, env, clear=True):
            config = MonitorConfig.from_env()
        assert config.product == "NRML"

    def test_product_type_default(self):
        """Don't set TV_PRODUCT, verify MonitorConfig.from_env().product == 'MIS'."""
        env = {
            "TV_OPTION_SYMBOL": "NIFTY24JUN23500CE",
            "TV_OPTION_EXCHANGE": "NFO",
            "TV_ENTRY_PRICE": "100.0",
            "TV_QUANTITY": "75",
            "TV_ORDER_ID": "ORD123",
            "OPENALGO_APIKEY": "test_key",
            "OPENALGO_HOST": "http://127.0.0.1:5000",
        }
        with patch.dict(os.environ, env, clear=True):
            config = MonitorConfig.from_env()
        assert config.product == "MIS"


# ===========================================================================
# Test: Invalid env var handling (warning + default)
# Validates: Requirements 8.1, 8.3
# ===========================================================================
class TestInvalidEnvVarHandling:
    """Tests for invalid environment variable values falling back to defaults."""

    def test_invalid_sl_pct_uses_default(self, capsys):
        """Set TV_SL_PCT='abc', verify config.sl_pct == 15.0 and warning logged."""
        env = {
            "TV_OPTION_SYMBOL": "NIFTY24JUN23500CE",
            "TV_OPTION_EXCHANGE": "NFO",
            "TV_ENTRY_PRICE": "100.0",
            "TV_QUANTITY": "75",
            "TV_ORDER_ID": "ORD123",
            "TV_SL_PCT": "abc",
            "OPENALGO_APIKEY": "test_key",
            "OPENALGO_HOST": "http://127.0.0.1:5000",
        }
        with patch.dict(os.environ, env, clear=True):
            config = MonitorConfig.from_env()

        assert config.sl_pct == 15.0
        captured = capsys.readouterr()
        assert "WARNING" in captured.out
        assert "TV_SL_PCT" in captured.out

    def test_invalid_poll_interval_uses_default(self, capsys):
        """Set TV_POLL_INTERVAL='xyz', verify config.poll_interval == 5 and warning logged."""
        env = {
            "TV_OPTION_SYMBOL": "NIFTY24JUN23500CE",
            "TV_OPTION_EXCHANGE": "NFO",
            "TV_ENTRY_PRICE": "100.0",
            "TV_QUANTITY": "75",
            "TV_ORDER_ID": "ORD123",
            "TV_POLL_INTERVAL": "xyz",
            "OPENALGO_APIKEY": "test_key",
            "OPENALGO_HOST": "http://127.0.0.1:5000",
        }
        with patch.dict(os.environ, env, clear=True):
            config = MonitorConfig.from_env()

        assert config.poll_interval == 5
        captured = capsys.readouterr()
        assert "WARNING" in captured.out
        assert "TV_POLL_INTERVAL" in captured.out


# ===========================================================================
# Test: compute_sl_floor logic
# Validates: Requirements 5.1, 5.2, 5.3
# ===========================================================================
class TestComputeSlFloor:
    """Tests for the SL floor computation function."""

    def test_compute_sl_floor_basic_sl(self):
        """Entry 100, premium 90 (profit -10%), SL floor = 100 * (1 - 15/100) = 85."""
        entry_price = 100.0
        current_premium = 90.0
        sl_pct = 15.0
        trail_activate_pct = 20.0
        trail_step_pct = 5.0

        result = compute_sl_floor(entry_price, current_premium, sl_pct, trail_activate_pct, trail_step_pct)

        assert result == pytest.approx(85.0)

    def test_compute_sl_floor_trail_activated(self):
        """Entry 100, premium 125 (profit 25%), trail_activate=20, step=5.
        steps = floor((25-20)/5) = 1
        SL = 100 * (1 + 1*5/100) = 105.
        """
        entry_price = 100.0
        current_premium = 125.0
        sl_pct = 15.0
        trail_activate_pct = 20.0
        trail_step_pct = 5.0

        result = compute_sl_floor(entry_price, current_premium, sl_pct, trail_activate_pct, trail_step_pct)

        assert result == pytest.approx(105.0)

    def test_compute_sl_floor_at_trail_boundary(self):
        """Entry 100, premium 120 (profit exactly 20%), trail activates.
        steps = floor((20-20)/5) = 0
        SL = 100 * (1 + 0*5/100) = 100.0 (breakeven).
        """
        entry_price = 100.0
        current_premium = 120.0
        sl_pct = 15.0
        trail_activate_pct = 20.0
        trail_step_pct = 5.0

        result = compute_sl_floor(entry_price, current_premium, sl_pct, trail_activate_pct, trail_step_pct)

        assert result == pytest.approx(100.0)

    def test_compute_sl_floor_multiple_trail_steps(self):
        """Entry 100, premium 140 (profit 40%), trail_activate=20, step=5.
        steps = floor((40-20)/5) = 4
        SL = 100 * (1 + 4*5/100) = 120.
        """
        entry_price = 100.0
        current_premium = 140.0
        sl_pct = 15.0
        trail_activate_pct = 20.0
        trail_step_pct = 5.0

        result = compute_sl_floor(entry_price, current_premium, sl_pct, trail_activate_pct, trail_step_pct)

        assert result == pytest.approx(120.0)
