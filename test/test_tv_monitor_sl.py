# test/test_tv_monitor_sl.py
# Property-based tests for the Stop-Loss State Machine in tv_trade_monitor.py
# Feature: tv-signal-trade-monitor, Property 7: Stop-Loss State Machine

import math
import sys

import pytest
from hypothesis import given, settings, assume
from hypothesis import strategies as st

# Import the function under test
sys.path.insert(0, "strategies/scripts")
from tv_trade_monitor import compute_sl_floor


# ---------------------------------------------------------------------------
# Strategies for random values
# ---------------------------------------------------------------------------
entry_price_st = st.floats(min_value=10.0, max_value=10000.0, allow_nan=False, allow_infinity=False)
sl_pct_st = st.floats(min_value=1.0, max_value=50.0, allow_nan=False, allow_infinity=False)
trail_activate_pct_st = st.floats(min_value=5.0, max_value=100.0, allow_nan=False, allow_infinity=False)
trail_step_pct_st = st.floats(min_value=1.0, max_value=50.0, allow_nan=False, allow_infinity=False)


# ===========================================================================
# Property 7: Stop-Loss State Machine
# Feature: tv-signal-trade-monitor, Property 7: Stop-Loss State Machine
# Validates: Requirements 5.1, 5.2, 5.3
# ===========================================================================


# Feature: tv-signal-trade-monitor, Property 7: Stop-Loss State Machine
@given(
    entry_price=entry_price_st,
    sl_pct=sl_pct_st,
    trail_activate_pct=trail_activate_pct_st,
    trail_step_pct=trail_step_pct_st,
    multiplier=st.floats(min_value=0.5, max_value=0.99, allow_nan=False, allow_infinity=False),
)
@settings(max_examples=100, deadline=None)
def test_sl_floor_below_trail_activation(entry_price, sl_pct, trail_activate_pct, trail_step_pct, multiplier):
    """**Validates: Requirements 5.1**

    When profit_pct < trail_activate_pct, SL floor = entry_price * (1 - sl_pct/100).
    """
    # Derive current_premium so profit_pct is below trail_activate_pct
    # profit_pct = ((current_premium - entry_price) / entry_price) * 100
    # We want profit_pct < trail_activate_pct, so:
    # current_premium < entry_price * (1 + trail_activate_pct / 100)
    max_premium = entry_price * (1 + trail_activate_pct / 100)
    # Use multiplier to stay below the threshold (multiplier < 1.0 so we're within range)
    current_premium = entry_price + (max_premium - entry_price) * multiplier * 0.99

    # Verify profit is actually below threshold
    profit_pct = ((current_premium - entry_price) / entry_price) * 100
    assume(profit_pct < trail_activate_pct)

    result = compute_sl_floor(entry_price, current_premium, sl_pct, trail_activate_pct, trail_step_pct)
    expected = entry_price * (1 - sl_pct / 100)

    assert math.isclose(result, expected, rel_tol=1e-9, abs_tol=1e-9), (
        f"Below trail: expected SL floor {expected}, got {result} "
        f"(entry={entry_price}, premium={current_premium}, profit_pct={profit_pct:.2f}%)"
    )


# Feature: tv-signal-trade-monitor, Property 7: Stop-Loss State Machine
@given(
    entry_price=entry_price_st,
    sl_pct=sl_pct_st,
    trail_activate_pct=trail_activate_pct_st,
    trail_step_pct=trail_step_pct_st,
    extra_pct=st.floats(min_value=0.0, max_value=200.0, allow_nan=False, allow_infinity=False),
)
@settings(max_examples=100, deadline=None)
def test_sl_floor_above_trail_activation(entry_price, sl_pct, trail_activate_pct, trail_step_pct, extra_pct):
    """**Validates: Requirements 5.2, 5.3**

    When profit_pct >= trail_activate_pct, SL floor = entry_price * (1 + steps * trail_step_pct/100)
    where steps = floor((profit_pct - trail_activate_pct) / trail_step_pct).
    """
    # Derive current_premium so profit_pct >= trail_activate_pct
    # profit_pct = trail_activate_pct + extra_pct
    target_profit_pct = trail_activate_pct + extra_pct
    current_premium = entry_price * (1 + target_profit_pct / 100)

    # Verify profit is at or above threshold
    profit_pct = ((current_premium - entry_price) / entry_price) * 100
    assume(profit_pct >= trail_activate_pct)

    result = compute_sl_floor(entry_price, current_premium, sl_pct, trail_activate_pct, trail_step_pct)

    steps_above = math.floor((profit_pct - trail_activate_pct) / trail_step_pct)
    expected = entry_price * (1 + steps_above * trail_step_pct / 100)

    assert math.isclose(result, expected, rel_tol=1e-9, abs_tol=1e-9), (
        f"Above trail: expected SL floor {expected}, got {result} "
        f"(entry={entry_price}, profit_pct={profit_pct:.2f}%, steps={steps_above})"
    )


# Feature: tv-signal-trade-monitor, Property 7: Stop-Loss State Machine
@given(
    entry_price=entry_price_st,
    sl_pct=st.floats(min_value=1.0, max_value=99.0, allow_nan=False, allow_infinity=False),
    trail_activate_pct=trail_activate_pct_st,
    trail_step_pct=trail_step_pct_st,
    premium_multiplier=st.floats(min_value=0.5, max_value=5.0, allow_nan=False, allow_infinity=False),
)
@settings(max_examples=100, deadline=None)
def test_sl_floor_always_positive(entry_price, sl_pct, trail_activate_pct, trail_step_pct, premium_multiplier):
    """**Validates: Requirements 5.1, 5.2, 5.3**

    SL floor is always positive when entry_price > 0 and sl_pct < 100.
    """
    current_premium = entry_price * premium_multiplier

    result = compute_sl_floor(entry_price, current_premium, sl_pct, trail_activate_pct, trail_step_pct)

    assert result > 0, (
        f"SL floor should be positive, got {result} "
        f"(entry={entry_price}, sl_pct={sl_pct}, premium={current_premium})"
    )


# Feature: tv-signal-trade-monitor, Property 7: Stop-Loss State Machine
@given(
    entry_price=entry_price_st,
    sl_pct=sl_pct_st,
    trail_activate_pct=trail_activate_pct_st,
    trail_step_pct=trail_step_pct_st,
)
@settings(max_examples=100, deadline=None)
def test_sl_floor_monotonic_after_trail_activation(entry_price, sl_pct, trail_activate_pct, trail_step_pct):
    """**Validates: Requirements 5.2, 5.3**

    SL floor is monotonically non-decreasing as profit increases once trail is activated.
    """
    # Generate a sequence of increasing premiums above trail activation
    base_premium = entry_price * (1 + trail_activate_pct / 100)

    prev_sl = None
    # Check SL floor at increasing profit levels
    for step_mult in range(0, 10):
        current_premium = base_premium + entry_price * (step_mult * trail_step_pct / 100)
        sl_floor = compute_sl_floor(entry_price, current_premium, sl_pct, trail_activate_pct, trail_step_pct)

        if prev_sl is not None:
            assert sl_floor >= prev_sl - 1e-9, (
                f"SL floor should be non-decreasing after trail activation. "
                f"Prev SL: {prev_sl}, Current SL: {sl_floor} "
                f"(step_mult={step_mult}, premium={current_premium})"
            )
        prev_sl = sl_floor
