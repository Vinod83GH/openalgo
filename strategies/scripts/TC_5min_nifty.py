#!/usr/bin/env python
"""
5-Minute Candle Strategy - Index Options (NIFTY/BANKNIFTY)
==========================================================
Strategy Logic:
1. Wait for defined 5-min candle to close (starting at STRATEGY_ENTRY_START)
2. Mark its High and Low
3. Monitor subsequent 5-min candles for breakout:
   - Close ABOVE HIGH (bullish breakout) → wait for retracement + re-test → BUY CALL
   - Close BELOW LOW (bearish breakout) → wait for retracement + re-test → BUY PUT
4. Bias flip: if opposite side breaks during retracement, flip direction
5. Stop-loss: candle close crosses opposite side of defined candle
6. Auto-exit at configured exit time or profit target

Configuration (via Environment Variables on Python Strategy page):
  STRATEGY_SYMBOL     = NIFTY | BANKNIFTY          (default: NIFTY)
  STRATEGY_STRIKE     = ITM3|ITM2|ITM1|ATM|OTM1|OTM2|OTM3  (default: ITM2)
  STRATEGY_LOTS       = Number of lots              (default: 1)
  STRATEGY_ENTRY_START = HH:MM 5-min candle start  (default: 09:15)
  STRATEGY_ENTRY_END  = HH:MM entry window end     (default: 12:00)
  STRATEGY_EXIT_TIME  = HH:MM force exit time      (default: 15:15)
  STRATEGY_PRODUCT    = MIS | NRML                  (default: MIS)
  STRATEGY_EXCHANGE   = NFO | BFO                   (default: NFO)
  STRATEGY_TARGET_PCT = Profit target %             (default: 0 = disabled)
  STRATEGY_ORDER_TYPE = MARKET | LIMIT              (default: MARKET)
"""

import os
import sys
import signal
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
        self._active = None

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
            filtered_kwargs = {k: v for k, v in kwargs.items() if v is not None}
            payload = {"apikey": self.api_key, **filtered_kwargs}
            resp = requests.post(
                f"{self.host}/api/v1/paperjournal/trade",
                json=payload,
                timeout=10,
            )
            if resp.status_code == 201:
                data = resp.json()
                return data.get("data", {}).get("trade_id")
            else:
                log(f"  📓 Journal API returned {resp.status_code}: {resp.text[:200]}")
        except Exception as e:
            log(f"  📓 Journal API error: {e}")
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
ENTRY_START = os.getenv("STRATEGY_ENTRY_START", "09:15")
ENTRY_END = os.getenv("STRATEGY_ENTRY_END", "12:00")
EXIT_TIME = os.getenv("STRATEGY_EXIT_TIME", "15:15")
PRODUCT = os.getenv("STRATEGY_PRODUCT", "MIS")
EXCHANGE = os.getenv("STRATEGY_EXCHANGE", "NFO")
TARGET_PCT = float(os.getenv("STRATEGY_TARGET_PCT", "0"))
ORDER_TYPE = os.getenv("STRATEGY_ORDER_TYPE", "MARKET")
RETRACEMENT_BUFFER = float(os.getenv("STRATEGY_RETRACEMENT_BUFFER", "2"))
MAX_LOSS_PCT = float(os.getenv("STRATEGY_MAX_LOSS_PCT", "10"))  # Max loss % on option premium before forced exit. 0 = disabled.
MAX_FLIP_ENTRIES = int(os.getenv("STRATEGY_MAX_FLIP_ENTRIES", "3"))  # Max flip re-entries after SL hit (default: 3)
TRAIL_GAP = float(os.getenv("STRATEGY_TRAIL_GAP", "5"))  # Trailing SL: points below high watermark after target hit. 0 = disabled (exit at target).

# Derived
STRATEGY_NAME = f"TC5minCandle-{SYMBOL}"
SPOT_EXCHANGE = os.getenv("STRATEGY_SPOT_EXCHANGE", "NSE_INDEX")  # Spot exchange for quotes/history (default NSE_INDEX for indices)

# Candle interval
CANDLE_INTERVAL = "5m"
CANDLE_DURATION_SECS = 300  # 5 minutes in seconds

# Lot sizes (fallbacks — actual fetched from API)
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
exit_done = False
option_symbol = None
option_exchange = None
actual_quantity = None
journal_trade_id = None
entry_option_price_saved = None


def log(msg):
    """Print with timestamp."""
    print(f"[{datetime.now().strftime('%H:%M:%S')}] {msg}")


def graceful_exit_handler(signum, frame):
    """Handle SIGTERM/SIGINT: exit open position before dying."""
    sig_name = "SIGTERM" if signum == signal.SIGTERM else "SIGINT"
    log(f"")
    log(f"⚠️ {sig_name} received — graceful shutdown initiated")
    if entry_done and not exit_done and option_symbol:
        log(f"  📤 Exiting open position before shutdown...")
        place_exit(f"Graceful shutdown ({sig_name})")
    else:
        log(f"  No open position to exit.")
    log(f"  👋 Strategy terminated gracefully.")
    sys.exit(0)


signal.signal(signal.SIGTERM, graceful_exit_handler)
# signal.signal(signal.SIGINT, graceful_exit_handler)


def get_nearest_expiry():
    """Calculate the nearest expiry date in DDMMMYY format based on underlying type.

    Rules:
    - NIFTY: Weekly Tuesday expiry. If today is Tuesday, pick next week.
    - SENSEX: Weekly Thursday expiry. If today is Thursday, pick next week.
    - BANKNIFTY/STOCKS: Monthly last Tuesday expiry. Never trade same-day expiry.
    """
    today = datetime.now().date()
    symbol_upper = SYMBOL.upper()

    if symbol_upper == "NIFTY":
        expiry_weekday = 1  # Tuesday
        days_until = (expiry_weekday - today.weekday()) % 7
        if days_until == 0:
            days_until = 7
        expiry = today + timedelta(days=days_until)

    elif symbol_upper == "SENSEX":
        expiry_weekday = 3  # Thursday
        days_until = (expiry_weekday - today.weekday()) % 7
        if days_until == 0:
            days_until = 7
        expiry = today + timedelta(days=days_until)

    else:
        # BANKNIFTY and all STOCKS: Monthly last Tuesday expiry
        import calendar
        year, month = today.year, today.month

        last_day = calendar.monthrange(year, month)[1]
        last_date = today.replace(day=last_day)

        while last_date.weekday() != 1:  # Tuesday = 1
            last_date -= timedelta(days=1)

        if today >= last_date:
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
    """Use the /api/v1/optionsymbol API to resolve the correct option contract."""
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


def get_seconds_to_next_5min_close():
    """Calculate seconds until the next 5-min candle closes (+ 5s buffer)."""
    now = datetime.now()
    # 5-min candles align to clock: :00, :05, :10, :15, :20, :25, :30, :35, :40, :45, :50, :55
    current_minute = now.minute
    next_5min_mark = ((current_minute // 5) + 1) * 5
    if next_5min_mark >= 60:
        # Next 5-min mark is in the next hour
        target = now.replace(minute=0, second=0, microsecond=0) + timedelta(hours=1)
    else:
        target = now.replace(minute=next_5min_mark, second=0, microsecond=0)
    wait_secs = (target - now).total_seconds() + 5  # 5s buffer for candle to form
    return max(wait_secs, 5)


def get_first_candle():
    """Capture the defined 5-min candle after it closes."""
    global first_candle_high, first_candle_low, first_candle_close, first_candle_mid

    # Calculate when the 5-min candle closes (ENTRY_START + 5 minutes)
    candle_close_h = ENTRY_START_H
    candle_close_m = ENTRY_START_M + 5
    if candle_close_m >= 60:
        candle_close_h += 1
        candle_close_m -= 60

    log(f"Waiting for 5-min candle to close ({ENTRY_START_H:02d}:{ENTRY_START_M:02d} - {candle_close_h:02d}:{candle_close_m:02d})...")
    wait_for_time(candle_close_h, candle_close_m, "5-min candle close")

    # Extra 5 seconds to ensure candle is fully formed
    time.sleep(5)

    # Fetch today's 5-min data
    end_date = datetime.now().strftime("%Y-%m-%d")
    start_date = end_date

    for attempt in range(5):
        try:
            df = client.history(
                symbol=SYMBOL,
                exchange=SPOT_EXCHANGE,
                interval=CANDLE_INTERVAL,
                start_date=start_date,
                end_date=end_date,
            )

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

            # Find the candle for the ENTRY_START time slot
            # The candle opens at ENTRY_START (e.g., 11:20) and closes at ENTRY_START+5 (11:25)
            # Different brokers/APIs may index candles by open OR close time
            # So we search for both ENTRY_START_H:ENTRY_START_M and the close time
            candle_open_h = ENTRY_START_H
            candle_open_m = ENTRY_START_M
            candle_close_h_search = ENTRY_START_H
            candle_close_m_search = ENTRY_START_M + 5
            if candle_close_m_search >= 60:
                candle_close_h_search += 1
                candle_close_m_search -= 60

            candle = None
            matched_time = None
            for idx in today_data.index:
                candle_dt = idx
                if hasattr(idx, 'hour'):
                    # Match by open time (most common)
                    if candle_dt.hour == candle_open_h and candle_dt.minute == candle_open_m:
                        candle = today_data.loc[idx]
                        matched_time = f"{candle_dt.hour:02d}:{candle_dt.minute:02d}"
                        break
                    # Also try matching by close time (some APIs index by close)
                    if candle_dt.hour == candle_close_h_search and candle_dt.minute == candle_close_m_search:
                        candle = today_data.loc[idx]
                        matched_time = f"{candle_dt.hour:02d}:{candle_dt.minute:02d} (close-indexed)"
                        break

            if candle is not None:
                log(f"  ✅ Found candle at index time: {matched_time}")

            # No fallback — if candle not found, abort
            if candle is None:
                available_times = []
                for idx in today_data.index[:20]:
                    if hasattr(idx, 'strftime'):
                        available_times.append(idx.strftime('%H:%M'))
                log(f"  ❌ CANDLE NOT FOUND at {ENTRY_START_H:02d}:{ENTRY_START_M:02d}!")
                log(f"  Available candle times: {available_times}")
                log(f"  Aborting strategy.")
                return False

            first_candle_high = round(float(candle["high"]), 2)
            first_candle_low = round(float(candle["low"]), 2)
            first_candle_close = round(float(candle["close"]), 2)
            first_candle_mid = round((first_candle_high + first_candle_low) / 2, 2)

            log(f"")
            log(f"{'='*50}")
            log(f"  DEFINED 5-MIN CANDLE: H={first_candle_high} L={first_candle_low} C={first_candle_close}")
            log(f"  Midpoint: {first_candle_mid}")
            log(f"{'='*50}")
            log(f"  Waiting for breakout (5-min candle close):")
            log(f"    CALL entry: 5-min candle close > {first_candle_high}")
            log(f"    PUT entry:  5-min candle close < {first_candle_low}")
            log(f"    SL (after entry): 5-min close crosses opposite side")
            log(f"")
            return True

        except Exception as e:
            log(f"  Error: {e}, retry {attempt + 1}/5...")
            time.sleep(3)

    log("Failed to capture defined 5-min candle. Aborting.")
    return False


def get_spot_ltp():
    """Get current spot LTP."""
    try:
        quotes = client.quotes(symbol=SYMBOL, exchange=SPOT_EXCHANGE)
        if quotes and isinstance(quotes, dict):
            if "ltp" in quotes:
                return float(quotes["ltp"])
            elif "data" in quotes and isinstance(quotes["data"], dict) and "ltp" in quotes["data"]:
                return float(quotes["data"]["ltp"])
    except Exception as e:
        log(f"  Quote error: {e}")
    return None


def get_option_ltp(symbol, exchange):
    """Get current LTP for an option symbol, rounded to nearest whole number."""
    try:
        quotes = client.quotes(symbol=symbol, exchange=exchange)
        if quotes and isinstance(quotes, dict):
            if "ltp" in quotes:
                return round(float(quotes["ltp"]))
            elif "data" in quotes and isinstance(quotes["data"], dict) and "ltp" in quotes["data"]:
                return round(float(quotes["data"]["ltp"]))
    except Exception as e:
        log(f"  Option quote error for {symbol}: {e}")
    return None


def get_latest_5min_candles():
    """Fetch today's 5-min candles."""
    end_date = datetime.now().strftime("%Y-%m-%d")
    start_date = end_date

    try:
        df = client.history(
            symbol=SYMBOL,
            exchange=SPOT_EXCHANGE,
            interval=CANDLE_INTERVAL,
            start_date=start_date,
            end_date=end_date,
        )

        if isinstance(df, dict):
            return None
        if df is None or df.empty:
            return None

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


def place_entry(option_type):
    """Resolve option, fetch premium, and place entry order."""
    global entry_done, option_symbol, option_exchange, actual_quantity, journal_trade_id, entry_option_price_saved

    spot_ltp = get_spot_ltp()

    sym, exch, lotsize = resolve_option_symbol(option_type, spot_ltp)
    if sym is None:
        log("Option resolution failed. Skipping entry.")
        return False

    option_symbol = sym
    option_exchange = exch
    actual_quantity = LOTS * lotsize

    option_ltp = get_option_ltp(option_symbol, option_exchange)
    if option_ltp:
        log(f"  Option Premium: ₹{option_ltp}")

    # Determine order type from config
    if ORDER_TYPE == "MARKET":
        price_type = "MARKET"
    elif option_ltp:
        price_type = "LIMIT"
        price = option_ltp
    else:
        log(f"  ⚠️ LIMIT requested but no LTP available, falling back to MARKET")

    log(f"")
    log(f"🚀 ENTRY: BUY {option_symbol} | Qty={actual_quantity} ({LOTS} lots × {lotsize}) | {price_type} @ {price if price else 'MKT'}")

    try:
        order_params = {
            "strategy": STRATEGY_NAME,
            "symbol": option_symbol,
            "action": "BUY",
            "exchange": option_exchange,
            "price_type": price_type,
            "product": PRODUCT,
            "quantity": actual_quantity,
            "position_size": actual_quantity,
        }
        if price_type == "LIMIT":
            order_params["price"] = price
        if price_type == "MARKET":
            order_params["market_protection"] = -1

        response = client.placesmartorder(**order_params)
        log(f"  Order Response: {response}")

        if not isinstance(response, dict) or response.get("status") != "success":
            log(f"  ❌ Order placement FAILED. Not marking entry_done.")
            return False

        entry_done = True
        entry_option_price_saved = option_ltp

        # Log trade to paper journal (only in Analyzer mode)
        try:
            if journal.is_active():
                trade_id = journal.open_trade(
                    strategy_name=STRATEGY_NAME,
                    direction=bias,
                    trade_date=datetime.now().strftime("%Y-%m-%d"),
                    entry_time=datetime.now().isoformat(),
                    entry_spot_price=spot_ltp,
                    entry_option_symbol=option_symbol,
                    entry_option_price=option_ltp,
                    entry_quantity=actual_quantity,
                    entry_action="BUY",
                    custom_metadata={
                        "first_candle_high": first_candle_high,
                        "first_candle_low": first_candle_low,
                        "first_candle_close": first_candle_close,
                        "first_candle_mid": first_candle_mid,
                        "bias": bias,
                        "entry_price_type": price_type,
                        "candle_interval": "5m",
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
    global exit_done
    if not entry_done or not option_symbol or exit_done:
        return

    option_ltp = get_option_ltp(option_symbol, option_exchange)

    if ORDER_TYPE == "MARKET":
        price_type = "MARKET"
    elif option_ltp:
        price_type = "LIMIT"
        price = option_ltp
    else:
        log(f"  ⚠️ LIMIT requested but no LTP available for exit, falling back to MARKET")
        price_type = "MARKET"

    log(f"")
    log(f"🛑 EXIT ({reason}): SELL {option_symbol} | Qty={actual_quantity} | {price_type} @ {price if price else 'MKT'}")

    try:
        order_params = {
            "strategy": STRATEGY_NAME,
            "symbol": option_symbol,
            "action": "SELL",
            "exchange": option_exchange,
            "price_type": price_type,
            "product": PRODUCT,
            "quantity": actual_quantity,
            "position_size": 0,
        }
        if price_type == "LIMIT":
            order_params["price"] = price
        if price_type == "MARKET":
            order_params["market_protection"] = -1

        response = client.placesmartorder(**order_params)
        log(f"  Exit Response: {response}")

        if not isinstance(response, dict) or response.get("status") != "success":
            log(f"  ❌ Exit Order FAILED. Not marking exit_done.")
            return False

        exit_done = True

    except Exception as e:
        log(f"  Exit Error: {e}")

    # Log exit to paper journal (only in Analyzer mode)
    try:
        if journal_trade_id and journal.is_active():
            spot_ltp = get_spot_ltp()
            success = journal.close_trade(
                journal_trade_id,
                exit_time=datetime.now().isoformat(),
                exit_spot_price=spot_ltp,
                exit_option_price=option_ltp,
                exit_reason=reason,
            )
            if success:
                log(f"  📓 Journal: Trade closed (ID={journal_trade_id}) | Exit Premium: ₹{option_ltp}")
            else:
                log(f"  📓 Journal: close_trade failed")
    except Exception as e:
        log(f"  📓 Journal: Error logging exit - {e}")


def check_retracement(latest_close, latest_high, latest_low, retraced, candle_time):
    """Check retracement and re-test conditions for the current candle."""
    if bias == "BULLISH":
        if not retraced and latest_low <= first_candle_high + RETRACEMENT_BUFFER:
            log(f"  📉 Retracement detected [{candle_time}] C={latest_close} ≤ HIGH+buf={first_candle_high + RETRACEMENT_BUFFER}")
            if latest_close > first_candle_high:
                log(f"  ✅ STEP 2 CONFIRMED [{candle_time}]: Re-test! L={latest_low} touched HIGH+buf={first_candle_high + RETRACEMENT_BUFFER}, C={latest_close} > HIGH-buf")
                return True, True, "CE"

            return True, False, None
        if retraced and latest_high >= first_candle_high - RETRACEMENT_BUFFER and latest_close > first_candle_high - RETRACEMENT_BUFFER:
            log(f"  ✅ STEP 2 CONFIRMED [{candle_time}]: Re-test! H={latest_high} touched HIGH-buf={first_candle_high - RETRACEMENT_BUFFER}, C={latest_close} > HIGH-buf")
            return retraced, True, "CE"
        if retraced:
            log(f"  5m [{candle_time}] C={latest_close} | Retraced={retraced} | Waiting for re-test above {first_candle_high - RETRACEMENT_BUFFER}")
    elif bias == "BEARISH":
        if not retraced and latest_high >= first_candle_low - RETRACEMENT_BUFFER:
            log(f"  📈 Retracement detected [{candle_time}] C={latest_close} ≥ LOW-buf={first_candle_low - RETRACEMENT_BUFFER}")
            if latest_close < first_candle_low:
                log(f"  ✅ STEP 2 CONFIRMED [{candle_time}]: Re-test! H={latest_high} touched LOW-buf={first_candle_low - RETRACEMENT_BUFFER}, C={latest_close} < LOW+buf")
                return True, True, "PE"

            return True, False, None
        if retraced and latest_low <= first_candle_low + RETRACEMENT_BUFFER and latest_close < first_candle_low + RETRACEMENT_BUFFER:
            log(f"  ✅ STEP 2 CONFIRMED [{candle_time}]: Re-test! L={latest_low} touched LOW+buf={first_candle_low + RETRACEMENT_BUFFER}, C={latest_close} < LOW+buf")
            return retraced, True, "PE"
        if retraced:
            log(f"  5m [{candle_time}] C={latest_close} | Retraced={retraced} | Waiting for re-test below {first_candle_low + RETRACEMENT_BUFFER}")
    return retraced, False, None


def check_bias_flip(latest_close, candle_time):
    """Check if opposite side breaks out during retracement wait — flip bias."""
    global bias
    if bias == "BULLISH" and latest_close < first_candle_low:
        log(f"  🔄 FLIP! [{candle_time}] Close ({latest_close}) < LOW ({first_candle_low}) — switching to BEARISH")
        bias = "BEARISH"
        log(f"STEP 2 (RESET): Now waiting for retracement then 5-min close < {first_candle_low} to confirm PUT")
        return True
    elif bias == "BEARISH" and latest_close > first_candle_high:
        log(f"  🔄 FLIP! [{candle_time}] Close ({latest_close}) > HIGH ({first_candle_high}) — switching to BULLISH")
        bias = "BULLISH"
        log(f"STEP 2 (RESET): Now waiting for retracement then 5-min close > {first_candle_high} to confirm CALL")
        return True
    return False





def monitor_for_entry():
    """Step 1: Monitor 5-min candles for breakout — no order placed here."""
    global bias

    log(f"STEP 1: Monitoring for breakout via 5-min candle close (until {ENTRY_END})...")
    log(f"  BULLISH breakout: 5-min candle close > {first_candle_high} (defined candle HIGH)")
    log(f"  BEARISH breakout: 5-min candle close < {first_candle_low} (defined candle LOW)")

    while True:
        if is_past_time(ENTRY_END_H, ENTRY_END_M):
            log(f"⏰ Entry window closed ({ENTRY_END}). No breakout occurred.")
            return

        # Wait for next 5-min candle close
        wait_secs = get_seconds_to_next_5min_close()
        log(f"  Waiting {wait_secs:.0f}s for next 5-min candle close...")
        time.sleep(wait_secs)

        # Fetch latest 5-min candles
        candles = get_latest_5min_candles()
        if candles is None or (hasattr(candles, 'empty') and candles.empty):
            log(f"  No candle data available, retrying...")
            continue

        latest = candles.iloc[-1]
        latest_close = round(float(latest["close"]), 2)

        candle_time = candles.index[-1] if hasattr(candles.index[-1], 'strftime') else "?"
        log(f"  5m Candle [{candle_time}] C={latest_close}")

        # Check BULLISH breakout: close > defined candle HIGH
        if latest_close > first_candle_high:
            bias = "BULLISH"
            log(f"  ✅ STEP 1 CONFIRMED: BULLISH BREAKOUT! Close ({latest_close}) > HIGH ({first_candle_high})")
            log(f"  Now waiting for retracement + re-test...")
            monitor_for_retest()
            return

        # Check BEARISH breakout: close < defined candle LOW
        elif latest_close < first_candle_low:
            bias = "BEARISH"
            log(f"  ✅ STEP 1 CONFIRMED: BEARISH BREAKOUT! Close ({latest_close}) < LOW ({first_candle_low})")
            log(f"  Now waiting for retracement + re-test...")
            monitor_for_retest()
            return


def monitor_for_retest():
    """Step 2: After breakout, wait for retracement then re-test on 5-min candles."""
    global entry_done, bias

    if bias == "BULLISH":
        log(f"STEP 2: Waiting for retracement then 5-min candle close > {first_candle_high} to confirm CALL")
    else:
        log(f"STEP 2: Waiting for retracement then 5-min candle close < {first_candle_low} to confirm PUT")

    retraced = False

    while not entry_done:
        if is_past_time(ENTRY_END_H, ENTRY_END_M):
            log(f"⏰ Entry window closed ({ENTRY_END}). Retracement not confirmed.")
            return

        wait_secs = get_seconds_to_next_5min_close()
        time.sleep(wait_secs)

        candles = get_latest_5min_candles()
        if candles is None or (hasattr(candles, 'empty') and candles.empty):
            log(f"  ⚠️ No 5-min candle data available, retrying next cycle...")
            continue

        latest = candles.iloc[-1]
        latest_high = round(float(latest["high"]), 2)
        latest_low = round(float(latest["low"]), 2)
        latest_close = round(float(latest["close"]), 2)
        candle_time = candles.index[-1] if hasattr(candles.index[-1], 'strftime') else "?"

        if check_bias_flip(latest_close, candle_time):
            retraced = False
            continue

        retraced, confirmed, option_type = check_retracement(latest_close, latest_high, latest_low, retraced, candle_time)
        if confirmed:
            place_entry(option_type)
            return


def check_candle_sl(latest_close, candle_time, profit_pct):
    """Phase 1: Check candle-based stop-loss (defined candle HIGH/LOW).
    Returns True if SL hit and exit was placed."""
    if bias == "BULLISH":
        log(f"  SL [{candle_time}] Spot={latest_close} | SL={first_candle_low} (candle-based) | Profit={profit_pct:.1f}%")
        if latest_close < first_candle_low:
            place_exit(f"SL HIT - Spot {latest_close} < Defined Candle Low {first_candle_low}")
            return True
    elif bias == "BEARISH":
        log(f"  SL [{candle_time}] Spot={latest_close} | SL={first_candle_high} (candle-based) | Profit={profit_pct:.1f}%")
        if latest_close > first_candle_high:
            place_exit(f"SL HIT - Spot {latest_close} > Defined Candle High {first_candle_high}")
            return True
    return False





def trail_after_target(activation_premium):
    """
    Trailing SL after profit target is hit.
    SL = highest_premium - TRAIL_GAP (never below activation_premium).
    SL only moves up. Exit when premium drops to or below SL.
    
    Returns exit reason string, or None if time exit triggers first.
    """
    highest_premium = activation_premium
    trail_sl = activation_premium  # SL starts at activation price

    log(f"  🔄 TRAILING MODE ACTIVATED | Activation: {activation_premium:.2f} | Gap: {TRAIL_GAP} pts")

    while True:
        if is_past_time(EXIT_H, EXIT_M):
            place_exit(f"Exit time {EXIT_TIME} (trailing)")
            return "time"

        time.sleep(5)  # Poll every 5 seconds for trailing

        current_ltp = get_option_ltp(option_symbol, option_exchange)
        if current_ltp is None:
            continue

        # Update high watermark
        if current_ltp > highest_premium:
            highest_premium = current_ltp

        # Compute new SL: highest - gap, but never below activation price
        new_sl = max(highest_premium - TRAIL_GAP, activation_premium)

        # SL only goes up
        if new_sl > trail_sl:
            log(f"  📈 Trail SL updated: {trail_sl:.2f} → {new_sl:.2f} (HWM: {highest_premium:.2f})")
            trail_sl = new_sl

        profit_pct = ((current_ltp - entry_option_price_saved) / entry_option_price_saved) * 100
        log(f"  Trail | LTP: {current_ltp:.2f} | HWM: {highest_premium:.2f} | SL: {trail_sl:.2f} | P&L: {profit_pct:.1f}%")

        # Check if SL hit
        if current_ltp <= trail_sl:
            log(f"  🛑 TRAIL SL HIT! LTP {current_ltp:.2f} <= SL {trail_sl:.2f}")
            place_exit(f"Trail SL hit (LTP={current_ltp:.2f}, SL={trail_sl:.2f}, P&L={profit_pct:.1f}%)")
            return "trail_sl"


def monitor_stop_loss():
    """Monitor candle-based SL, profit target, max loss, and exit time (5-min candles).
    
    Returns:
        "sl" — candle SL hit or max loss % hit
        "profit" — profit target hit
        "time" — exit time reached
        None — if no entry was done (early return)
    """
    if not entry_done:
        return None

    log(f"Monitoring SL (candle-based) | Target: {TARGET_PCT}% | Max Loss: {MAX_LOSS_PCT}% | Exit: {EXIT_TIME}")

    while True:
        if is_past_time(EXIT_H, EXIT_M):
            place_exit(f"Exit time {EXIT_TIME}")
            return "time"

        wait_secs = get_seconds_to_next_5min_close()
        time.sleep(wait_secs)

        if is_past_time(EXIT_H, EXIT_M):
            place_exit(f"Exit time {EXIT_TIME}")
            return "time"

        # Get current option premium for profit/loss check
        current_option_ltp = None
        profit_pct = 0.0
        if entry_option_price_saved and entry_option_price_saved > 0:
            current_option_ltp = get_option_ltp(option_symbol, option_exchange)
            if current_option_ltp is not None:
                profit_pct = ((current_option_ltp - entry_option_price_saved) / entry_option_price_saved) * 100

        # Check profit target
        if TARGET_PCT > 0 and profit_pct >= TARGET_PCT:
            if TRAIL_GAP > 0:
                # Switch to trailing mode instead of exiting
                log(f"  🎯 TARGET HIT! Profit={profit_pct:.1f}% ≥ {TARGET_PCT}% → switching to trailing SL (gap={TRAIL_GAP} pts)")
                trail_result = trail_after_target(current_option_ltp)
                return trail_result if trail_result else "profit"
            else:
                # No trailing configured — exit immediately at target
                log(f"  🎯 PROFIT TARGET HIT! Option LTP={current_option_ltp}, Entry={entry_option_price_saved}, Profit={profit_pct:.1f}% ≥ {TARGET_PCT}%")
                place_exit(f"Profit Target {profit_pct:.1f}% (target={TARGET_PCT}%)")
                return "profit"

        # Check max loss
        if MAX_LOSS_PCT > 0 and profit_pct <= -MAX_LOSS_PCT:
            log(f"  🛑 MAX LOSS HIT! Option LTP={current_option_ltp}, Entry={entry_option_price_saved}, Loss={profit_pct:.1f}% ≤ -{MAX_LOSS_PCT}%")
            place_exit(f"Max Loss {profit_pct:.1f}% (limit=-{MAX_LOSS_PCT}%)")
            return "sl"

        # Fetch latest 5-min candle close for SL check
        candles = get_latest_5min_candles()
        if candles is None or (hasattr(candles, 'empty') and candles.empty):
            log(f"  ⚠️ No 5-min candle data for SL check, retrying...")
            continue

        latest_close = round(float(candles.iloc[-1]["close"]), 2)
        candle_time = candles.index[-1] if hasattr(candles.index[-1], 'strftime') else "?"

        if check_candle_sl(latest_close, candle_time, profit_pct):
            return "sl"


def monitor_for_flip_entry():
    """After SL hit, monitor for opposite direction breakout (no retracement needed).
    Returns True if flip entry was taken, False if entry window expired."""
    global bias, entry_done, exit_done

    if bias == "BULLISH":
        bias = "BEARISH"
    else:
        bias = "BULLISH"

    log(f"")
    log(f"  🔄 FLIP ENTRY MODE: Looking for {bias} breakout (no retracement needed)")
    if bias == "BULLISH":
        log(f"    Entry trigger: 5-min close > {first_candle_high}")
    else:
        log(f"    Entry trigger: 5-min close < {first_candle_low}")

    while True:
        if is_past_time(ENTRY_END_H, ENTRY_END_M):
            log(f"⏰ Entry window closed ({ENTRY_END}). No flip entry.")
            return False

        wait_secs = get_seconds_to_next_5min_close()
        time.sleep(wait_secs)

        candles = get_latest_5min_candles()
        if candles is None or (hasattr(candles, 'empty') and candles.empty):
            log(f"  ⚠️ No candle data, retrying...")
            continue

        latest = candles.iloc[-1]
        latest_close = round(float(latest["close"]), 2)
        candle_time = candles.index[-1] if hasattr(candles.index[-1], 'strftime') else "?"
        log(f"  Flip [{candle_time}] C={latest_close} | Waiting for {bias} breakout")

        if bias == "BULLISH" and latest_close > first_candle_high:
            log(f"  ✅ FLIP ENTRY CONFIRMED: BULLISH! Close ({latest_close}) > HIGH ({first_candle_high})")
            entry_done = False
            exit_done = False
            place_entry("CE")
            return entry_done

        elif bias == "BEARISH" and latest_close < first_candle_low:
            log(f"  ✅ FLIP ENTRY CONFIRMED: BEARISH! Close ({latest_close}) < LOW ({first_candle_low})")
            entry_done = False
            exit_done = False
            place_entry("PE")
            return entry_done


def main():
    """Main strategy execution with flip-entry support."""
    log(f"")
    log(f"{'='*60}")
    log(f"  5-MIN CANDLE STRATEGY (TC)")
    log(f"  Symbol: {SYMBOL} | Strike: {STRIKE_SELECTION} | Lots: {LOTS}")
    log(f"  Defined Candle: {ENTRY_START} (5-min) | Entry Window: until {ENTRY_END}")
    log(f"  Exit: {EXIT_TIME} | Product: {PRODUCT} | Exchange: {EXCHANGE}")
    log(f"  Target: {TARGET_PCT}% | Max Loss: {MAX_LOSS_PCT}% | Order: {ORDER_TYPE}")
    log(f"  Max Flip Entries: {MAX_FLIP_ENTRIES}")
    log(f"{'='*60}")
    log(f"")

    # Step 1: Wait for market open
    wait_for_time(9, 15, "market open")

    # Step 2: Capture defined 5-min candle
    if not get_first_candle():
        return

    # Step 3: Monitor for initial entry (with retracement)
    monitor_for_entry()

    # Step 4: Trade loop — SL monitoring + flip entries
    sl_count = 0
    cumulative_loss_pct = 0.0  # Track total loss % across all trades today

    while True:
        if entry_done and not exit_done:
            exit_reason = monitor_stop_loss()

        if exit_done:
            # Only attempt flip re-entry on SL-type exits (candle SL or max loss)
            if exit_reason != "sl":
                log(f"  ✅ Exit was due to '{exit_reason}' — no flip re-entry needed. Done for today.")
                break

            # Calculate loss % for this trade and add to cumulative
            if entry_option_price_saved and entry_option_price_saved > 0:
                exit_option_ltp = get_option_ltp(option_symbol, option_exchange)
                if exit_option_ltp is not None:
                    trade_loss_pct = ((exit_option_ltp - entry_option_price_saved) / entry_option_price_saved) * 100
                    cumulative_loss_pct += trade_loss_pct
                    log(f"  📉 Trade loss: {trade_loss_pct:.1f}% | Cumulative day loss: {cumulative_loss_pct:.1f}%")

            sl_count += 1
            log(f"")
            log(f"  📊 Trade exited (SL). Count: {sl_count}/{MAX_FLIP_ENTRIES} | Day Loss: {cumulative_loss_pct:.1f}%")

            # Check if cumulative daily loss exceeds max allowed
            if MAX_LOSS_PCT > 0 and cumulative_loss_pct <= -MAX_LOSS_PCT:
                log(f"  🛑 DAILY MAX LOSS REACHED! Cumulative: {cumulative_loss_pct:.1f}% ≤ -{MAX_LOSS_PCT}%. No more entries.")
                break

            if sl_count >= MAX_FLIP_ENTRIES:
                log(f"  ❌ Max flip entries ({MAX_FLIP_ENTRIES}) reached. Done for today.")
                break

            if is_past_time(ENTRY_END_H, ENTRY_END_M):
                log(f"  ⏰ Entry window closed. No more flip entries.")
                break

            flip_success = monitor_for_flip_entry()
            if not flip_success:
                log(f"  No flip entry taken. Done for today.")
                break
        else:
            break

    # Final forced exit
    if entry_done and not exit_done:
        log(f"  ⚠️ Forced exit: position still open at strategy end!")
        place_exit(f"Strategy end - forced exit at {EXIT_TIME}")

    log(f"\n✅ Strategy complete for today. Trades taken: {sl_count + (1 if entry_done else 0)}")


if __name__ == "__main__":
    main()
