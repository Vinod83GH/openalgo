#!/usr/bin/env python
"""
TradingView Signal Trade Monitor
=================================
Post-entry trade monitor subprocess spawned by the TV webhook blueprint.
Manages multi-step stop-loss, profit trailing, forced time exit, and
graceful shutdown on SIGTERM.

Reads ALL configuration from environment variables (injected by parent process).

Configuration (environment variables):
  TV_OPTION_SYMBOL         - Resolved option contract symbol
  TV_OPTION_EXCHANGE       - Option exchange (e.g., "NFO")
  TV_ENTRY_PRICE           - Premium at entry
  TV_QUANTITY              - Total quantity (lots × lotsize)
  TV_ORDER_ID              - Entry order ID
  TV_SL_PCT               - Initial stop-loss % (default: 15)
  TV_TRAIL_ACTIVATE_PCT   - Trail activation % (default: 20)
  TV_TRAIL_STEP_PCT       - Trail step % (default: 5)
  TV_EXIT_TIME            - Forced exit time HH:MM (default: "15:15")
  TV_POLL_INTERVAL        - Polling interval in seconds (default: 5)
  TV_PRODUCT              - Product type (default: "MIS")
  OPENALGO_APIKEY         - API key (auto-injected)
  OPENALGO_HOST           - Host URL (default: "http://127.0.0.1:5000")
"""

import math
import os
import re
import signal
import sys
import time
from dataclasses import dataclass
from datetime import datetime, timezone, timedelta

# IST timezone offset (+5:30)
IST = timezone(timedelta(hours=5, minutes=30))


def log(message: str) -> None:
    """Print a timestamped log line to stdout (captured by parent process to log file)."""
    timestamp = datetime.now(IST).isoformat(timespec="seconds")
    print(f"{timestamp} {message}", flush=True)


def _parse_float(env_var: str, default: float) -> float:
    """Parse a float from environment variable. Log warning and return default on invalid."""
    raw = os.getenv(env_var)
    if raw is None:
        return default
    try:
        return float(raw)
    except (ValueError, TypeError):
        log(f"WARNING: {env_var}={raw!r} is not a valid number, using default {default}")
        return default


def _parse_int(env_var: str, default: int) -> int:
    """Parse an int from environment variable. Log warning and return default on invalid."""
    raw = os.getenv(env_var)
    if raw is None:
        return default
    try:
        return int(raw)
    except (ValueError, TypeError):
        log(f"WARNING: {env_var}={raw!r} is not a valid integer, using default {default}")
        return default


def _parse_exit_time(env_var: str, default: str) -> str:
    """Parse HH:MM time format from environment variable. Log warning and return default on invalid."""
    raw = os.getenv(env_var)
    if raw is None:
        return default
    # Validate HH:MM format (00-23 hours, 00-59 minutes)
    pattern = r"^([01]\d|2[0-3]):([0-5]\d)$"
    if re.match(pattern, raw.strip()):
        return raw.strip()
    log(f"WARNING: {env_var}={raw!r} is not a valid HH:MM time format, using default {default!r}")
    return default


@dataclass
class MonitorConfig:
    """Trade monitor configuration parsed from environment variables."""

    # Entry details (passed from webhook)
    option_symbol: str       # TV_OPTION_SYMBOL - resolved option contract
    option_exchange: str     # TV_OPTION_EXCHANGE - e.g., "NFO"
    entry_price: float       # TV_ENTRY_PRICE - premium at entry
    quantity: int            # TV_QUANTITY - total quantity (lots × lotsize)
    order_id: str            # TV_ORDER_ID - entry order ID

    # Trade management thresholds
    sl_pct: float            # TV_SL_PCT - initial SL % (default: 15)
    trail_activate_pct: float  # TV_TRAIL_ACTIVATE_PCT - trail activation % (default: 20)
    trail_step_pct: float    # TV_TRAIL_STEP_PCT - trail step % (default: 5)
    exit_time: str           # TV_EXIT_TIME - forced exit time (default: "15:15")
    poll_interval: int       # TV_POLL_INTERVAL - polling seconds (default: 5)
    product: str             # TV_PRODUCT - product type (default: "MIS")

    # API access
    api_key: str             # OPENALGO_APIKEY - auto-injected
    host: str                # OPENALGO_HOST - default "http://127.0.0.1:5000"

    @classmethod
    def from_env(cls) -> "MonitorConfig":
        """Parse all configuration from environment variables with validation and defaults."""
        # Required entry details (no defaults — must be provided by parent process)
        option_symbol = os.getenv("TV_OPTION_SYMBOL", "")
        option_exchange = os.getenv("TV_OPTION_EXCHANGE", "NFO")
        entry_price = _parse_float("TV_ENTRY_PRICE", 0.0)
        quantity = _parse_int("TV_QUANTITY", 0)
        order_id = os.getenv("TV_ORDER_ID", "")

        # Trade management thresholds with defaults
        sl_pct = _parse_float("TV_SL_PCT", 15.0)
        trail_activate_pct = _parse_float("TV_TRAIL_ACTIVATE_PCT", 20.0)
        trail_step_pct = _parse_float("TV_TRAIL_STEP_PCT", 5.0)
        exit_time = _parse_exit_time("TV_EXIT_TIME", "15:15")
        poll_interval = _parse_int("TV_POLL_INTERVAL", 5)
        product = os.getenv("TV_PRODUCT", "MIS")

        # API access
        api_key = os.getenv("OPENALGO_APIKEY", "")
        host = os.getenv("OPENALGO_HOST", "http://127.0.0.1:5000")

        return cls(
            option_symbol=option_symbol,
            option_exchange=option_exchange,
            entry_price=entry_price,
            quantity=quantity,
            order_id=order_id,
            sl_pct=sl_pct,
            trail_activate_pct=trail_activate_pct,
            trail_step_pct=trail_step_pct,
            exit_time=exit_time,
            poll_interval=poll_interval,
            product=product,
            api_key=api_key,
            host=host,
        )

    def log_config(self) -> None:
        """Log full configuration at startup for audit purposes."""
        log("=" * 60)
        log("TV Trade Monitor — Configuration")
        log("=" * 60)
        log(f"  Option Symbol   : {self.option_symbol}")
        log(f"  Option Exchange : {self.option_exchange}")
        log(f"  Entry Price     : {self.entry_price}")
        log(f"  Quantity        : {self.quantity}")
        log(f"  Order ID        : {self.order_id}")
        log(f"  SL %            : {self.sl_pct}")
        log(f"  Trail Activate %: {self.trail_activate_pct}")
        log(f"  Trail Step %    : {self.trail_step_pct}")
        log(f"  Exit Time       : {self.exit_time}")
        log(f"  Poll Interval   : {self.poll_interval}s")
        log(f"  Product         : {self.product}")
        log(f"  API Key         : {'*' * 4}{self.api_key[-4:] if len(self.api_key) >= 4 else '****'}")
        log(f"  Host            : {self.host}")
        log("=" * 60)


def get_current_premium(client, symbol: str, exchange: str):
    """Fetch current option LTP. Returns float or None on failure."""
    try:
        quotes = client.quotes(symbol=symbol, exchange=exchange)
        if quotes and isinstance(quotes, dict):
            if "ltp" in quotes:
                return float(quotes["ltp"])
            elif "data" in quotes and isinstance(quotes["data"], dict) and "ltp" in quotes["data"]:
                return float(quotes["data"]["ltp"])
    except Exception as e:
        log(f"WARNING: Quote fetch error: {e}")
    return None


def compute_sl_floor(entry_price: float, current_premium: float, sl_pct: float,
                     trail_activate_pct: float, trail_step_pct: float) -> float:
    """
    Compute the current stop-loss floor based on profit level.

    - Below trail activation: SL floor = entry_price * (1 - sl_pct/100)
    - At/above trail activation: SL floor = entry_price * (1 + steps * trail_step_pct/100)
      where steps = floor((profit_pct - trail_activate_pct) / trail_step_pct)
    """
    profit_pct = ((current_premium - entry_price) / entry_price) * 100

    if profit_pct < trail_activate_pct:
        return entry_price * (1 - sl_pct / 100)
    else:
        steps_above = math.floor((profit_pct - trail_activate_pct) / trail_step_pct)
        return entry_price * (1 + steps_above * trail_step_pct / 100)


def place_exit_order(client, config: MonitorConfig, reason: str, current_premium: float = None) -> bool:
    """Place MARKET SELL exit order with one retry. Returns True on success."""
    profit_pct = 0.0
    if current_premium and config.entry_price > 0:
        profit_pct = ((current_premium - config.entry_price) / config.entry_price) * 100

    log(f"{'='*40}")
    log(f"EXIT ORDER — Reason: {reason}")
    log(f"  Symbol: {config.option_symbol} | Qty: {config.quantity}")
    log(f"  Entry: {config.entry_price:.2f} | Current: {f'{current_premium:.2f}' if current_premium else 'N/A'}")
    log(f"  P&L: {profit_pct:.2f}%")
    log(f"{'='*40}")

    for attempt in range(2):  # Max 2 attempts (initial + 1 retry)
        try:
            response = client.placesmartorder(
                strategy="TV-Signal-Monitor",
                symbol=config.option_symbol,
                action="SELL",
                exchange=config.option_exchange,
                price_type="MARKET",
                product=config.product,
                quantity=config.quantity,
                position_size=0,
            )

            if isinstance(response, dict) and response.get("status") == "success":
                order_id = response.get("orderid", "")
                log(f"✅ Exit order placed successfully. OrderID: {order_id}")
                return True
            else:
                error_msg = response.get("message", "Unknown") if isinstance(response, dict) else str(response)
                log(f"❌ Exit order failed (attempt {attempt + 1}/2): {error_msg}")
        except Exception as e:
            log(f"❌ Exit order error (attempt {attempt + 1}/2): {e}")

        if attempt == 0:
            log("  Retrying in 2 seconds...")
            time.sleep(2)

    log("❌ CRITICAL: Exit order failed after 2 attempts. Position may need manual intervention!")
    return False


def main():
    """Trade monitor entry point. Parses config and starts monitoring loop."""
    config = MonitorConfig.from_env()
    config.log_config()

    # Initialize API client
    from openalgo import api
    client = api(api_key=config.api_key, host=config.host)

    # Track position state (used by SIGTERM handler via nonlocal)
    position_open = True

    # SIGTERM handler for graceful shutdown
    def sigterm_handler(signum, frame):
        nonlocal position_open
        log("")
        log("⚠️ SIGTERM received — graceful shutdown initiated")
        if position_open:
            log("  📤 Exiting open position before shutdown...")
            current_ltp = get_current_premium(client, config.option_symbol, config.option_exchange)
            place_exit_order(client, config, "SIGTERM shutdown", current_ltp)
        else:
            log("  No open position to exit.")
        log("  👋 TV Trade Monitor terminated gracefully.")
        sys.exit(0)

    signal.signal(signal.SIGTERM, sigterm_handler)

    # Parse exit time
    exit_parts = config.exit_time.split(":")
    exit_hour, exit_minute = int(exit_parts[0]), int(exit_parts[1])

    log(f"Entry confirmed: {config.option_symbol} @ {config.entry_price} | Qty: {config.quantity}")
    log(f"Monitoring started. Poll interval: {config.poll_interval}s | Exit time: {config.exit_time} IST")

    last_sl_floor = None
    trail_activated = False

    while position_open:
        # Check time-based exit
        now_ist = datetime.now(IST)
        if now_ist.hour > exit_hour or (now_ist.hour == exit_hour and now_ist.minute >= exit_minute):
            log(f"⏰ EXIT TIME REACHED ({config.exit_time} IST) — forcing exit")
            place_exit_order(client, config, "Exit time reached",
                           get_current_premium(client, config.option_symbol, config.option_exchange))
            position_open = False
            break

        # Fetch current premium
        current_premium = get_current_premium(client, config.option_symbol, config.option_exchange)
        if current_premium is None:
            log("WARNING: Failed to fetch quote, will retry next cycle")
            time.sleep(config.poll_interval)
            continue

        # Compute profit percentage
        profit_pct = ((current_premium - config.entry_price) / config.entry_price) * 100

        # SL floor computation
        sl_floor = compute_sl_floor(
            config.entry_price, current_premium,
            config.sl_pct, config.trail_activate_pct, config.trail_step_pct
        )

        # Track SL level changes and trail activation
        if last_sl_floor is None:
            last_sl_floor = sl_floor
            log(f"Initial SL floor: {sl_floor:.2f}")

        if profit_pct >= config.trail_activate_pct and not trail_activated:
            trail_activated = True
            log(f"🔄 TRAIL ACTIVATED! Profit {profit_pct:.2f}% >= {config.trail_activate_pct}%")
            log(f"  SL floor moved to: {sl_floor:.2f}")

        if sl_floor != last_sl_floor:
            log(f"📈 SL floor updated: {last_sl_floor:.2f} → {sl_floor:.2f}")
            last_sl_floor = sl_floor

        log(f"LTP: {current_premium:.2f} | Profit: {profit_pct:.2f}% | SL: {sl_floor:.2f}")

        # Check if SL hit
        if current_premium <= sl_floor:
            log(f"🛑 STOP-LOSS HIT! LTP {current_premium:.2f} <= SL floor {sl_floor:.2f}")
            log(f"  Profit at exit: {profit_pct:.2f}%")
            place_exit_order(client, config, "Stop-loss hit", current_premium)
            position_open = False
            break

        time.sleep(config.poll_interval)

    log("Monitor terminated.")
    sys.exit(0)


if __name__ == "__main__":
    main()
