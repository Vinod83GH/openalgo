# test/test_pnl_monitor.py
# Tests for services/pnl_monitor.py
# Covers Property 9 (P&L computation) and unit tests for market hours / status polling.

import math
import threading
from datetime import time
from unittest.mock import MagicMock, call, patch

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

# ---------------------------------------------------------------------------
# Helpers — import the class under test without triggering app-level imports
# ---------------------------------------------------------------------------

def _make_monitor():
    """Return a PnLMonitor instance without starting the thread."""
    from services.pnl_monitor import PnLMonitor
    return PnLMonitor()


# ===========================================================================
# Property 9: P&L computation from position book
# Feature: kill-switch, Property 9: P&L computation from position book
# Validates: Requirements 4.1
# ===========================================================================

# Feature: kill-switch, Property 9: P&L computation from position book
@given(
    positions=st.lists(
        st.fixed_dictionaries({"pnl": st.floats(min_value=-1e6, max_value=1e6, allow_nan=False)}),
        max_size=50,
    )
)
@settings(max_examples=100, deadline=None)
def test_pnl_computation(positions):
    """**Validates: Requirements 4.1**

    _compute_pnl should return the sum of all 'pnl' fields across all position records.
    """
    monitor = _make_monitor()
    result = monitor._compute_pnl(positions)
    expected = sum(float(p["pnl"]) for p in positions)
    # Use math.isclose to handle floating-point accumulation differences
    assert math.isclose(result, expected, rel_tol=1e-9, abs_tol=1e-9), (
        f"Expected {expected}, got {result}"
    )


def test_pnl_computation_empty():
    """_compute_pnl on an empty list should return 0.0."""
    monitor = _make_monitor()
    assert monitor._compute_pnl([]) == 0.0


def test_pnl_computation_missing_pnl_key():
    """_compute_pnl should treat missing 'pnl' key as 0."""
    monitor = _make_monitor()
    positions = [{"symbol": "NIFTY"}, {"pnl": 100.0}, {"pnl": -50.0}]
    assert math.isclose(monitor._compute_pnl(positions), 50.0)


# ===========================================================================
# Unit tests: _is_market_hours
# Validates: Requirements 4.4
# ===========================================================================

def _patch_ist_time(monitor, hour, minute):
    """Patch datetime.now inside pnl_monitor to return a fixed IST time."""
    import pytz
    from datetime import datetime as _dt

    tz = pytz.timezone("Asia/Kolkata")
    fake_now = _dt(2024, 1, 15, hour, minute, 0, tzinfo=tz)

    with patch("services.pnl_monitor.datetime") as mock_dt:
        mock_dt.now.return_value = fake_now
        return monitor._is_market_hours()


def test_is_market_hours_before_open():
    """Before 09:15 IST should return False."""
    monitor = _make_monitor()
    assert _patch_ist_time(monitor, 9, 14) is False


def test_is_market_hours_at_open():
    """At exactly 09:15 IST should return True."""
    monitor = _make_monitor()
    assert _patch_ist_time(monitor, 9, 15) is True


def test_is_market_hours_during_session():
    """During trading session (e.g. 12:00) should return True."""
    monitor = _make_monitor()
    assert _patch_ist_time(monitor, 12, 0) is True


def test_is_market_hours_just_before_close():
    """At 15:29 IST should return True."""
    monitor = _make_monitor()
    assert _patch_ist_time(monitor, 15, 29) is True


def test_is_market_hours_at_close():
    """At exactly 15:30 IST should return False (exclusive upper bound)."""
    monitor = _make_monitor()
    assert _patch_ist_time(monitor, 15, 30) is False


def test_is_market_hours_after_close():
    """After 15:30 IST should return False."""
    monitor = _make_monitor()
    assert _patch_ist_time(monitor, 16, 0) is False


# ===========================================================================
# Unit tests: _poll_all_active_brokers
# Validates: Requirements 4.3, 4.4
# ===========================================================================

def _make_config(broker_name: str, enabled: bool = True):
    """Create a minimal mock KillSwitchConfig object."""
    cfg = MagicMock()
    cfg.broker_name = broker_name
    cfg.enabled = enabled
    return cfg


def test_poll_calls_get_broker_kill_switch_status():
    """_poll_all_active_brokers should call get_broker_kill_switch_status for each enabled broker."""
    monitor = _make_monitor()
    configs = [_make_config("dhan"), _make_config("zerodha")]

    with (
        patch("database.kill_switch_db.KillSwitchConfig") as mock_ks_cls,
        patch("services.kill_switch_service.get_broker_kill_switch_status", return_value="DEACTIVATED") as mock_status,
        patch("services.positionbook_service.get_positionbook", return_value=(True, {"status": "success", "data": []}, 200)),
        patch("services.kill_switch_service.evaluate_pnl_thresholds"),
        patch.object(monitor, "_get_auth_token_for_broker", return_value="tok123"),
    ):
        mock_ks_cls.query.filter_by.return_value.all.return_value = configs
        monitor._poll_all_active_brokers()

    assert mock_status.call_count == 2
    mock_status.assert_any_call(broker_name="dhan", auth_token="tok123", broker="dhan")
    mock_status.assert_any_call(broker_name="zerodha", auth_token="tok123", broker="zerodha")


def test_poll_skips_broker_without_auth_token():
    """_poll_all_active_brokers should skip brokers with no auth token."""
    monitor = _make_monitor()
    configs = [_make_config("dhan")]

    with (
        patch("database.kill_switch_db.KillSwitchConfig") as mock_ks_cls,
        patch("services.kill_switch_service.get_broker_kill_switch_status") as mock_status,
        patch.object(monitor, "_get_auth_token_for_broker", return_value=None),
    ):
        mock_ks_cls.query.filter_by.return_value.all.return_value = configs
        monitor._poll_all_active_brokers()

    mock_status.assert_not_called()


def test_poll_skips_evaluate_when_activated():
    """evaluate_pnl_thresholds should NOT be called when broker status is ACTIVATED."""
    monitor = _make_monitor()
    configs = [_make_config("dhan")]

    with (
        patch("database.kill_switch_db.KillSwitchConfig") as mock_ks_cls,
        patch("services.kill_switch_service.get_broker_kill_switch_status", return_value="ACTIVATED"),
        patch("services.positionbook_service.get_positionbook") as mock_pos,
        patch("services.kill_switch_service.evaluate_pnl_thresholds") as mock_eval,
        patch.object(monitor, "_get_auth_token_for_broker", return_value="tok"),
    ):
        mock_ks_cls.query.filter_by.return_value.all.return_value = configs
        monitor._poll_all_active_brokers()

    mock_pos.assert_not_called()
    mock_eval.assert_not_called()


def test_poll_calls_evaluate_when_deactivated():
    """evaluate_pnl_thresholds SHOULD be called when broker status is DEACTIVATED."""
    monitor = _make_monitor()
    configs = [_make_config("dhan")]
    positions = [{"pnl": 500.0}, {"pnl": -100.0}]

    with (
        patch("database.kill_switch_db.KillSwitchConfig") as mock_ks_cls,
        patch("services.kill_switch_service.get_broker_kill_switch_status", return_value="DEACTIVATED"),
        patch("services.positionbook_service.get_positionbook", return_value=(True, {"status": "success", "data": positions}, 200)),
        patch("services.kill_switch_service.evaluate_pnl_thresholds") as mock_eval,
        patch.object(monitor, "_get_auth_token_for_broker", return_value="tok"),
    ):
        mock_ks_cls.query.filter_by.return_value.all.return_value = configs
        monitor._poll_all_active_brokers()

    mock_eval.assert_called_once_with(
        broker_name="dhan",
        current_pnl=400.0,
        auth_token="tok",
        broker="dhan",
    )


def test_poll_logs_warning_on_positionbook_error():
    """When positionbook API returns an error, log WARNING and skip evaluate."""
    monitor = _make_monitor()
    configs = [_make_config("dhan")]

    with (
        patch("database.kill_switch_db.KillSwitchConfig") as mock_ks_cls,
        patch("services.kill_switch_service.get_broker_kill_switch_status", return_value="DEACTIVATED"),
        patch("services.positionbook_service.get_positionbook", return_value=(False, {"status": "error", "message": "timeout"}, 500)),
        patch("services.kill_switch_service.evaluate_pnl_thresholds") as mock_eval,
        patch.object(monitor, "_get_auth_token_for_broker", return_value="tok"),
    ):
        mock_ks_cls.query.filter_by.return_value.all.return_value = configs
        # Should not raise
        monitor._poll_all_active_brokers()

    mock_eval.assert_not_called()


def test_poll_one_broker_failure_does_not_stop_others():
    """An exception for one broker should not prevent processing of subsequent brokers."""
    monitor = _make_monitor()
    configs = [_make_config("dhan"), _make_config("zerodha")]

    call_count = {"n": 0}

    def fake_status(broker_name, auth_token, broker):
        call_count["n"] += 1
        if broker_name == "dhan":
            raise RuntimeError("dhan API down")
        return "DEACTIVATED"

    with (
        patch("database.kill_switch_db.KillSwitchConfig") as mock_ks_cls,
        patch("services.kill_switch_service.get_broker_kill_switch_status", side_effect=fake_status),
        patch("services.positionbook_service.get_positionbook", return_value=(True, {"status": "success", "data": []}, 200)),
        patch("services.kill_switch_service.evaluate_pnl_thresholds"),
        patch.object(monitor, "_get_auth_token_for_broker", return_value="tok"),
    ):
        mock_ks_cls.query.filter_by.return_value.all.return_value = configs
        monitor._poll_all_active_brokers()

    # Both brokers were attempted
    assert call_count["n"] == 2


# ===========================================================================
# Structural / daemon checks
# ===========================================================================

def test_monitor_is_daemon_thread():
    """PnLMonitor must be a daemon thread so it doesn't block app shutdown."""
    from services.pnl_monitor import PnLMonitor
    monitor = PnLMonitor()
    assert monitor.daemon is True


def test_monitor_is_thread_subclass():
    """PnLMonitor must subclass threading.Thread."""
    from services.pnl_monitor import PnLMonitor
    assert issubclass(PnLMonitor, threading.Thread)


def test_poll_interval_within_60_seconds():
    """POLL_INTERVAL_SECONDS must be ≤ 60 (Requirement 3.1)."""
    from services.pnl_monitor import PnLMonitor
    assert PnLMonitor.POLL_INTERVAL_SECONDS <= 60


def test_market_open_close_constants():
    """MARKET_OPEN and MARKET_CLOSE must match spec values."""
    from services.pnl_monitor import PnLMonitor
    assert PnLMonitor.MARKET_OPEN == time(9, 15)
    assert PnLMonitor.MARKET_CLOSE == time(15, 30)
