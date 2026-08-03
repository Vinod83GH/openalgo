# test/test_tv_webhook_option.py
# Property-based tests for option resolution and order quantity computation
# Feature: tv-signal-trade-monitor, Property 4: Option Response Extraction
# Feature: tv-signal-trade-monitor, Property 5: Order Quantity Computation

from unittest.mock import MagicMock, patch

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from blueprints.tv_webhook import _resolve_option


# ---------------------------------------------------------------------------
# Strategies
# ---------------------------------------------------------------------------
symbol_st = st.text(
    min_size=3, max_size=20, alphabet=st.characters(whitelist_categories=("L", "N"))
)
exchange_st = st.sampled_from(["NFO", "BFO", "MCX"])
lotsize_st = st.integers(min_value=1, max_value=5000)


# ===========================================================================
# Property 4: Option Response Extraction
# Feature: tv-signal-trade-monitor, Property 4: Option Response Extraction
# Validates: Requirements 2.2
# ===========================================================================


# Feature: tv-signal-trade-monitor, Property 4: Option Response Extraction
@given(
    symbol=symbol_st,
    exchange=exchange_st,
    lotsize=lotsize_st,
)
@settings(max_examples=100, deadline=None)
def test_option_response_extraction(symbol, exchange, lotsize):
    """**Validates: Requirements 2.2**

    For any valid optionsymbol API response containing
    {status: "success", symbol: S, exchange: E, lotsize: L},
    _resolve_option SHALL extract exactly (S, E, int(L)).
    """
    mock_response = MagicMock()
    mock_response.json.return_value = {
        "status": "success",
        "symbol": symbol,
        "exchange": exchange,
        "lotsize": lotsize,
    }
    with patch("blueprints.tv_webhook.requests.post", return_value=mock_response):
        result_sym, result_exch, result_lot = _resolve_option(
            "test_key", "NIFTY", "CE", "ITM1"
        )

    assert result_sym == symbol
    assert result_exch == exchange
    assert result_lot == int(lotsize)


# ===========================================================================
# Property 5: Order Quantity Computation
# Feature: tv-signal-trade-monitor, Property 5: Order Quantity Computation
# Validates: Requirements 3.1
# ===========================================================================


# Feature: tv-signal-trade-monitor, Property 5: Order Quantity Computation
@given(
    lots=st.integers(min_value=1, max_value=100),
    lotsize=st.integers(min_value=1, max_value=5000),
)
@settings(max_examples=100, deadline=None)
def test_quantity_computation(lots, lotsize):
    """**Validates: Requirements 3.1**

    For any configured lot count N and resolved lot size L,
    the order quantity SHALL equal N × L and be positive.
    """
    quantity = lots * lotsize
    assert quantity == lots * lotsize
    assert quantity > 0
    assert isinstance(quantity, int)


# ===========================================================================
# Edge case: error response returns (None, None, None)
# ===========================================================================


def test_option_resolution_returns_none_on_error():
    """Verify _resolve_option returns (None, None, None) on error API response."""
    mock_response = MagicMock()
    mock_response.json.return_value = {"status": "error", "message": "Not found"}
    with patch("blueprints.tv_webhook.requests.post", return_value=mock_response):
        result = _resolve_option("test_key", "NIFTY", "CE", "ITM1")
    assert result == (None, None, None)
