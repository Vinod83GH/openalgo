#!/usr/bin/env python
"""
First 1-Minute Candle Strategy - Index Options (NIFTY/BANKNIFTY)
================================================================
Strategy Logic:
1. Wait for 1st 1-min candle to close (9:15-9:16)
2. Mark its High and Low
3. Determine bias:
   - Close ABOVE midpoint (bullish) → wait for retracement to High → BUY CALL
   - Close BELOW midpoint (bearish) → wait for retracement to Low → BUY PUT
4. Stop-loss: opposite side of 1st candle
5. Auto-exit at configured exit time

Configuration (via Environment Variables on Python Strategy page):
  STRATEGY_SYMBOL     = NIFTY | BANKNIFTY          (default: NIFTY)
  STRATEGY_STRIKE     = ITM3|ITM2|ITM1|ATM|OTM1|OTM2|OTM3  (default: ITM2)
  STRATEGY_LOTS       = Number of lots              (default: 1)
  STRATEGY_ENTRY_START = HH:MM entry window start  (default: 09:16)
  STRATEGY_ENTRY_END  = HH:MM entry window end     (default: 10:30)
  STRATEGY_EXIT_TIME  = HH:MM force exit time      (default: 15:15)
  STRATEGY_PRODUCT    = MIS | NRML                  (default: MIS)
  STRATEGY_EXCHANGE   = NFO | BFO                   (default: NFO)
"""

import os
import time
import requests
from datetime import datetime, timedelta

from openalgo import api


# ============================================================
# PAPER JOURNAL CLIENT
# ============================================================

class PaperJournalClient:
    """Lightweight REST client for the Paper Trade Journal service."""

    def __init__(self, api_key: str, host: str):
        self.api_key = api_key
        self.host = host.rstrip("/")
        self._active = None  # Cached mode status

    def is_active(self) -> bool:
        """Check if app is in Analyzer mode by querying the journal status endpoint."""
        try:
            resp = requests.get(
                f"{self.host}/api/v1/paperjournal/status",
                params={"apikey": self.api_key},
                timeout=5,
            )
            if resp.status_code == 200:
                data = resp.json()
                mode = data.get("data", {}).get("mode", "")
                self._active = mode == "analyze"
            else:
                self._active = False
        except Exception:
            self._active = False
        return self._active

    def open_trade(self, **kwargs) -> int | None:
        """Open a new trade record. Returns trade_id or None on failure."""
        try:
            payload = {"apikey": self.api_key, **kwargs}
            resp = requests.post(
                f"{self.host}/api/v1/paperjournal/trade",
                json=payload,
                timeout=10,
            )
            if resp.status_code == 201:
                data = resp.json()
                return data.get("data", {}).get("trade_id")
        except Exception:
            pass
        return None

    def close_trade(self, trade_id: int, **kwargs) -> bool:
        """Close/update an existing trade. Returns True on success."""
        try:
            payload = {"apikey": self.api_key, **kwargs}
            resp = requests.patch(
                f"{self.host}/api/v1/paperjournal/trade/{trade_id}",
                json=payload,
                timeout=10,
            )
            return resp.status_code == 200
        except Exception:
            return False

# ============================================================
# CONFIGURATION — Read from environment variables
# ============================================================

API_KEY = os.getenv("OPENALGO_APIKEY")
if not API_KEY:
    print("Error: OPENALGO_APIKEY environment variable not set")
    exit(1)

HOST = os.getenv("OPENALGO_HOST", "http://127.0.0.1:5000")

# Strategy parameters (configurable from Python Strategy page env vars)
SYMBOL = os.getenv("STRATEGY_SYMBOL", "NIFTY")
STRIKE_SELECTION = os.getenv("STRATEGY_STRIKE", "ITM2")
LOTS = int(os.getenv("STRATEGY_LOTS", "1"))
ENTRY_START = os.getenv("STRATEGY_ENTRY_START", "09:16")
ENTRY_END = os.getenv("STRATEGY_ENTRY_END", "10:30")
EXIT_TIME = os.getenv("STRATEGY_EXIT_TIME", "15:15")
PRODUCT = os.getenv("STRATEGY_PRODUCT", "MIS")
EXCHANGE = os.getenv("STRATEGY_EXCHANGE", "NFO")

# Derived
STRATEGY_NAME = f"FirstMinCandle-{SYMBOL}"
SPOT_EXCHANGE = os.getenv("STRATEGY_EXCHANGE", "NSE_INDEX")  # Spot exchange from page env (default NSE_INDEX for indices)

# Lot sizes (will be fetched from API, these are fallbacks)
LOT_SIZES = {"NIFTY": 65, "BANKNIFTY": 30}

# Parse time configs
def parse_time(time_str):
    parts = time_str.split(":")
    return int(parts[0]), int(parts[1])

ENTRY_START_H, ENTRY_START_M = parse_time(ENTRY_START)
ENTRY_END_H, ENTRY_END_M = parse_time(ENTRY_END)
EXIT_H, EXIT_M = parse_time(EXIT_TIME)

# API client
client = api(api_key=API_KEY, host=HOST)

# Paper Journal client
journal = PaperJournalClient(api_key=API_KEY, host=HOST)

# ============================================================
# STATE
# ============================================================

first_candle_high = None
first_candle_low = None
first_candle_close = None
first_candle_mid = None
bias = None
entry_done = False
option_symbol = None
option_exchange = None
actual_quantity = None
journal_trade_id = None


def log(msg):
    """Print with timestamp."""
    print(f"[{datetime.now().strftime('%H:%M:%S')}] {msg}")


def get_nearest_expiry():
    """Calculate the nearest expiry date in DDMMMYY format based on underlying type.

    Rules:
    - NIFTY: Weekly Tuesday expiry. If today is Tuesday, pick next week.
    - SENSEX: Weekly Thursday expiry. If today is Thursday, pick next week.
    - BANKNIFTY: Monthly last Tuesday expiry. If today is expiry day, pick next month.
    - STOCKS (everything else): Monthly last Tuesday expiry. If today is expiry day, pick next month.
    """
    today = datetime.now().date()
    symbol_upper = SYMBOL.upper()

    if symbol_upper == "NIFTY":
        # Weekly Tuesday expiry
        expiry_weekday = 1  # Tuesday = 1
        days_until = (expiry_weekday - today.weekday()) % 7
        if days_until == 0:
            # Today is Tuesday (expiry day) — skip to next week
            days_until = 7
        expiry = today + timedelta(days=days_until)

    elif symbol_upper == "SENSEX":
        # Weekly Thursday expiry
        expiry_weekday = 3  # Thursday = 3
        days_until = (expiry_weekday - today.weekday()) % 7
        if days_until == 0:
            # Today is Thursday (expiry day) — skip to next week
            days_until = 7
        expiry = today + timedelta(days=days_until)

    else:
        # BANKNIFTY and all STOCKS: Monthly last Tuesday expiry
        # Find last Tuesday of current month
        import calendar
        year, month = today.year, today.month

        # Get last day of month
        last_day = calendar.monthrange(year, month)[1]
        last_date = today.replace(day=last_day)

        # Find last Tuesday
        while last_date.weekday() != 1:  # Tuesday = 1
            last_date -= timedelta(days=1)

        if today >= last_date:
            # Already past this month's expiry — go to next month
            if month == 12:
                year += 1
                month = 1
            else:
                month += 1
            last_day = calendar.monthrange(year, month)[1]
            last_date = datetime(year, month, last_day).date()
            while last_date.weekday() != 1:
                last_date -= timedelta(days=1)

        expiry = last_date

    return expiry.strftime("%d%b%y").upper()


def resolve_option_symbol(option_type, spot_ltp):
    """
    Use the /api/v1/optionsymbol API to resolve the correct option contract.
    Returns (symbol, exchange, lotsize) or (None, None, None) on failure.
    """
    url = f"{HOST}/api/v1/optionsymbol"
    expiry_date = get_nearest_expiry()
    payload = {
        "apikey": API_KEY,
        "underlying": SYMBOL,
        "exchange": SPOT_EXCHANGE,
        "expiry_date": expiry_date,
        "offset": STRIKE_SELECTION,
        "option_type": option_type,
    }

    log(f"Resolving option: {SYMBOL} {option_type} {STRIKE_SELECTION} expiry={expiry_date} (LTP={spot_ltp})...")

    try:
        resp = requests.post(url, json=payload, timeout=10)
        data = resp.json()

        if data.get("status") == "success":
            sym = data.get("symbol")
            exch = data.get("exchange", EXCHANGE)
            lotsize = data.get("lotsize", LOT_SIZES.get(SYMBOL, 75))
            log(f"  ✅ Resolved: {sym} on {exch} (lot={lotsize})")
            return sym, exch, int(lotsize)
        else:
            log(f"  ❌ Resolution failed: {data.get('message', 'Unknown error')}")
            return None, None, None
    except Exception as e:
        log(f"  ❌ API error: {e}")
        return None, None, None


def wait_for_time(hour, minute, label=""):
    """Wait until the specified time."""
    while True:
        now = datetime.now()
        target = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
        if now >= target:
            return
        wait_secs = (target - now).total_seconds()
        if wait_secs > 60:
            log(f"Waiting {wait_secs:.0f}s for {label} ({hour:02d}:{minute:02d})...")
        time.sleep(min(wait_secs, 30))


def is_past_time(hour, minute):
    """Check if current time is past the given time."""
    now = datetime.now()
    return now.hour > hour or (now.hour == hour and now.minute >= minute)


def get_first_candle():
    """Capture the 1st 1-minute candle after it closes."""
    global first_candle_high, first_candle_low, first_candle_close, first_candle_mid, bias

    log("Waiting for 1st minute candle to close...")
    wait_for_time(ENTRY_START_H, ENTRY_START_M, "1st candle close")

    # Extra 5 seconds to ensure candle is fully formed
    time.sleep(5)

    # Fetch today's 1-min data
    end_date = datetime.now().strftime("%Y-%m-%d")
    start_date = end_date

    for attempt in range(5):
        try:
            df = client.history(
                symbol=SYMBOL,
                exchange=SPOT_EXCHANGE,
                interval="1m",
                start_date=start_date,
                end_date=end_date,
            )

            # Handle API error responses (returns dict instead of DataFrame)
            if isinstance(df, dict):
                error_msg = df.get("message", df.get("error", "Unknown API error"))
                log(f"  API error: {error_msg}, retry {attempt + 1}/5...")
                time.sleep(3)
                continue

            if df is None or df.empty:
                log(f"  Empty data, retry {attempt + 1}/5...")
                time.sleep(3)
                continue

            # Get today's data
            if hasattr(df, 'index') and hasattr(df.index, 'date'):
                today_data = df[df.index.date == datetime.now().date()]
            else:
                today_data = df

            if today_data is None or (hasattr(today_data, 'empty') and today_data.empty):
                log(f"  No today's data, retry {attempt + 1}/5...")
                time.sleep(3)
                continue

            # First candle
            candle = today_data.iloc[0]
            first_candle_high = round(float(candle["high"]), 2)
            first_candle_low = round(float(candle["low"]), 2)
            first_candle_close = round(float(candle["close"]), 2)
            first_candle_mid = round((first_candle_high + first_candle_low) / 2, 2)

            log(f"")
            log(f"{'='*50}")
            log(f"  1st CANDLE: H={first_candle_high} L={first_candle_low} C={first_candle_close}")
            log(f"  Midpoint: {first_candle_mid}")
            log(f"{'='*50}")
            log(f"  Waiting for breakout:")
            log(f"    CALL entry: any candle close > {first_candle_high}")
            log(f"    PUT entry:  any candle close < {first_candle_low}")
            log(f"    SL (after entry): close crosses opposite side")
            log(f"")
            return True

        except Exception as e:
            log(f"  Error: {e}, retry {attempt + 1}/5...")
            time.sleep(3)

    log("Failed to capture 1st candle. Aborting.")
    return False


def get_spot_ltp():
    """Get current spot LTP."""
    try:
        quotes = client.quotes(symbol=SYMBOL, exchange=SPOT_EXCHANGE)
        if quotes and "ltp" in quotes:
            return float(quotes["ltp"])
    except Exception as e:
        log(f"  Quote error: {e}")
    return None


def place_entry(option_type):
    """Resolve option and place entry order."""
    global entry_done, option_symbol, option_exchange, actual_quantity, journal_trade_id

    spot_ltp = get_spot_ltp()
    # spot_ltp is optional — used for logging only, don't block entry if quotes fail

    # Resolve option symbol via API
    sym, exch, lotsize = resolve_option_symbol(option_type, spot_ltp)
    if sym is None:
        log("Option resolution failed. Skipping entry.")
        return False

    option_symbol = sym
    option_exchange = exch
    actual_quantity = LOTS * lotsize

    log(f"")
    log(f"🚀 ENTRY: BUY {option_symbol} | Qty={actual_quantity} ({LOTS} lots × {lotsize})")

    try:
        response = client.placesmartorder(
            strategy=STRATEGY_NAME,
            symbol=option_symbol,
            action="BUY",
            exchange=option_exchange,
            price_type="MARKET",
            product=PRODUCT,
            quantity=actual_quantity,
            position_size=actual_quantity,
        )
        log(f"  Order Response: {response}")
        entry_done = True

        # Log trade to paper journal
        try:
            trade_id = journal.open_trade(
                strategy_name=STRATEGY_NAME,
                direction=bias,
                trade_date=datetime.now().strftime("%Y-%m-%d"),
                entry_time=datetime.now().isoformat(),
                entry_spot_price=spot_ltp,
                entry_option_symbol=option_symbol,
                entry_quantity=actual_quantity,
                entry_action="BUY",
                custom_metadata={
                    "first_candle_high": first_candle_high,
                    "first_candle_low": first_candle_low,
                    "first_candle_close": first_candle_close,
                    "first_candle_mid": first_candle_mid,
                    "bias": bias,
                },
            )
            if trade_id:
                journal_trade_id = trade_id
                log(f"  📓 Journal: Trade opened (ID={trade_id})")
            else:
                log(f"  📓 Journal: open_trade returned no ID")
        except Exception as e:
            log(f"  📓 Journal: Error logging entry - {e}")

        return True
    except Exception as e:
        log(f"  Order Error: {e}")
        return False


def place_exit(reason=""):
    """Exit the position."""
    if not entry_done or not option_symbol:
        return

    log(f"")
    log(f"🛑 EXIT ({reason}): SELL {option_symbol} | Qty={actual_quantity}")

    try:
        response = client.placesmartorder(
            strategy=STRATEGY_NAME,
            symbol=option_symbol,
            action="SELL",
            exchange=option_exchange,
            price_type="MARKET",
            product=PRODUCT,
            quantity=actual_quantity,
            position_size=0,
        )
        log(f"  Exit Response: {response}")
    except Exception as e:
        log(f"  Exit Error: {e}")

    # Log exit to paper journal
    try:
        if journal_trade_id:
            spot_ltp = get_spot_ltp()
            success = journal.close_trade(
                journal_trade_id,
                exit_time=datetime.now().isoformat(),
                exit_spot_price=spot_ltp,
                exit_reason=reason,
            )
            if success:
                log(f"  📓 Journal: Trade closed (ID={journal_trade_id})")
            else:
                log(f"  📓 Journal: close_trade failed")
    except Exception as e:
        log(f"  📓 Journal: Error logging exit - {e}")


def get_latest_candles():
    """Fetch today's 1-min candles and return the latest closed one."""
    end_date = datetime.now().strftime("%Y-%m-%d")
    start_date = end_date

    try:
        df = client.history(
            symbol=SYMBOL,
            exchange=SPOT_EXCHANGE,
            interval="1m",
            start_date=start_date,
            end_date=end_date,
        )

        # Handle API error responses (returns dict instead of DataFrame)
        if isinstance(df, dict):
            return None

        if df is None or df.empty:
            return None

        # Get today's data
        if hasattr(df, 'index') and hasattr(df.index, 'date'):
            today_data = df[df.index.date == datetime.now().date()]
        else:
            today_data = df

        if today_data is None or (hasattr(today_data, 'empty') and today_data.empty):
            return None

        return today_data

    except Exception as e:
        log(f"  Candle fetch error: {e}")
        return None


def monitor_for_entry():
    """Step 1: Monitor 1-min candles for breakout — no order placed here."""
    global bias

    log(f"STEP 1: Monitoring for breakout via 1-min candle close (until {ENTRY_END})...")
    log(f"  BULLISH breakout: candle close > {first_candle_high} (1st candle HIGH)")
    log(f"  BEARISH breakout: candle close < {first_candle_low} (1st candle LOW)")

    while True:
        # Check entry window timeout
        if is_past_time(ENTRY_END_H, ENTRY_END_M):
            log(f"⏰ Entry window closed ({ENTRY_END}). No breakout occurred.")
            return

        # Wait for the current minute to close (sleep until next minute + 5s buffer)
        now = datetime.now()
        seconds_to_next_min = 60 - now.second + 5
        log(f"  Waiting {seconds_to_next_min}s for next candle close...")
        time.sleep(seconds_to_next_min)

        # Fetch latest candles
        candles = get_latest_candles()
        if candles is None or (hasattr(candles, 'empty') and candles.empty):
            log(f"  No candle data available, retrying...")
            continue

        # Get the last closed candle (most recent row)
        latest = candles.iloc[-1]
        latest_close = round(float(latest["close"]), 2)

        candle_time = candles.index[-1] if hasattr(candles.index[-1], 'strftime') else "?"
        log(f"  Candle [{candle_time}] C={latest_close}")

        # Check BULLISH breakout: close > 1st candle HIGH
        if latest_close > first_candle_high:
            bias = "BULLISH"
            log(f"  ✅ STEP 1 CONFIRMED: BULLISH BREAKOUT! Close ({latest_close}) > HIGH ({first_candle_high})")
            log(f"  Now waiting for retracement + re-test...")
            monitor_for_retest()
            return

        # Check BEARISH breakout: close < 1st candle LOW
        elif latest_close < first_candle_low:
            bias = "BEARISH"
            log(f"  ✅ STEP 1 CONFIRMED: BEARISH BREAKOUT! Close ({latest_close}) < LOW ({first_candle_low})")
            log(f"  Now waiting for retracement + re-test...")
            monitor_for_retest()
            return


def monitor_for_retest():
    """Step 2: After breakout, wait for retracement then re-test.
    If opposite side breaks out during wait, flip bias and restart Step 2."""
    global entry_done, bias

    if bias == "BULLISH":
        log(f"STEP 2: Waiting for retracement then candle close > {first_candle_high} to confirm CALL")
    else:
        log(f"STEP 2: Waiting for retracement then candle close < {first_candle_low} to confirm PUT")

    retraced = False  # Track if price has pulled back

    while not entry_done:
        # Check entry window timeout
        if is_past_time(ENTRY_END_H, ENTRY_END_M):
            log(f"⏰ Entry window closed ({ENTRY_END}). Retracement not confirmed.")
            return

        # Wait for next candle
        now = datetime.now()
        seconds_to_next_min = 60 - now.second + 5
        time.sleep(seconds_to_next_min)

        # Fetch latest candles
        candles = get_latest_candles()
        if candles is None or (hasattr(candles, 'empty') and candles.empty):
            continue

        latest = candles.iloc[-1]
        latest_high = round(float(latest["high"]), 2)
        latest_low = round(float(latest["low"]), 2)
        latest_close = round(float(latest["close"]), 2)

        candle_time = candles.index[-1] if hasattr(candles.index[-1], 'strftime') else "?"

        if bias == "BULLISH":
            # Check for opposite-side breakout (bearish breakdown while waiting)
            if latest_close < first_candle_low:
                log(f"  🔄 FLIP! [{candle_time}] Close ({latest_close}) < LOW ({first_candle_low}) — switching to BEARISH")
                bias = "BEARISH"
                retraced = False
                log(f"STEP 2 (RESET): Now waiting for retracement then candle close < {first_candle_low} to confirm PUT")
                continue

            # Check if price has retraced (candle close ≤ HIGH)
            if not retraced and latest_close <= first_candle_high:
                retraced = True
                log(f"  📉 Retracement detected [{candle_time}] C={latest_close} ≤ HIGH={first_candle_high}")

            # After retracement, check for re-test: candle touches HIGH AND closes above it
            elif retraced and latest_high >= first_candle_high and latest_close > first_candle_high:
                log(f"  ✅ STEP 2 CONFIRMED [{candle_time}]: Re-test! H={latest_high} touched HIGH, C={latest_close} > HIGH={first_candle_high}")
                place_entry("CE")
                return
            else:
                log(f"  Candle [{candle_time}] C={latest_close} | Retraced={retraced} | Waiting for re-test above {first_candle_high}")

        elif bias == "BEARISH":
            # Check for opposite-side breakout (bullish breakout while waiting)
            if latest_close > first_candle_high:
                log(f"  🔄 FLIP! [{candle_time}] Close ({latest_close}) > HIGH ({first_candle_high}) — switching to BULLISH")
                bias = "BULLISH"
                retraced = False
                log(f"STEP 2 (RESET): Now waiting for retracement then candle close > {first_candle_high} to confirm CALL")
                continue

            # Check if price has retraced (candle close ≥ LOW)
            if not retraced and latest_close >= first_candle_low:
                retraced = True
                log(f"  📈 Retracement detected [{candle_time}] C={latest_close} ≥ LOW={first_candle_low}")

            # After retracement, check for re-test: candle touches LOW AND closes below it
            elif retraced and latest_low <= first_candle_low and latest_close < first_candle_low:
                log(f"  ✅ STEP 2 CONFIRMED [{candle_time}]: Re-test! L={latest_low} touched LOW, C={latest_close} < LOW={first_candle_low}")
                place_entry("PE")
                return
            else:
                log(f"  Candle [{candle_time}] C={latest_close} | Retraced={retraced} | Waiting for re-test below {first_candle_low}")


def monitor_stop_loss():
    """Monitor 1-min candles for SL or exit time (candle-based)."""
    if not entry_done:
        return

    log(f"Monitoring SL & exit time via 1-min candles (exit at {EXIT_TIME})...")

    while True:
        # Check exit time
        if is_past_time(EXIT_H, EXIT_M):
            place_exit(f"Exit time {EXIT_TIME}")
            return

        # Wait for the current minute to close
        now = datetime.now()
        seconds_to_next_min = 60 - now.second + 5
        time.sleep(seconds_to_next_min)

        # Check exit time again after sleep
        if is_past_time(EXIT_H, EXIT_M):
            place_exit(f"Exit time {EXIT_TIME}")
            return

        # Fetch latest candles
        candles = get_latest_candles()
        if candles is None or (hasattr(candles, 'empty') and candles.empty):
            log(f"  No candle data for SL check, retrying...")
            continue

        latest = candles.iloc[-1]
        latest_high = round(float(latest["high"]), 2)
        latest_low = round(float(latest["low"]), 2)
        latest_close = round(float(latest["close"]), 2)

        candle_time = candles.index[-1] if hasattr(candles.index[-1], 'strftime') else "?"
        log(f"  SL Check [{candle_time}] H={latest_high} L={latest_low} C={latest_close}")

        if bias == "BULLISH" and latest_close < first_candle_low:
            place_exit(f"SL HIT - Candle Close {latest_close} < 1st Candle Low {first_candle_low}")
            return

        elif bias == "BEARISH" and latest_close > first_candle_high:
            place_exit(f"SL HIT - Candle Close {latest_close} > 1st Candle High {first_candle_high}")
            return


def main():
    """Main strategy execution."""
    log(f"")
    log(f"{'='*60}")
    log(f"  FIRST 1-MIN CANDLE STRATEGY")
    log(f"  Symbol: {SYMBOL} | Strike: {STRIKE_SELECTION} | Lots: {LOTS}")
    log(f"  Entry: {ENTRY_START}-{ENTRY_END} | Exit: {EXIT_TIME}")
    log(f"  Product: {PRODUCT} | Exchange: {EXCHANGE}")
    log(f"{'='*60}")
    log(f"")

    # Step 1: Wait for market open
    wait_for_time(9, 15, "market open")

    # Step 2: Capture 1st candle
    if not get_first_candle():
        return

    # Step 3: Monitor for entry
    monitor_for_entry()

    # Step 4: Monitor SL / exit
    monitor_stop_loss()

    log(f"\n✅ Strategy complete for today.")


if __name__ == "__main__":
    main()
