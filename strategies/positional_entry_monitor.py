# strategies/positional_entry_monitor.py
"""
Entry Window Monitor for Positional Strategy Scripts.

Monitors and manages the entry window for positional strategies:
- Check if current datetime is within the configured entry window
- Determine if candle capture should begin (in window + no defined candle)
- Record confirmed entries (breakout + retracement)
- Handle bias flips during retracement
- Detect entry window expiry

Strategy scripts import this module to get entry window lifecycle management.

Usage in a strategy script:
    from strategies.positional_entry_monitor import EntryWindowMonitor

    monitor = EntryWindowMonitor(
        strategy_id="my_strategy",
        state=current_state,
        state_manager=manager,
    )

    if monitor.is_entry_window_expired():
        monitor.handle_entry_window_expiry()
    elif monitor.is_in_entry_window():
        if monitor.should_capture_candle():
            # execute candle capture logic
            ...
"""

from datetime import datetime

import pytz

from services.positional_state_serializer import StrategyState
from strategies.positional_state_helper import PositionalStateManager
from utils.logging import get_logger

logger = get_logger(__name__)

# IST timezone for all datetime comparisons
IST = pytz.timezone("Asia/Kolkata")


def _now_ist() -> datetime:
    """Get the current datetime in IST timezone."""
    return datetime.now(IST)


def _parse_config_datetime(dt_string: str) -> datetime:
    """Parse a YYYY-MM-DD HH:MM string into an IST-aware datetime.

    Args:
        dt_string: Datetime string in format "YYYY-MM-DD HH:MM".

    Returns:
        Timezone-aware datetime in IST.

    Raises:
        ValueError: If the string cannot be parsed.
    """
    naive = datetime.strptime(dt_string.strip(), "%Y-%m-%d %H:%M")
    return IST.localize(naive)


class EntryWindowMonitor:
    """Monitors and manages the entry window for positional strategies.

    Provides logic for:
    - Checking if the current time is within the entry window
    - Detecting entry window expiry
    - Deciding when candle capture should begin
    - Recording confirmed entries with immediate persistence
    - Handling bias flips during retracement with immediate persistence
    """

    def __init__(
        self,
        strategy_id: str,
        state: StrategyState,
        state_manager: PositionalStateManager,
    ):
        """Initialize with strategy state and state manager for persistence.

        Args:
            strategy_id: Unique identifier for this strategy instance.
            state: Current StrategyState object (mutable, updated in-place on changes).
            state_manager: PositionalStateManager for checkpoint persistence.
        """
        self.strategy_id = strategy_id
        self.state = state
        self.state_manager = state_manager

        # Parse entry window boundaries from config
        config = state.config
        self._entry_start = _parse_config_datetime(
            config["STRATEGY_ENTRY_START_DATE_TIME"]
        )
        self._entry_end = _parse_config_datetime(
            config["STRATEGY_ENTRY_END_DATE_TIME"]
        )

        logger.info(
            f"EntryWindowMonitor: Initialized for strategy '{strategy_id}' "
            f"(window: {self._entry_start} to {self._entry_end})"
        )

    def is_in_entry_window(self) -> bool:
        """Check if current datetime is within the configured entry window.

        Returns True if entry_start <= now <= entry_end (inclusive on both ends).
        Uses IST timezone for comparison.

        Returns:
            True if currently within the entry window, False otherwise.
        """
        now = _now_ist()
        in_window = self._entry_start <= now <= self._entry_end

        logger.debug(
            f"EntryWindowMonitor: is_in_entry_window={in_window} "
            f"(now={now.strftime('%Y-%m-%d %H:%M')}, "
            f"start={self._entry_start.strftime('%Y-%m-%d %H:%M')}, "
            f"end={self._entry_end.strftime('%Y-%m-%d %H:%M')})"
        )
        return in_window

    def is_entry_window_expired(self) -> bool:
        """Check if the entry window has passed without an entry.

        Returns True if current time is past STRATEGY_ENTRY_END_DATE_TIME
        and no entry has been made (entry_done is False).

        Returns:
            True if entry window expired without entry, False otherwise.
        """
        if self.state.entry_done:
            return False

        now = _now_ist()
        expired = now > self._entry_end

        if expired:
            logger.info(
                f"EntryWindowMonitor: Entry window expired for strategy "
                f"'{self.strategy_id}' (end was {self._entry_end.strftime('%Y-%m-%d %H:%M')})"
            )
        return expired

    def handle_entry_window_expiry(self) -> None:
        """Handle entry window expiry: log, set status, stop lifecycle.

        When the entry window expires without an entry:
        1. Logs "entry window expired" with strategy details
        2. Sets the strategy status to "entry_expired" in the config
        3. Persists the updated state immediately

        After calling this, the strategy script should stop its main loop
        and exit cleanly (no further auto-resume will occur).
        """
        logger.info(
            f"EntryWindowMonitor: Entry window expired for strategy "
            f"'{self.strategy_id}' — no entry taken within window "
            f"({self._entry_start.strftime('%Y-%m-%d %H:%M')} to "
            f"{self._entry_end.strftime('%Y-%m-%d %H:%M')}). "
            f"Setting status to 'entry_expired'."
        )

        # Update status in config
        self.state.config["positional_status"] = "entry_expired"

        # Update timestamp
        self.state.timestamp = _now_ist().isoformat()

        # Persist immediately
        self.state_manager.save_checkpoint(self.state)

        logger.info(
            f"EntryWindowMonitor: Strategy '{self.strategy_id}' marked as "
            f"'entry_expired'. Session lifecycle stopped."
        )

    def should_capture_candle(self) -> bool:
        """Check if we should start candle capture (in window, no defined candle yet).

        Candle capture should begin when:
        1. Current time is within the entry window
        2. No first candle has been defined yet (first_candle_high is None)
        3. No entry has been made yet (entry_done is False)

        Returns:
            True if candle capture should be initiated, False otherwise.
        """
        if self.state.entry_done:
            return False

        if self.state.first_candle_high is not None:
            # Candle already captured
            return False

        in_window = self.is_in_entry_window()

        if in_window:
            logger.debug(
                f"EntryWindowMonitor: Should capture candle for strategy "
                f"'{self.strategy_id}' (in window, no defined candle)"
            )
        return in_window

    def record_entry(
        self,
        option_symbol: str,
        option_exchange: str,
        actual_quantity: int,
        entry_price: float,
        journal_trade_id: int | None = None,
    ) -> StrategyState:
        """Record a confirmed entry (breakout + retracement). Persists immediately.

        Updates the state with entry details and saves a checkpoint to the DB
        so that subsequent sessions can monitor the position.

        Args:
            option_symbol: The resolved option contract symbol.
            option_exchange: Exchange for the option (e.g., "NFO").
            actual_quantity: Total quantity entered (lots × lot_size).
            entry_price: The option premium at entry.
            journal_trade_id: Optional paper journal trade ID.

        Returns:
            The updated StrategyState with entry recorded.
        """
        logger.info(
            f"EntryWindowMonitor: Recording entry for strategy '{self.strategy_id}' "
            f"— {option_symbol} qty={actual_quantity} @ ₹{entry_price}"
        )

        # Update state fields
        self.state.entry_done = True
        self.state.option_symbol = option_symbol
        self.state.option_exchange = option_exchange
        self.state.actual_quantity = actual_quantity
        self.state.entry_option_price_saved = entry_price
        self.state.journal_trade_id = journal_trade_id
        self.state.timestamp = _now_ist().isoformat()

        # Persist immediately
        success = self.state_manager.save_checkpoint(self.state)

        if success:
            logger.info(
                f"EntryWindowMonitor: Entry state persisted for strategy "
                f"'{self.strategy_id}' (entry_done=True, symbol={option_symbol})"
            )
        else:
            logger.error(
                f"EntryWindowMonitor: Failed to persist entry state for strategy "
                f"'{self.strategy_id}' — state may be lost on crash!"
            )

        return self.state

    def handle_bias_flip(self, new_bias: str) -> StrategyState:
        """Handle bias flip during retracement: update bias, reset flags, persist.

        When the opposite side breaks out during retracement wait, the bias
        flips direction. This resets retracement tracking and persists the
        change immediately so it survives session boundaries.

        Args:
            new_bias: The new bias direction ("BULLISH" or "BEARISH").

        Returns:
            The updated StrategyState with new bias and reset retracement flags.
        """
        old_bias = self.state.bias

        logger.info(
            f"EntryWindowMonitor: Bias flip for strategy '{self.strategy_id}' "
            f"— {old_bias} → {new_bias}"
        )

        # Update bias
        self.state.bias = new_bias

        # Update timestamp
        self.state.timestamp = _now_ist().isoformat()

        # Persist immediately
        success = self.state_manager.save_checkpoint(self.state)

        if success:
            logger.info(
                f"EntryWindowMonitor: Bias flip persisted for strategy "
                f"'{self.strategy_id}' (bias={new_bias})"
            )
        else:
            logger.error(
                f"EntryWindowMonitor: Failed to persist bias flip for strategy "
                f"'{self.strategy_id}' — state may be inconsistent on crash!"
            )

        return self.state
