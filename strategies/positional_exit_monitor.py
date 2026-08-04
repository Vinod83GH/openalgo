# strategies/positional_exit_monitor.py
"""
Position Exit Monitor for Positional Strategy Hosting.

Monitors an active position and handles exits:
- Candle-based stop-loss (opposite side of defined candle)
- Flip re-entry (direction reversal on SL hit)
- High watermark tracking (running maximum of option premium)
- Trailing stop-loss (activated at target, floor never below activation price)
- Time-based forced exit at STRATEGY_EXIT_DATE_TIME
- Expired option symbol detection

All state changes are written atomically to the database via PositionalStateManager.

Usage in a positional strategy script:
    from strategies.positional_exit_monitor import PositionExitMonitor

    monitor = PositionExitMonitor(
        strategy_id="my_strategy",
        state=restored_state,
        state_manager=manager,
        config=strategy_config
    )

    # In the monitoring loop:
    sl_triggered, reason = monitor.check_stop_loss(candle_close)
    if sl_triggered:
        new_state = monitor.handle_stop_loss_exit()
        # Or handle flip re-entry:
        new_state = monitor.handle_flip_reentry()
"""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING
from zoneinfo import ZoneInfo

from utils.logging import get_logger

if TYPE_CHECKING:
    from services.positional_state_serializer import StrategyState
    from strategies.positional_state_helper import PositionalStateManager

logger = get_logger(__name__)

# IST timezone
IST = ZoneInfo("Asia/Kolkata")


class PositionExitMonitor:
    """Monitors an active position and handles exits (SL, trailing SL, time-based, flip re-entry).

    Designed to be used in a positional strategy process after resuming with an
    active position (entry_done=true, exit_done=false).
    """

    def __init__(
        self,
        strategy_id: str,
        state: "StrategyState",
        state_manager: "PositionalStateManager",
        config: dict,
    ):
        """Initialize with current state, state manager, and strategy config.

        Args:
            strategy_id: Unique identifier for this strategy instance.
            state: Current StrategyState with active position data.
            state_manager: PositionalStateManager for persisting state changes.
            config: Strategy configuration dict containing STRATEGY_TARGET_PCT,
                    TRAIL_GAP, MAX_FLIP_ENTRIES, STRATEGY_EXIT_DATE_TIME, etc.
        """
        self.strategy_id = strategy_id
        self.state = state
        self.state_manager = state_manager
        self.config = config

        # Extract config values with defaults
        self._target_pct = float(config.get("STRATEGY_TARGET_PCT", 0))
        self._trail_gap = float(config.get("TRAIL_GAP", 0))
        self._max_flip_entries = int(config.get("MAX_FLIP_ENTRIES", 0))
        self._exit_datetime_str = config.get("STRATEGY_EXIT_DATE_TIME", "")

        # Parse exit datetime
        self._exit_datetime = self._parse_exit_datetime(self._exit_datetime_str)

        # Calculate activation price for trailing SL
        self._activation_price = self._calculate_activation_price()

        logger.info(
            f"PositionExitMonitor: Initialized for strategy '{strategy_id}' | "
            f"bias={state.bias}, entry_price={state.entry_option_price_saved}, "
            f"sl_count={state.sl_count}, trailing_active={state.trailing_active}"
        )

    def _parse_exit_datetime(self, dt_str: str) -> datetime | None:
        """Parse STRATEGY_EXIT_DATE_TIME string to datetime in IST.

        Expected format: YYYY-MM-DD HH:MM
        """
        if not dt_str or not dt_str.strip():
            return None
        try:
            dt = datetime.strptime(dt_str.strip(), "%Y-%m-%d %H:%M")
            return dt.replace(tzinfo=IST)
        except ValueError:
            logger.warning(
                f"PositionExitMonitor: Invalid STRATEGY_EXIT_DATE_TIME format: '{dt_str}'"
            )
            return None

    def _calculate_activation_price(self) -> float:
        """Calculate the trailing SL activation price.

        activation_price = entry_option_price_saved * (1 + STRATEGY_TARGET_PCT / 100)
        """
        entry_price = self.state.entry_option_price_saved
        if entry_price is None or entry_price <= 0:
            return 0.0
        return entry_price * (1 + self._target_pct / 100)

    # ------------------------------------------------------------------
    # STOP-LOSS LOGIC
    # ------------------------------------------------------------------

    def check_stop_loss(self, candle_close: float) -> tuple[bool, str]:
        """Check if candle close triggers stop-loss.

        BULLISH trade: SL triggered when candle close < first_candle_low
        BEARISH trade: SL triggered when candle close > first_candle_high

        Uses ORIGINAL first_candle_high/low values across all sessions.

        Args:
            candle_close: The closing price of the latest candle.

        Returns:
            (triggered: bool, reason: str) - reason is empty string if not triggered.
        """
        bias = self.state.bias
        first_candle_high = self.state.first_candle_high
        first_candle_low = self.state.first_candle_low

        if bias is None or first_candle_high is None or first_candle_low is None:
            return False, ""

        if bias == "BULLISH" and candle_close < first_candle_low:
            reason = (
                f"BULLISH SL hit: candle close {candle_close} < "
                f"first_candle_low {first_candle_low}"
            )
            logger.info(f"PositionExitMonitor: {reason}")
            return True, reason

        if bias == "BEARISH" and candle_close > first_candle_high:
            reason = (
                f"BEARISH SL hit: candle close {candle_close} > "
                f"first_candle_high {first_candle_high}"
            )
            logger.info(f"PositionExitMonitor: {reason}")
            return True, reason

        return False, ""

    def handle_stop_loss_exit(self) -> "StrategyState":
        """Execute stop-loss exit: set exit_done=true, persist state atomically.

        Returns:
            Updated StrategyState with exit_done=True.
        """
        self.state.exit_done = True
        self.state.timestamp = datetime.now(IST).isoformat()

        # Persist atomically
        self.state_manager.save_checkpoint(self.state)

        logger.info(
            f"PositionExitMonitor: Stop-loss exit executed for strategy "
            f"'{self.strategy_id}'"
        )
        return self.state

    # ------------------------------------------------------------------
    # FLIP RE-ENTRY LOGIC
    # ------------------------------------------------------------------

    def handle_flip_reentry(self) -> "StrategyState | None":
        """If sl_count < MAX_FLIP_ENTRIES: flip direction, re-enter, increment counter.

        Flips BULLISH→BEARISH or BEARISH→BULLISH.
        Increments sl_count and persists state immediately.

        Returns:
            Updated StrategyState if flip was executed, None if max flips reached.
        """
        if self.state.sl_count >= self._max_flip_entries:
            logger.info(
                f"PositionExitMonitor: Max flip entries reached "
                f"({self.state.sl_count} >= {self._max_flip_entries}), no re-entry"
            )
            return None

        # Flip direction
        old_bias = self.state.bias
        if old_bias == "BULLISH":
            self.state.bias = "BEARISH"
        elif old_bias == "BEARISH":
            self.state.bias = "BULLISH"
        else:
            logger.error(
                f"PositionExitMonitor: Cannot flip — invalid bias: {old_bias}"
            )
            return None

        # Increment sl_count
        self.state.sl_count += 1

        # Reset exit state for new position
        self.state.exit_done = False
        self.state.entry_done = True

        # Reset trailing state for new position
        self.state.trailing_active = False
        self.state.high_watermark = None

        # Update timestamp
        self.state.timestamp = datetime.now(IST).isoformat()

        # Persist immediately before next monitoring cycle
        self.state_manager.save_checkpoint(self.state)

        logger.info(
            f"PositionExitMonitor: Flip re-entry for strategy '{self.strategy_id}' | "
            f"{old_bias} → {self.state.bias} | sl_count={self.state.sl_count}"
        )
        return self.state

    # ------------------------------------------------------------------
    # HIGH WATERMARK TRACKING
    # ------------------------------------------------------------------

    def update_high_watermark(self, current_ltp: float) -> bool:
        """Update high watermark if current LTP exceeds stored value.

        Tracks the running maximum of the option premium.

        Args:
            current_ltp: Current last traded price of the option.

        Returns:
            True if watermark was updated (new high), False otherwise.
        """
        current_watermark = self.state.high_watermark

        if current_watermark is None or current_ltp > current_watermark:
            self.state.high_watermark = current_ltp
            self.state.timestamp = datetime.now(IST).isoformat()

            # Persist atomically
            self.state_manager.save_checkpoint(self.state)

            logger.debug(
                f"PositionExitMonitor: High watermark updated to {current_ltp} "
                f"(was {current_watermark}) for strategy '{self.strategy_id}'"
            )
            return True

        return False

    # ------------------------------------------------------------------
    # TRAILING STOP-LOSS LOGIC
    # ------------------------------------------------------------------

    def should_activate_trailing(self) -> bool:
        """Check if trailing stop-loss mode should be activated based on high watermark.

        Activation conditions:
        - high_watermark > entry_option_price_saved * (1 + STRATEGY_TARGET_PCT/100)
        - TRAIL_GAP > 0
        - trailing not already active

        Returns:
            True if trailing should be activated.
        """
        if self.state.trailing_active:
            return False

        if self._trail_gap <= 0:
            return False

        high_watermark = self.state.high_watermark
        if high_watermark is None:
            return False

        return high_watermark > self._activation_price

    def activate_trailing(self) -> None:
        """Activate trailing stop-loss mode and persist state.

        Should be called after should_activate_trailing() returns True.
        """
        self.state.trailing_active = True
        self.state.timestamp = datetime.now(IST).isoformat()

        # Persist atomically
        self.state_manager.save_checkpoint(self.state)

        logger.info(
            f"PositionExitMonitor: Trailing SL activated for strategy "
            f"'{self.strategy_id}' | high_watermark={self.state.high_watermark}, "
            f"activation_price={self._activation_price}, trail_gap={self._trail_gap}"
        )

    def get_trailing_floor(self) -> float:
        """Calculate trailing floor: high_watermark - TRAIL_GAP (never below activation price).

        Returns:
            The trailing stop-loss floor value.
        """
        high_watermark = self.state.high_watermark
        if high_watermark is None:
            return self._activation_price

        floor = high_watermark - self._trail_gap

        # Floor never drops below activation price
        if floor < self._activation_price:
            floor = self._activation_price

        return floor

    def check_trailing_stop_loss(self, current_ltp: float) -> tuple[bool, float]:
        """Check if trailing stop-loss should trigger.

        Trailing exit triggers when current_ltp drops below the trailing floor.

        Args:
            current_ltp: Current last traded price of the option.

        Returns:
            (triggered: bool, floor_value: float) - floor is 0.0 if trailing not active.
        """
        if not self.state.trailing_active:
            return False, 0.0

        floor = self.get_trailing_floor()

        if current_ltp < floor:
            logger.info(
                f"PositionExitMonitor: Trailing SL triggered for strategy "
                f"'{self.strategy_id}' | LTP={current_ltp} < floor={floor}"
            )
            return True, floor

        return False, floor

    def handle_trailing_exit(self) -> "StrategyState":
        """Execute trailing stop-loss exit: set exit_done=true, persist state.

        Returns:
            Updated StrategyState with exit_done=True.
        """
        self.state.exit_done = True
        self.state.timestamp = datetime.now(IST).isoformat()

        # Persist atomically
        self.state_manager.save_checkpoint(self.state)

        logger.info(
            f"PositionExitMonitor: Trailing exit executed for strategy "
            f"'{self.strategy_id}' | high_watermark={self.state.high_watermark}, "
            f"floor={self.get_trailing_floor()}"
        )
        return self.state

    # ------------------------------------------------------------------
    # TIME-BASED EXIT
    # ------------------------------------------------------------------

    def check_time_exit(self) -> bool:
        """Check if STRATEGY_EXIT_DATE_TIME has been reached.

        Compares current IST datetime against the configured exit datetime.

        Returns:
            True if time-based exit should trigger.
        """
        if self._exit_datetime is None:
            return False

        now = datetime.now(IST)
        return now >= self._exit_datetime

    def handle_time_exit(self) -> "StrategyState":
        """Force-exit at STRATEGY_EXIT_DATE_TIME, mark completed.

        Sets exit_done=True and updates config with status "completed".

        Returns:
            Updated StrategyState.
        """
        self.state.exit_done = True
        self.state.timestamp = datetime.now(IST).isoformat()

        # Mark as completed in config
        self.state.config["positional_status"] = "completed"

        # Persist atomically
        self.state_manager.save_checkpoint(self.state)

        logger.info(
            f"PositionExitMonitor: Time-based exit executed for strategy "
            f"'{self.strategy_id}' at {self._exit_datetime_str} — marked 'completed'"
        )
        return self.state

    # ------------------------------------------------------------------
    # OPTION VALIDITY CHECK
    # ------------------------------------------------------------------

    def check_option_validity(self) -> bool:
        """Check if option_symbol still exists in the current master contract.

        Queries the SymToken table for an exact symbol + exchange match.
        If symbol is not found (e.g., option expired), logs an error and
        sets the strategy status to "requires_manual_review".

        Returns:
            True if symbol is valid, False if expired/not found.
        """
        option_symbol = self.state.option_symbol
        option_exchange = self.state.option_exchange

        if not option_symbol or not option_exchange:
            logger.warning(
                f"PositionExitMonitor: No option_symbol/exchange set for "
                f"strategy '{self.strategy_id}'"
            )
            return False

        try:
            from database.symbol import SymToken

            result = SymToken.query.filter(
                SymToken.symbol == option_symbol,
                SymToken.exchange == option_exchange,
            ).first()

            if result is not None:
                return True

            # Symbol not found — expired or invalid
            logger.error(
                f"PositionExitMonitor: Option symbol '{option_symbol}' on "
                f"'{option_exchange}' not found in master contract — "
                f"option may have expired. Strategy '{self.strategy_id}' "
                f"set to 'requires_manual_review'"
            )

            self.state.config["positional_status"] = "requires_manual_review"
            self.state.timestamp = datetime.now(IST).isoformat()
            self.state_manager.save_checkpoint(self.state)

            return False

        except Exception as e:
            logger.error(
                f"PositionExitMonitor: Error checking option validity for "
                f"strategy '{self.strategy_id}': {e}"
            )
            return False
