#!/usr/bin/env python
"""
Positional Stock Options Strategy (Multi-Day)
==============================================
Strategy Logic (same candle breakout + retracement as TC_5min_nifty, adapted for stocks):
1. Wait for defined candle to close (configurable timeframe via CANDLE_TIMEFRAME_MIN)
2. Mark its High and Low
3. Monitor subsequent candles for breakout:
   - Close ABOVE HIGH (bullish breakout) → wait for retracement + re-test → BUY CALL
   - Close BELOW LOW (bearish breakout) → wait for retracement + re-test → BUY PUT
4. Bias flip: if opposite side breaks during retracement, flip direction
5. Stop-loss: candle close crosses opposite side of defined candle
6. Exit conditions: SL hit, profit target, trailing SL, exit datetime reached, or manual_exit_requested

Key Differences from Intraday (TC_5min_nifty):
- Multi-day entry window (STRATEGY_ENTRY_START_DATE_TIME / END in YYYY-MM-DD HH:MM)
- State persistence via PositionalStateManager (SIGTERM saves state, does NOT exit positions)
- NRML product (positions carried overnight)
- Configurable candle timeframe (CANDLE_TIMEFRAME_MIN env var)
- Monthly last Thursday expiry for stock options
- LIMIT order type default (Zerodha blocks MARKET for stock options)
- manual_exit_requested flag checked on each candle cycle

Configuration (via Environment Variables):
  STRATEGY_SYMBOL                = Stock name (e.g., RELIANCE, TCS, HDFCBANK)
  STRATEGY_STRIKE                = ITM2 (default)
  STRATEGY_LOTS                  = 1 (default)
  STRATEGY_ENTRY_START_DATE_TIME = YYYY-MM-DD HH:MM (entry window start)
  STRATEGY_ENTRY_END_DATE_TIME   = YYYY-MM-DD HH:MM (entry window end)
  STRATEGY_EXIT_DATE_TIME        = YYYY-MM-DD HH:MM (force exit datetime)
  CANDLE_TIMEFRAME_MIN           = 15 (default, candle interval in minutes)
  STRATEGY_PRODUCT               = NRML (default)
  STRATEGY_EXCHANGE              = NFO (default)
  STRATEGY_TARGET_PCT            = 0 (default, disabled)
  STRATEGY_ORDER_TYPE            = LIMIT (default for stocks)
  TRAIL_GAP                      = 0 (default, disabled)
  MAX_FLIP_ENTRIES               = 3 (default)
  STRATEGY_ID                    = (set by Strategy_Host)
"""

import os
import sys
import json
import time
import sys
import requests
from datetime import datetime, timedelta
from pathlib import Path

# Add app root to sys.path so we can import from services/, database/
APP_ROOT = str(Path(__file__).resolve().parent.parent.parent)
if APP_ROOT not in sys.path:
    sys.path.insert(0, APP_ROOT)

from openalgo import api
from strategies.positional_state_helper import PositionalStateManager
from services.positional_state_serializer import StrategyState, CURRENT_SCHEMA_VERSION


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

# Strategy ID (set by Strategy_Host)
STRATEGY_ID = os.getenv("STRATEGY_ID", "")
if not STRATEGY_ID:
    # Derive from script filename (e.g., TC_positional_stocks_20260804214937.py → use as ID)
    STRATEGY_ID = Path(__file__).stem
    log(f"  ℹ️ STRATEGY_ID not set, derived from filename: {STRATEGY_ID}")

# Strategy parameters (configurable from Python Strategy page env vars)
SYMBOL = os.getenv("STRATEGY_SYMBOL", "RELIANCE")
STRIKE_SELECTION = os.getenv("STRATEGY_STRIKE", "ITM2")
LOTS = int(os.getenv("STRATEGY_LOTS", "1"))
PRODUCT = os.getenv("STRATEGY_PRODUCT", "NRML")
EXCHANGE = os.getenv("STRATEGY_EXCHANGE", "NFO")
TARGET_PCT = float(os.getenv("STRATEGY_TARGET_PCT", "0"))
ORDER_TYPE = os.getenv("STRATEGY_ORDER_TYPE", "LIMIT")
RETRACEMENT_BUFFER = float(os.getenv("STRATEGY_RETRACEMENT_BUFFER", "2"))
MAX_LOSS_PCT = float(os.getenv("STRATEGY_MAX_LOSS_PCT", "10"))
MAX_FLIP_ENTRIES = int(os.getenv("STRATEGY_MAX_FLIP_ENTRIES", "3"))
TRAIL_GAP = float(os.getenv("STRATEGY_TRAIL_GAP", "0"))

# Multi-day datetime windows (YYYY-MM-DD HH:MM format)
ENTRY_START_DT_STR = os.getenv("STRATEGY_ENTRY_START_DATE_TIME", "")
ENTRY_END_DT_STR = os.getenv("STRATEGY_ENTRY_END_DATE_TIME", "")
EXIT_DT_STR = os.getenv("STRATEGY_EXIT_DATE_TIME", "")

# Candle timeframe (minutes)
CANDLE_TIMEFRAME_MIN = int(os.getenv("CANDLE_TIMEFRAME_MIN", "15"))

# Derived
STRATEGY_NAME = f"TC_Positional-{SYMBOL}"
SPOT_EXCHANGE = os.getenv("STRATEGY_SPOT_EXCHANGE", "NSE")  # NSE for stocks (not NSE_INDEX)

# Candle interval string for API calls
CANDLE_INTERVAL = f"{CANDLE_TIMEFRAME_MIN}m"
CANDLE_DURATION_SECS = CANDLE_TIMEFRAME_MIN * 60

# Default lot size fallback (used only if API doesn't return lotsize)
DEFAULT_LOT_SIZE = 500


# Parse datetime configs
DT_FORMAT = "%Y-%m-%d %H:%M"

def parse_datetime(dt_str, field_name, required=True):
    """Parse YYYY-MM-DD HH:MM string to datetime object.
    If required=False and dt_str is empty, returns None without error.
    """
    if not dt_str or not dt_str.strip():
        if required:
            print(f"Error: {field_name} is not set")
            exit(1)
        return None
    try:
        return datetime.strptime(dt_str.strip(), DT_FORMAT)
    except ValueError:
        print(f"Error: {field_name} has invalid format: '{dt_str}'. Expected: YYYY-MM-DD HH:MM")
        exit(1)

ENTRY_START_DT = parse_datetime(ENTRY_START_DT_STR, "STRATEGY_ENTRY_START_DATE_TIME", required=True)
ENTRY_END_DT = parse_datetime(ENTRY_END_DT_STR, "STRATEGY_ENTRY_END_DATE_TIME", required=True)
EXIT_DT = parse_datetime(EXIT_DT_STR, "STRATEGY_EXIT_DATE_TIME", required=False)  # Optional — None means no time-based exit

# Validate chronological ordering
if ENTRY_START_DT >= ENTRY_END_DT:
    print(f"Error: ENTRY_START_DATE_TIME ({ENTRY_START_DT_STR}) must be before ENTRY_END_DATE_TIME ({ENTRY_END_DT_STR})")
    exit(1)
if EXIT_DT is not None and ENTRY_END_DT >= EXIT_DT:
    print(f"Error: ENTRY_END_DATE_TIME ({ENTRY_END_DT_STR}) must be before EXIT_DATE_TIME ({EXIT_DT_STR})")
    exit(1)


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
sl_count = 0
cumulative_loss_pct = 0.0
high_watermark = None
trailing_active = False


def log(msg):
    """Print with timestamp."""
    print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] {msg}")


def build_state():
    """Build the current StrategyState for checkpoint/SIGTERM persistence."""
    return StrategyState(
        schema_version=CURRENT_SCHEMA_VERSION,
        strategy_id=STRATEGY_ID,
        timestamp=datetime.now().isoformat(),
        first_candle_high=first_candle_high,
        first_candle_low=first_candle_low,
        first_candle_close=first_candle_close,
        first_candle_mid=first_candle_mid,
        bias=bias,
        entry_done=entry_done,
        exit_done=exit_done,
        option_symbol=option_symbol,
        option_exchange=option_exchange,
        actual_quantity=actual_quantity,
        entry_option_price_saved=entry_option_price_saved,
        journal_trade_id=journal_trade_id,
        sl_count=sl_count,
        cumulative_loss_pct=cumulative_loss_pct,
        high_watermark=high_watermark,
        trailing_active=trailing_active,
        config={
            "STRATEGY_SYMBOL": SYMBOL,
            "STRATEGY_STRIKE": STRIKE_SELECTION,
            "STRATEGY_LOTS": LOTS,
            "STRATEGY_PRODUCT": PRODUCT,
            "STRATEGY_EXCHANGE": EXCHANGE,
            "STRATEGY_TARGET_PCT": TARGET_PCT,
            "STRATEGY_ORDER_TYPE": ORDER_TYPE,
            "CANDLE_TIMEFRAME_MIN": CANDLE_TIMEFRAME_MIN,
            "STRATEGY_ENTRY_START_DATE_TIME": ENTRY_START_DT_STR,
            "STRATEGY_ENTRY_END_DATE_TIME": ENTRY_END_DT_STR,
            "STRATEGY_EXIT_DATE_TIME": EXIT_DT_STR,
            "TRAIL_GAP": TRAIL_GAP,
            "MAX_FLIP_ENTRIES": MAX_FLIP_ENTRIES,
        },
    )


def restore_state_from(state):
    """Restore global state variables from a deserialized StrategyState."""
    global first_candle_high, first_candle_low, first_candle_close, first_candle_mid
    global bias, entry_done, exit_done, option_symbol, option_exchange
    global actual_quantity, entry_option_price_saved, journal_trade_id
    global sl_count, cumulative_loss_pct, high_watermark, trailing_active

    first_candle_high = state.first_candle_high
    first_candle_low = state.first_candle_low
    first_candle_close = state.first_candle_close
    first_candle_mid = state.first_candle_mid
    bias = state.bias
    entry_done = state.entry_done
    exit_done = state.exit_done
    option_symbol = state.option_symbol
    option_exchange = state.option_exchange
    actual_quantity = state.actual_quantity
    entry_option_price_saved = state.entry_option_price_saved
    journal_trade_id = state.journal_trade_id
    sl_count = state.sl_count
    cumulative_loss_pct = state.cumulative_loss_pct
    high_watermark = state.high_watermark
    trailing_active = state.trailing_active

    log(f"  ✅ State restored: entry_done={entry_done}, exit_done={exit_done}, "
        f"bias={bias}, option={option_symbol}, sl_count={sl_count}")


# ============================================================
# EXPIRY CALCULATION — Monthly last Thursday for stocks
# ============================================================


# ============================================================
# HELPER FUNCTIONS
# ============================================================

def is_past_datetime(target_dt: datetime) -> bool:
    """Check if current time is past the given datetime."""
    return datetime.now() >= target_dt


def get_seconds_to_next_candle_close():
    """Calculate seconds until the next candle of CANDLE_TIMEFRAME_MIN closes (+ 5s buffer)."""
    now = datetime.now()
    interval = CANDLE_TIMEFRAME_MIN
    current_minute = now.hour * 60 + now.minute
    # Candles align to clock based on interval from 00:00
    next_candle_minute = ((current_minute // interval) + 1) * interval
    next_candle_hour = next_candle_minute // 60
    next_candle_min = next_candle_minute % 60

    if next_candle_hour >= 24:
        # Next candle is tomorrow at 00:00
        target = (now + timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)
    else:
        target = now.replace(hour=next_candle_hour, minute=next_candle_min, second=0, microsecond=0)

    wait_secs = (target - now).total_seconds() + 5  # 5s buffer for candle to form
    return max(wait_secs, 5)


def wait_until_datetime(target_dt: datetime, label: str = ""):
    """Wait until the specified datetime, sleeping in intervals."""
    while True:
        now = datetime.now()
        if now >= target_dt:
            return
        wait_secs = (target_dt - now).total_seconds()
        if wait_secs > 60:
            log(f"Waiting {wait_secs:.0f}s for {label} ({target_dt.strftime(DT_FORMAT)})...")
        time.sleep(min(wait_secs, 30))


def check_manual_exit_requested() -> bool:
    """Check the DB state for manual_exit_requested flag set by the UI.

    The Strategy Host UI writes this flag to the positional state table
    when the user requests a manual exit.
    """
    try:
        from database.positional_state_db import load_state
        raw_state = load_state(STRATEGY_ID)
        if raw_state and "manual_exit_requested" in raw_state:
            flag = json.loads(raw_state["manual_exit_requested"])
            if flag is True:
                log(f"  🚨 Manual exit requested via UI!")
                return True
    except Exception as e:
        log(f"  ⚠️ Error checking manual_exit flag: {e}")
    return False


def resolve_option_symbol(option_type, spot_ltp):
    """Use the /api/v1/optionsymbol API to resolve the correct option contract.
    
    The API automatically resolves the nearest available expiry from the 
    master contract database — no need to calculate expiry manually.
    """
    url = f"{HOST}/api/v1/optionsymbol"
    payload = {
        "apikey": API_KEY,
        "underlying": SYMBOL,
        "exchange": SPOT_EXCHANGE,
        "offset": STRIKE_SELECTION,
        "option_type": option_type,
    }

    log(f"Resolving option: {SYMBOL} {option_type} {STRIKE_SELECTION} (LTP={spot_ltp})...")

    try:
        resp = requests.post(url, json=payload, timeout=10)
        data = resp.json()

        if data.get("status") == "success":
            sym = data.get("symbol")
            exch = data.get("exchange", EXCHANGE)
            lotsize = data.get("lotsize", DEFAULT_LOT_SIZE)
            log(f"  ✅ Resolved: {sym} on {exch} (lot={lotsize})")
            return sym, exch, int(lotsize)
        else:
            log(f"  ❌ Resolution failed: {data.get('message', 'Unknown error')}")
            return None, None, None
    except Exception as e:
        log(f"  ❌ API error: {e}")
        return None, None, None


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


def get_latest_candles():
    """Fetch today's candles at the configured timeframe."""
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


def get_first_candle():
    """Capture the defined candle after it closes (first candle of entry window)."""
    global first_candle_high, first_candle_low, first_candle_close, first_candle_mid

    # Calculate when the candle closes (ENTRY_START + CANDLE_TIMEFRAME_MIN)
    candle_close_dt = ENTRY_START_DT + timedelta(minutes=CANDLE_TIMEFRAME_MIN)

    log(f"Waiting for {CANDLE_TIMEFRAME_MIN}-min candle to close "
        f"({ENTRY_START_DT.strftime(DT_FORMAT)} - {candle_close_dt.strftime(DT_FORMAT)})...")
    wait_until_datetime(candle_close_dt, f"{CANDLE_TIMEFRAME_MIN}-min candle close")

    # Extra 5 seconds to ensure candle is fully formed
    time.sleep(5)

    # Fetch candle data
    end_date = datetime.now().strftime("%Y-%m-%d")
    start_date = ENTRY_START_DT.strftime("%Y-%m-%d")

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

            # Get data for the entry start date
            target_date = ENTRY_START_DT.date()
            if hasattr(df, 'index') and hasattr(df.index, 'date'):
                target_data = df[df.index.date == target_date]
            else:
                target_data = df

            if target_data is None or (hasattr(target_data, 'empty') and target_data.empty):
                log(f"  No data for {target_date}, retry {attempt + 1}/5...")
                time.sleep(3)
                continue

            # Find the candle matching entry start time
            candle_open_h = ENTRY_START_DT.hour
            candle_open_m = ENTRY_START_DT.minute
            candle_close_h = candle_close_dt.hour
            candle_close_m = candle_close_dt.minute

            candle = None
            matched_time = None
            for idx in target_data.index:
                candle_dt = idx
                if hasattr(idx, 'hour'):
                    # Match by open time (most common)
                    if candle_dt.hour == candle_open_h and candle_dt.minute == candle_open_m:
                        candle = target_data.loc[idx]
                        matched_time = f"{candle_dt.hour:02d}:{candle_dt.minute:02d}"
                        break
                    # Also try matching by close time (some APIs index by close)
                    if candle_dt.hour == candle_close_h and candle_dt.minute == candle_close_m:
                        candle = target_data.loc[idx]
                        matched_time = f"{candle_dt.hour:02d}:{candle_dt.minute:02d} (close-indexed)"
                        break

            if candle is not None:
                log(f"  ✅ Found candle at index time: {matched_time}")

            if candle is None:
                available_times = []
                for idx in target_data.index[:20]:
                    if hasattr(idx, 'strftime'):
                        available_times.append(idx.strftime('%H:%M'))
                log(f"  ❌ CANDLE NOT FOUND at {candle_open_h:02d}:{candle_open_m:02d}!")
                log(f"  Available candle times: {available_times}")
                log(f"  Aborting strategy.")
                return False

            first_candle_high = round(float(candle["high"]), 2)
            first_candle_low = round(float(candle["low"]), 2)
            first_candle_close = round(float(candle["close"]), 2)
            first_candle_mid = round((first_candle_high + first_candle_low) / 2, 2)

            log(f"")
            log(f"{'='*50}")
            log(f"  DEFINED {CANDLE_TIMEFRAME_MIN}-MIN CANDLE: H={first_candle_high} L={first_candle_low} C={first_candle_close}")
            log(f"  Midpoint: {first_candle_mid}")
            log(f"{'='*50}")
            log(f"  Waiting for breakout ({CANDLE_TIMEFRAME_MIN}-min candle close):")
            log(f"    CALL entry: candle close > {first_candle_high}")
            log(f"    PUT entry:  candle close < {first_candle_low}")
            log(f"    SL (after entry): candle close crosses opposite side")
            log(f"")
            return True

        except Exception as e:
            log(f"  Error: {e}, retry {attempt + 1}/5...")
            time.sleep(3)

    log(f"Failed to capture defined {CANDLE_TIMEFRAME_MIN}-min candle. Aborting.")
    return False


# ============================================================
# ORDER PLACEMENT
# ============================================================

def place_entry(option_type):
    """Resolve option, fetch premium, and place entry order."""
    global entry_done, option_symbol, option_exchange, actual_quantity
    global journal_trade_id, entry_option_price_saved

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

    # Determine order type and price
    price = None
    if ORDER_TYPE == "MARKET":
        price_type = "MARKET"
    elif option_ltp:
        price_type = "LIMIT"
        price = option_ltp
    else:
        log(f"  ⚠️ LIMIT requested but no LTP available, falling back to MARKET")
        price_type = "MARKET"

    log(f"")
    log(f"🚀 ENTRY: BUY {option_symbol} | Qty={actual_quantity} ({LOTS} lots × {lotsize}) "
        f"| {price_type} @ {price if price else 'MKT'}")

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
                        "candle_interval": CANDLE_INTERVAL,
                        "strategy_type": "positional",
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

    price = None
    if ORDER_TYPE == "MARKET":
        price_type = "MARKET"
    elif option_ltp:
        price_type = "LIMIT"
        price = option_ltp
    else:
        log(f"  ⚠️ LIMIT requested but no LTP available for exit, falling back to MARKET")
        price_type = "MARKET"

    log(f"")
    log(f"🛑 EXIT ({reason}): SELL {option_symbol} | Qty={actual_quantity} "
        f"| {price_type} @ {price if price else 'MKT'}")

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


# ============================================================
# BREAKOUT / RETRACEMENT / SL MONITORING
# ============================================================

def check_retracement(latest_close, latest_high, latest_low, retraced, candle_time):
    """Check retracement and re-test conditions for the current candle."""
    if bias == "BULLISH":
        if not retraced and latest_low <= first_candle_high + RETRACEMENT_BUFFER:
            log(f"  📉 Retracement detected [{candle_time}] C={latest_close} ≤ HIGH+buf={first_candle_high + RETRACEMENT_BUFFER}")
            if latest_close > first_candle_high:
                log(f"  ✅ STEP 2 CONFIRMED [{candle_time}]: Re-test! L={latest_low} touched HIGH+buf, C={latest_close} > HIGH")
                return True, True, "CE"
            return True, False, None
        if retraced and latest_high >= first_candle_high - RETRACEMENT_BUFFER and latest_close > first_candle_high - RETRACEMENT_BUFFER:
            log(f"  ✅ STEP 2 CONFIRMED [{candle_time}]: Re-test! H={latest_high} touched HIGH-buf, C={latest_close} > HIGH-buf")
            return retraced, True, "CE"
        if retraced:
            log(f"  Candle [{candle_time}] C={latest_close} | Retraced={retraced} | Waiting for re-test above {first_candle_high - RETRACEMENT_BUFFER}")
    elif bias == "BEARISH":
        if not retraced and latest_high >= first_candle_low - RETRACEMENT_BUFFER:
            log(f"  📈 Retracement detected [{candle_time}] C={latest_close} ≥ LOW-buf={first_candle_low - RETRACEMENT_BUFFER}")
            if latest_close < first_candle_low:
                log(f"  ✅ STEP 2 CONFIRMED [{candle_time}]: Re-test! H={latest_high} touched LOW-buf, C={latest_close} < LOW")
                return True, True, "PE"
            return True, False, None
        if retraced and latest_low <= first_candle_low + RETRACEMENT_BUFFER and latest_close < first_candle_low + RETRACEMENT_BUFFER:
            log(f"  ✅ STEP 2 CONFIRMED [{candle_time}]: Re-test! L={latest_low} touched LOW+buf, C={latest_close} < LOW+buf")
            return retraced, True, "PE"
        if retraced:
            log(f"  Candle [{candle_time}] C={latest_close} | Retraced={retraced} | Waiting for re-test below {first_candle_low + RETRACEMENT_BUFFER}")
    return retraced, False, None


def check_bias_flip(latest_close, candle_time):
    """Check if opposite side breaks out during retracement wait — flip bias."""
    global bias
    if bias == "BULLISH" and latest_close < first_candle_low:
        log(f"  🔄 FLIP! [{candle_time}] Close ({latest_close}) < LOW ({first_candle_low}) — switching to BEARISH")
        bias = "BEARISH"
        log(f"STEP 2 (RESET): Now waiting for retracement then candle close < {first_candle_low} to confirm PUT")
        return True
    elif bias == "BEARISH" and latest_close > first_candle_high:
        log(f"  🔄 FLIP! [{candle_time}] Close ({latest_close}) > HIGH ({first_candle_high}) — switching to BULLISH")
        bias = "BULLISH"
        log(f"STEP 2 (RESET): Now waiting for retracement then candle close > {first_candle_high} to confirm CALL")
        return True
    return False


def check_candle_sl(latest_close, candle_time, profit_pct):
    """Check candle-based stop-loss (defined candle HIGH/LOW).
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


def monitor_for_entry(state_manager):
    """Step 1: Monitor candles for breakout — no order placed here."""
    global bias

    log(f"STEP 1: Monitoring for breakout via {CANDLE_TIMEFRAME_MIN}-min candle close "
        f"(until {ENTRY_END_DT.strftime(DT_FORMAT)})...")
    log(f"  BULLISH breakout: candle close > {first_candle_high} (defined candle HIGH)")
    log(f"  BEARISH breakout: candle close < {first_candle_low} (defined candle LOW)")

    while True:
        if is_past_datetime(ENTRY_END_DT):
            log(f"⏰ Entry window closed ({ENTRY_END_DT.strftime(DT_FORMAT)}). No breakout occurred.")
            return

        # Wait for next candle close
        wait_secs = get_seconds_to_next_candle_close()
        log(f"  Waiting {wait_secs:.0f}s for next {CANDLE_TIMEFRAME_MIN}-min candle close...")
        time.sleep(wait_secs)

        # Save checkpoint after each candle
        state_manager.save_checkpoint(build_state())

        # Fetch latest candles
        candles = get_latest_candles()
        if candles is None or (hasattr(candles, 'empty') and candles.empty):
            log(f"  No candle data available, retrying...")
            continue

        latest = candles.iloc[-1]
        latest_close = round(float(latest["close"]), 2)
        candle_time = candles.index[-1] if hasattr(candles.index[-1], 'strftime') else "?"
        log(f"  {CANDLE_TIMEFRAME_MIN}m Candle [{candle_time}] C={latest_close}")

        # Check BULLISH breakout
        if latest_close > first_candle_high:
            bias = "BULLISH"
            log(f"  ✅ STEP 1 CONFIRMED: BULLISH BREAKOUT! Close ({latest_close}) > HIGH ({first_candle_high})")
            log(f"  Now waiting for retracement + re-test...")
            monitor_for_retest(state_manager)
            return

        # Check BEARISH breakout
        elif latest_close < first_candle_low:
            bias = "BEARISH"
            log(f"  ✅ STEP 1 CONFIRMED: BEARISH BREAKOUT! Close ({latest_close}) < LOW ({first_candle_low})")
            log(f"  Now waiting for retracement + re-test...")
            monitor_for_retest(state_manager)
            return


def monitor_for_retest(state_manager):
    """Step 2: After breakout, wait for retracement then re-test on candles."""
    global entry_done, bias

    if bias == "BULLISH":
        log(f"STEP 2: Waiting for retracement then candle close > {first_candle_high} to confirm CALL")
    else:
        log(f"STEP 2: Waiting for retracement then candle close < {first_candle_low} to confirm PUT")

    retraced = False

    while not entry_done:
        if is_past_datetime(ENTRY_END_DT):
            log(f"⏰ Entry window closed ({ENTRY_END_DT.strftime(DT_FORMAT)}). Retracement not confirmed.")
            return

        wait_secs = get_seconds_to_next_candle_close()
        time.sleep(wait_secs)

        # Save checkpoint
        state_manager.save_checkpoint(build_state())

        candles = get_latest_candles()
        if candles is None or (hasattr(candles, 'empty') and candles.empty):
            log(f"  ⚠️ No candle data available, retrying next cycle...")
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


def trail_after_target(activation_premium, state_manager):
    """
    Trailing SL after profit target is hit.
    SL = highest_premium - TRAIL_GAP (never below activation_premium).
    SL only moves up. Exit when premium drops to or below SL.

    Returns exit reason string, or None if exit datetime triggers first.
    """
    global high_watermark, trailing_active

    high_watermark = activation_premium
    trailing_active = True
    trail_sl = activation_premium  # SL starts at activation price

    log(f"  🔄 TRAILING MODE ACTIVATED | Activation: {activation_premium:.2f} | Gap: {TRAIL_GAP} pts")

    while True:
        if EXIT_DT is not None and is_past_datetime(EXIT_DT):
            place_exit(f"Exit datetime {EXIT_DT.strftime(DT_FORMAT)} (trailing)")
            return "time"

        # Check manual exit
        if check_manual_exit_requested():
            place_exit("Manual exit requested (trailing)")
            return "manual"

        time.sleep(5)  # Poll every 5 seconds for trailing

        current_ltp = get_option_ltp(option_symbol, option_exchange)
        if current_ltp is None:
            continue

        # Update high watermark
        if current_ltp > high_watermark:
            high_watermark = current_ltp

        # Compute new SL: highest - gap, but never below activation price
        new_sl = min(high_watermark - TRAIL_GAP, activation_premium)

        # SL only goes up
        if new_sl > trail_sl:
            log(f"  📈 Trail SL updated: {trail_sl:.2f} → {new_sl:.2f} (HWM: {high_watermark:.2f})")
            trail_sl = new_sl

        profit_pct = ((current_ltp - entry_option_price_saved) / entry_option_price_saved) * 100
        log(f"  Trail | LTP: {current_ltp:.2f} | HWM: {high_watermark:.2f} | SL: {trail_sl:.2f} | P&L: {profit_pct:.1f}%")

        # Check if SL hit
        if current_ltp <= trail_sl:
            log(f"  🛑 TRAIL SL HIT! LTP {current_ltp:.2f} <= SL {trail_sl:.2f}")
            place_exit(f"Trail SL hit (LTP={current_ltp:.2f}, SL={trail_sl:.2f}, P&L={profit_pct:.1f}%)")
            return "trail_sl"


def monitor_stop_loss(state_manager):
    """Monitor candle-based SL, profit target, max loss, trailing, exit datetime, and manual exit.

    Returns:
        "sl" — candle SL hit or max loss % hit
        "profit" — profit target hit
        "time" — exit datetime reached
        "manual" — manual exit requested
        None — if no entry was done (early return)
    """
    if not entry_done:
        return None

    log(f"Monitoring SL (candle-based) | Target: {TARGET_PCT}% | Max Loss: {MAX_LOSS_PCT}% "
        f"| Exit: {EXIT_DT.strftime(DT_FORMAT) if EXIT_DT else 'None (no time exit)'}")

    while True:
        # Check exit datetime (only if configured)
        if EXIT_DT is not None and is_past_datetime(EXIT_DT):
            place_exit(f"Exit datetime {EXIT_DT.strftime(DT_FORMAT)}")
            return "time"

        # Check manual exit flag from DB
        if check_manual_exit_requested():
            place_exit("Manual exit requested")
            return "manual"

        # Wait for next candle close
        wait_secs = get_seconds_to_next_candle_close()
        time.sleep(wait_secs)

        # Save checkpoint after each candle
        state_manager.save_checkpoint(build_state())

        # Check exit datetime again after sleep
        if EXIT_DT is not None and is_past_datetime(EXIT_DT):
            place_exit(f"Exit datetime {EXIT_DT.strftime(DT_FORMAT)}")
            return "time"

        # Check manual exit again
        if check_manual_exit_requested():
            place_exit("Manual exit requested")
            return "manual"

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
                trail_result = trail_after_target(current_option_ltp, state_manager)
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

        # Fetch latest candle close for SL check
        candles = get_latest_candles()
        if candles is None or (hasattr(candles, 'empty') and candles.empty):
            log(f"  ⚠️ No candle data for SL check, retrying...")
            continue

        latest_close = round(float(candles.iloc[-1]["close"]), 2)
        candle_time = candles.index[-1] if hasattr(candles.index[-1], 'strftime') else "?"

        if check_candle_sl(latest_close, candle_time, profit_pct):
            return "sl"


def monitor_for_flip_entry(state_manager):
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
        log(f"    Entry trigger: candle close > {first_candle_high}")
    else:
        log(f"    Entry trigger: candle close < {first_candle_low}")

    while True:
        if is_past_datetime(ENTRY_END_DT):
            log(f"⏰ Entry window closed ({ENTRY_END_DT.strftime(DT_FORMAT)}). No flip entry.")
            return False

        wait_secs = get_seconds_to_next_candle_close()
        time.sleep(wait_secs)

        # Save checkpoint
        state_manager.save_checkpoint(build_state())

        candles = get_latest_candles()
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


# ============================================================
# MAIN ENTRY POINT
# ============================================================

def main():
    """Main strategy execution with state persistence and flip-entry support.

    Flow:
    1. Initialize PositionalStateManager
    2. Check for restored state → resume if found
    3. Fresh start: wait for entry window, capture candle, monitor breakout, entry
    4. After entry: monitor SL / target / trailing / exit datetime / manual exit
    5. Support flip re-entries (controlled by MAX_FLIP_ENTRIES)
    """
    global sl_count, cumulative_loss_pct, entry_done, exit_done

    log(f"")
    log(f"{'='*60}")
    log(f"  POSITIONAL STOCK OPTIONS STRATEGY (TC)")
    log(f"  Symbol: {SYMBOL} | Strike: {STRIKE_SELECTION} | Lots: {LOTS}")
    log(f"  Candle Timeframe: {CANDLE_TIMEFRAME_MIN} min")
    log(f"  Entry Window: {ENTRY_START_DT.strftime(DT_FORMAT)} → {ENTRY_END_DT.strftime(DT_FORMAT)}")
    log(f"  Exit Datetime: {EXIT_DT.strftime(DT_FORMAT) if EXIT_DT else 'None (no time-based exit)'}")
    log(f"  Product: {PRODUCT} | Exchange: {EXCHANGE} | Order: {ORDER_TYPE}")
    log(f"  Target: {TARGET_PCT}% | Max Loss: {MAX_LOSS_PCT}% | Trail Gap: {TRAIL_GAP}")
    log(f"  Max Flip Entries: {MAX_FLIP_ENTRIES}")
    log(f"  Strategy ID: {STRATEGY_ID}")
    log(f"{'='*60}")
    log(f"")

    # --- Step 1: Initialize PositionalStateManager ---
    state_manager = PositionalStateManager(strategy_id=STRATEGY_ID)
    state_manager.install_sigterm_handler(get_current_state_fn=build_state)

    # --- Step 2: Check for restored state ---
    restored = state_manager.load_restored_state()

    if restored:
        log(f"")
        log(f"🔄 RESUMING FROM SAVED STATE")
        restore_state_from(restored)

        if exit_done:
            log(f"  Strategy already exited (exit_done=True). Nothing to do.")
            log(f"\n✅ Strategy complete (resumed, already exited).")
            return

        if entry_done:
            # Position is open — skip to SL/target monitoring
            log(f"  Position is OPEN — skipping to SL/target monitoring.")
            # Jump directly to the trade loop (monitoring phase)
        else:
            # Entry not done — resume entry window monitoring
            log(f"  Entry NOT done — resuming entry window monitoring.")
            if first_candle_high is not None:
                # Candle was captured, resume breakout/retest monitoring
                log(f"  Defined candle already captured: H={first_candle_high} L={first_candle_low}")
                monitor_for_entry(state_manager)
            else:
                # Need to capture candle first
                log(f"  Defined candle NOT captured yet — will capture on entry window start.")
                if not is_past_datetime(ENTRY_START_DT):
                    wait_until_datetime(ENTRY_START_DT, "entry window start")
                if not get_first_candle():
                    return
                monitor_for_entry(state_manager)
    else:
        # --- Step 3: Fresh start — normal flow ---
        log(f"  No restored state — fresh start.")

        # Wait for entry window start
        if not is_past_datetime(ENTRY_START_DT):
            wait_until_datetime(ENTRY_START_DT, "entry window start")

        # Capture defined candle
        if not get_first_candle():
            return

        # Save initial checkpoint after candle capture
        state_manager.save_checkpoint(build_state())

        # Monitor for initial entry (with retracement)
        monitor_for_entry(state_manager)

    # --- Step 4: Trade loop — SL monitoring + flip entries ---
    exit_reason = None

    while True:
        if entry_done and not exit_done:
            # Save checkpoint before entering monitoring
            state_manager.save_checkpoint(build_state())
            exit_reason = monitor_stop_loss(state_manager)

        if exit_done:
            # Save checkpoint after exit
            state_manager.save_checkpoint(build_state())

            # Only attempt flip re-entry on SL-type exits (candle SL or max loss)
            if exit_reason != "sl":
                log(f"  ✅ Exit was due to '{exit_reason}' — no flip re-entry needed. Done.")
                break

            # Calculate loss % for this trade and add to cumulative
            if entry_option_price_saved and entry_option_price_saved > 0:
                exit_option_ltp = get_option_ltp(option_symbol, option_exchange)
                if exit_option_ltp is not None:
                    trade_loss_pct = ((exit_option_ltp - entry_option_price_saved) / entry_option_price_saved) * 100
                    cumulative_loss_pct += trade_loss_pct
                    log(f"  📉 Trade loss: {trade_loss_pct:.1f}% | Cumulative loss: {cumulative_loss_pct:.1f}%")

            sl_count += 1
            log(f"")
            log(f"  📊 Trade exited (SL). Count: {sl_count}/{MAX_FLIP_ENTRIES} | Loss: {cumulative_loss_pct:.1f}%")

            # Check if cumulative loss exceeds max allowed
            if MAX_LOSS_PCT > 0 and cumulative_loss_pct <= -MAX_LOSS_PCT:
                log(f"  🛑 MAX LOSS REACHED! Cumulative: {cumulative_loss_pct:.1f}% ≤ -{MAX_LOSS_PCT}%. No more entries.")
                break

            if sl_count >= MAX_FLIP_ENTRIES:
                log(f"  ❌ Max flip entries ({MAX_FLIP_ENTRIES}) reached. Done.")
                break

            if is_past_datetime(ENTRY_END_DT):
                log(f"  ⏰ Entry window closed. No more flip entries.")
                break

            flip_success = monitor_for_flip_entry(state_manager)
            if not flip_success:
                log(f"  No flip entry taken. Done.")
                break
        else:
            break

    # Final forced exit if position still open
    if entry_done and not exit_done:
        log(f"  ⚠️ Forced exit: position still open at strategy end!")
        place_exit("Strategy end - forced exit")

    # Final checkpoint save
    state_manager.save_checkpoint(build_state())

    log(f"\n✅ Strategy complete. Trades taken: {sl_count + (1 if entry_done else 0)}")


if __name__ == "__main__":
    main()
