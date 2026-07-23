# test/test_tv_monitor_config.py
# Feature: tv-signal-trade-monitor, Property 8: Configuration Parsing with Defaults
# Tests for configuration parsing helpers in strategies/scripts/tv_trade_monitor.py
# Validates: Requirements 8.1, 8.2, 8.3

import os
import sys
from unittest.mock import patch

import pytest
from hypothesis import given, settings, assume
from hypothesis import strategies as st

# ---------------------------------------------------------------------------
# Import functions under test
# ---------------------------------------------------------------------------
sys.path.insert(0, "strategies/scripts")
from tv_trade_monitor import _parse_float, _parse_int, _parse_exit_time, MonitorConfig


# ---------------------------------------------------------------------------
# Helper: check if a string is numeric (parseable as float or int)
# ---------------------------------------------------------------------------
def _is_numeric(s: str) -> bool:
    """Return True if s can be parsed as a float."""
    try:
        float(s)
        return True
    except (ValueError, TypeError):
        return False


def _is_int(s: str) -> bool:
    """Return True if s can be parsed as an int."""
    try:
        int(s)
        return True
    except (ValueError, TypeError):
        return False


# ---------------------------------------------------------------------------
# Strategies
# ---------------------------------------------------------------------------
valid_floats = st.floats(min_value=-1e6, max_value=1e6, allow_nan=False, allow_infinity=False)
valid_ints = st.integers(min_value=-10000, max_value=10000)
invalid_strings = st.text(
    alphabet=st.characters(whitelist_categories=("L", "P")), min_size=1, max_size=10
).filter(lambda s: not _is_numeric(s))
invalid_int_strings = st.text(
    alphabet=st.characters(whitelist_categories=("L", "P")), min_size=1, max_size=10
).filter(lambda s: not _is_int(s))
valid_hours = st.integers(min_value=0, max_value=23)
valid_minutes = st.integers(min_value=0, max_value=59)


# ===========================================================================
# Property 8: Configuration Parsing with Defaults
# Feature: tv-signal-trade-monitor, Property 8: Configuration Parsing with Defaults
# ===========================================================================


# ---------------------------------------------------------------------------
# 1. Valid floats parse correctly
# ---------------------------------------------------------------------------
# Feature: tv-signal-trade-monitor, Property 8: Configuration Parsing with Defaults
@given(value=valid_floats)
@settings(max_examples=100, deadline=None)
def test_parse_float_valid(value):
    """**Validates: Requirements 8.1, 8.2, 8.3**

    For any valid float value, _parse_float returns that float when the
    environment variable is set to its string representation.
    """
    env_var = "TEST_FLOAT_VAR"
    with patch.dict(os.environ, {env_var: str(value)}):
        result = _parse_float(env_var, 99.9)
    assert result == pytest.approx(value, rel=1e-9, abs=1e-9), (
        f"Expected {value}, got {result}"
    )


# ---------------------------------------------------------------------------
# 2. Invalid floats return default
# ---------------------------------------------------------------------------
# Feature: tv-signal-trade-monitor, Property 8: Configuration Parsing with Defaults
@given(invalid_str=invalid_strings, default=valid_floats)
@settings(max_examples=100, deadline=None)
def test_parse_float_invalid_returns_default(invalid_str, default):
    """**Validates: Requirements 8.1, 8.2, 8.3**

    For any non-numeric string, _parse_float returns the default value.
    """
    env_var = "TEST_FLOAT_VAR"
    with patch.dict(os.environ, {env_var: invalid_str}):
        result = _parse_float(env_var, default)
    assert result == default, f"Expected default {default}, got {result}"


# ---------------------------------------------------------------------------
# 3. Valid ints parse correctly
# ---------------------------------------------------------------------------
# Feature: tv-signal-trade-monitor, Property 8: Configuration Parsing with Defaults
@given(value=valid_ints)
@settings(max_examples=100, deadline=None)
def test_parse_int_valid(value):
    """**Validates: Requirements 8.1, 8.2, 8.3**

    For any valid integer value, _parse_int returns that integer when the
    environment variable is set to its string representation.
    """
    env_var = "TEST_INT_VAR"
    with patch.dict(os.environ, {env_var: str(value)}):
        result = _parse_int(env_var, 999)
    assert result == value, f"Expected {value}, got {result}"


# ---------------------------------------------------------------------------
# 4. Invalid ints return default
# ---------------------------------------------------------------------------
# Feature: tv-signal-trade-monitor, Property 8: Configuration Parsing with Defaults
@given(invalid_str=invalid_int_strings, default=valid_ints)
@settings(max_examples=100, deadline=None)
def test_parse_int_invalid_returns_default(invalid_str, default):
    """**Validates: Requirements 8.1, 8.2, 8.3**

    For any non-integer string, _parse_int returns the default value.
    """
    env_var = "TEST_INT_VAR"
    with patch.dict(os.environ, {env_var: invalid_str}):
        result = _parse_int(env_var, default)
    assert result == default, f"Expected default {default}, got {result}"


# ---------------------------------------------------------------------------
# 5. Valid HH:MM times are accepted
# ---------------------------------------------------------------------------
# Feature: tv-signal-trade-monitor, Property 8: Configuration Parsing with Defaults
@given(hour=valid_hours, minute=valid_minutes)
@settings(max_examples=100, deadline=None)
def test_parse_exit_time_valid(hour, minute):
    """**Validates: Requirements 8.1, 8.2, 8.3**

    For any valid time (0-23 hours, 0-59 minutes) formatted as HH:MM with
    zero-padding, _parse_exit_time returns that time string.
    """
    time_str = f"{hour:02d}:{minute:02d}"
    env_var = "TEST_TIME_VAR"
    with patch.dict(os.environ, {env_var: time_str}):
        result = _parse_exit_time(env_var, "15:15")
    assert result == time_str, f"Expected {time_str}, got {result}"


# ---------------------------------------------------------------------------
# 6. Invalid times return default
# ---------------------------------------------------------------------------
# Feature: tv-signal-trade-monitor, Property 8: Configuration Parsing with Defaults
@given(
    invalid_time=st.one_of(
        # Random non-time strings
        st.text(min_size=1, max_size=10).filter(
            lambda s: not __import__("re").match(r"^([01]\d|2[0-3]):([0-5]\d)$", s.strip())
        ),
        # Out-of-range hours
        st.builds(lambda h, m: f"{h:02d}:{m:02d}", st.integers(min_value=24, max_value=99), st.integers(min_value=0, max_value=59)),
        # Out-of-range minutes
        st.builds(lambda h, m: f"{h:02d}:{m:02d}", st.integers(min_value=0, max_value=23), st.integers(min_value=60, max_value=99)),
    )
)
@settings(max_examples=100, deadline=None)
def test_parse_exit_time_invalid_returns_default(invalid_time):
    """**Validates: Requirements 8.1, 8.2, 8.3**

    For any string that does not match a valid HH:MM format (00-23:00-59),
    _parse_exit_time returns the default value "15:15".
    """
    env_var = "TEST_TIME_VAR"
    default = "15:15"
    with patch.dict(os.environ, {env_var: invalid_time}):
        result = _parse_exit_time(env_var, default)
    assert result == default, f"Expected default {default!r}, got {result!r} for input {invalid_time!r}"


# ---------------------------------------------------------------------------
# 7. MonitorConfig.from_env uses defaults for missing vars
# ---------------------------------------------------------------------------
# Feature: tv-signal-trade-monitor, Property 8: Configuration Parsing with Defaults
@given(
    sl_pct=st.one_of(st.none(), valid_floats),
    trail_activate=st.one_of(st.none(), valid_floats),
    trail_step=st.one_of(st.none(), valid_floats),
    poll_interval=st.one_of(st.none(), valid_ints),
    exit_time=st.one_of(
        st.none(),
        st.builds(lambda h, m: f"{h:02d}:{m:02d}", valid_hours, valid_minutes),
    ),
)
@settings(max_examples=100, deadline=None)
def test_monitor_config_from_env_defaults(sl_pct, trail_activate, trail_step, poll_interval, exit_time):
    """**Validates: Requirements 8.1, 8.2, 8.3**

    When env vars are missing, MonitorConfig.from_env() uses the documented
    default values. When present and valid, it uses the provided value.
    """
    env = {}
    # Set env vars only when the value is not None (simulating "present")
    if sl_pct is not None:
        env["TV_SL_PCT"] = str(sl_pct)
    if trail_activate is not None:
        env["TV_TRAIL_ACTIVATE_PCT"] = str(trail_activate)
    if trail_step is not None:
        env["TV_TRAIL_STEP_PCT"] = str(trail_step)
    if poll_interval is not None:
        env["TV_POLL_INTERVAL"] = str(poll_interval)
    if exit_time is not None:
        env["TV_EXIT_TIME"] = exit_time

    # Clear all TV_ env vars to isolate tests, then set only what we want
    clear_vars = {
        "TV_OPTION_SYMBOL": "",
        "TV_OPTION_EXCHANGE": "NFO",
        "TV_ENTRY_PRICE": "100.0",
        "TV_QUANTITY": "50",
        "TV_ORDER_ID": "ORD123",
        "TV_SL_PCT": "",
        "TV_TRAIL_ACTIVATE_PCT": "",
        "TV_TRAIL_STEP_PCT": "",
        "TV_EXIT_TIME": "",
        "TV_POLL_INTERVAL": "",
        "TV_PRODUCT": "MIS",
        "OPENALGO_APIKEY": "testkey",
        "OPENALGO_HOST": "http://127.0.0.1:5000",
    }
    # Remove keys we want to test as "missing"
    env_to_set = {k: v for k, v in clear_vars.items()}
    # Remove the env vars we're testing so from_env sees them as missing or set
    for key in ["TV_SL_PCT", "TV_TRAIL_ACTIVATE_PCT", "TV_TRAIL_STEP_PCT", "TV_POLL_INTERVAL", "TV_EXIT_TIME"]:
        if key in env_to_set:
            del env_to_set[key]

    env_to_set.update(env)

    with patch.dict(os.environ, env_to_set, clear=True):
        config = MonitorConfig.from_env()

    # Verify: if value was set, config should use it; if None, should use default
    if sl_pct is not None:
        assert config.sl_pct == pytest.approx(sl_pct, rel=1e-9, abs=1e-9)
    else:
        assert config.sl_pct == 15.0

    if trail_activate is not None:
        assert config.trail_activate_pct == pytest.approx(trail_activate, rel=1e-9, abs=1e-9)
    else:
        assert config.trail_activate_pct == 20.0

    if trail_step is not None:
        assert config.trail_step_pct == pytest.approx(trail_step, rel=1e-9, abs=1e-9)
    else:
        assert config.trail_step_pct == 5.0

    if poll_interval is not None:
        assert config.poll_interval == poll_interval
    else:
        assert config.poll_interval == 5

    if exit_time is not None:
        assert config.exit_time == exit_time
    else:
        assert config.exit_time == "15:15"
