#!/usr/bin/env python
"""
OpenAlgo Client Test Script
============================
Run this script to test the openalgo SDK methods against a live/analyzer instance.
Requires OPENALGO_APIKEY and OPENALGO_HOST env vars (auto-injected by the platform).

Usage:
  - Upload this as a Python Strategy and run it, OR
  - Run directly: python test_openalgo_client.py

Tests:
  1. client.quotes() — Get spot LTP for NIFTY
  2. client.quotes() — Get option LTP for a resolved symbol
  3. client.placesmartorder() — Place a BUY order (LIMIT)
  4. client.placesmartorder() — Place a SELL exit order (LIMIT)

Each test prints PASS/FAIL with details.
"""

import os
import sys
from datetime import datetime

from openalgo import api

# ============================================================
# CONFIGURATION
# ============================================================

API_KEY = os.getenv("OPENALGO_APIKEY")
if not API_KEY:
    print("❌ FAIL: OPENALGO_APIKEY environment variable not set")
    sys.exit(1)

HOST = os.getenv("OPENALGO_HOST", "http://127.0.0.1:5000")

# Test parameters — adjust these as needed
TEST_SYMBOL = os.getenv("STRATEGY_SYMBOL", "NIFTY")
TEST_EXCHANGE = os.getenv("STRATEGY_EXCHANGE", "NSE_INDEX")
TEST_OPTION_SYMBOL = os.getenv("TEST_OPTION_SYMBOL", "DRREDDY28JUL261300PE")  # Leave empty to skip option tests
TEST_OPTION_EXCHANGE = "NFO"
TEST_STRATEGY_NAME = "TestClient"
TEST_PRODUCT = os.getenv("STRATEGY_PRODUCT", "MIS")
TEST_QUANTITY = 1  # Minimal quantity for testing

# Initialize client
client = api(api_key=API_KEY, host=HOST)

results = []


def log(msg):
    print(f"[{datetime.now().strftime('%H:%M:%S')}] {msg}")


def run_test(name, test_func):
    """Run a test function and record result."""
    log(f"\n{'='*50}")
    log(f"TEST: {name}")
    log(f"{'='*50}")
    try:
        passed, details = test_func()
        status = "✅ PASS" if passed else "❌ FAIL"
        log(f"  {status}: {details}")
        results.append((name, passed, details))
    except Exception as e:
        log(f"  ❌ EXCEPTION: {e}")
        results.append((name, False, f"Exception: {e}"))


# ============================================================
# TEST 1: Get Spot Quotes
# ============================================================

def test_spot_quotes():
    """Test getting spot LTP for the configured symbol."""
    response = client.quotes(symbol=TEST_SYMBOL, exchange=TEST_EXCHANGE)
    log(f"  Response: {response}")

    if response is None:
        return False, "quotes() returned None"

    if isinstance(response, dict) and "ltp" in response:
        ltp = response["ltp"]
        return True, f"LTP for {TEST_SYMBOL} on {TEST_EXCHANGE} = {ltp}"

    # Handle wrapped response: {"data": {"ltp": ...}, "status": "success"}
    if isinstance(response, dict) and "data" in response and isinstance(response["data"], dict):
        if "ltp" in response["data"]:
            ltp = response["data"]["ltp"]
            return True, f"LTP for {TEST_SYMBOL} on {TEST_EXCHANGE} = {ltp}"

    if isinstance(response, dict) and response.get("status") == "error":
        return False, f"API error: {response.get('message', 'Unknown')}"

    return False, f"Unexpected response format: {type(response)} - {str(response)[:200]}"


# ============================================================
# TEST 2: Get Option Quotes
# ============================================================

def test_option_quotes():
    """Test getting LTP for an option symbol on NFO."""
    if not TEST_OPTION_SYMBOL:
        return True, "SKIPPED - TEST_OPTION_SYMBOL not set"

    response = client.quotes(symbol=TEST_OPTION_SYMBOL, exchange=TEST_OPTION_EXCHANGE)
    log(f"  Response: {response}")

    if response is None:
        return False, f"quotes() returned None for {TEST_OPTION_SYMBOL}"

    if isinstance(response, dict) and "ltp" in response:
        ltp = response["ltp"]
        return True, f"LTP for {TEST_OPTION_SYMBOL} on {TEST_OPTION_EXCHANGE} = {ltp}"

    # Handle wrapped response: {"data": {"ltp": ...}, "status": "success"}
    if isinstance(response, dict) and "data" in response and isinstance(response["data"], dict):
        if "ltp" in response["data"]:
            ltp = response["data"]["ltp"]
            return True, f"LTP for {TEST_OPTION_SYMBOL} on {TEST_OPTION_EXCHANGE} = {ltp}"

    if isinstance(response, dict) and response.get("status") == "error":
        return False, f"API error: {response.get('message', 'Unknown')}"

    return False, f"Unexpected response: {str(response)[:200]}"


# ============================================================
# TEST 3: Place BUY Order (Smart Order)
# ============================================================

def test_place_buy_order():
    """Test placing a BUY smart order. Uses minimal quantity."""
    # Use a known symbol for testing — NIFTY option or configured option
    test_sym = TEST_OPTION_SYMBOL if TEST_OPTION_SYMBOL else TEST_SYMBOL
    test_exch = TEST_OPTION_EXCHANGE if TEST_OPTION_SYMBOL else TEST_EXCHANGE

    order_params = {
        "strategy": TEST_STRATEGY_NAME,
        "symbol": test_sym,
        "action": "BUY",
        "exchange": test_exch,
        "price_type": "LIMIT",
        "product": TEST_PRODUCT,
        "quantity": TEST_QUANTITY,
        "position_size": TEST_QUANTITY,
        "price": 0.05,  # Very low price — won't fill but tests the flow
    }

    log(f"  Placing BUY order: {test_sym} on {test_exch} qty={TEST_QUANTITY}")
    response = client.placesmartorder(**order_params)
    log(f"  Response: {response}")

    if response is None:
        return False, "placesmartorder() returned None"

    if isinstance(response, dict):
        status = response.get("status")
        if status == "success":
            order_id = response.get("orderid", "unknown")
            return True, f"BUY order placed successfully. OrderID: {order_id}, Mode: {response.get('mode', 'unknown')}"
        else:
            return False, f"Order failed: {response.get('message', str(response))}"

    return False, f"Unexpected response: {str(response)[:200]}"


# ============================================================
# TEST 4: Place SELL Exit Order (Smart Order)
# ============================================================

def test_place_sell_order():
    """Test placing a SELL smart order (exit). Uses position_size=0."""
    test_sym = TEST_OPTION_SYMBOL if TEST_OPTION_SYMBOL else TEST_SYMBOL
    test_exch = TEST_OPTION_EXCHANGE if TEST_OPTION_SYMBOL else TEST_EXCHANGE

    order_params = {
        "strategy": TEST_STRATEGY_NAME,
        "symbol": test_sym,
        "action": "SELL",
        "exchange": test_exch,
        "price_type": "LIMIT",
        "product": TEST_PRODUCT,
        "quantity": TEST_QUANTITY,
        "position_size": 0,  # Exit position
        "price": 99999.0,  # Very high price — won't fill but tests the flow
    }

    log(f"  Placing SELL (exit) order: {test_sym} on {test_exch} qty={TEST_QUANTITY}")
    response = client.placesmartorder(**order_params)
    log(f"  Response: {response}")

    if response is None:
        return False, "placesmartorder() returned None"

    if isinstance(response, dict):
        status = response.get("status")
        if status == "success":
            order_id = response.get("orderid", "unknown")
            return True, f"SELL order placed successfully. OrderID: {order_id}, Mode: {response.get('mode', 'unknown')}"
        else:
            return False, f"Order failed: {response.get('message', str(response))}"

    return False, f"Unexpected response: {str(response)[:200]}"


# ============================================================
# MAIN
# ============================================================

def main():
    log(f"")
    log(f"{'='*60}")
    log(f"  OPENALGO CLIENT TEST SUITE")
    log(f"  Host: {HOST}")
    log(f"  Symbol: {TEST_SYMBOL} | Exchange: {TEST_EXCHANGE}")
    log(f"  Option: {TEST_OPTION_SYMBOL or '(not set)'}")
    log(f"  API Key: {API_KEY[:8]}...{API_KEY[-4:]}" if len(API_KEY) > 12 else f"  API Key: (short)")
    log(f"{'='*60}")

    # Run tests
    run_test("1. Spot Quotes (client.quotes)", test_spot_quotes)
    run_test("2. Option Quotes (client.quotes)", test_option_quotes)
    run_test("3. Place BUY Order (client.placesmartorder)", test_place_buy_order)
    run_test("4. Place SELL Exit Order (client.placesmartorder)", test_place_sell_order)

    # Summary
    log(f"\n{'='*60}")
    log(f"  TEST SUMMARY")
    log(f"{'='*60}")
    passed = sum(1 for _, p, _ in results if p)
    total = len(results)
    for name, p, details in results:
        status = "✅" if p else "❌"
        log(f"  {status} {name}: {details[:80]}")

    log(f"\n  Result: {passed}/{total} tests passed")
    log(f"{'='*60}")

    if passed < total:
        sys.exit(1)


if __name__ == "__main__":
    main()
