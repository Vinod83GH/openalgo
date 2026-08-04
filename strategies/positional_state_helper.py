# strategies/positional_state_helper.py
"""
Positional State Helper for Strategy Scripts.

Provides state persistence capabilities for positional strategy processes:
- SIGTERM signal handler that saves state to DB (with file fallback)
- Candle-close checkpoint saves
- Restored state loading from environment variables on startup

Strategy scripts import this module to get automatic state lifecycle management.

Usage in a strategy script:
    from strategies.positional_state_helper import PositionalStateManager

    manager = PositionalStateManager(strategy_id="my_strategy")
    manager.install_sigterm_handler(get_current_state_fn=lambda: build_state())

    # On startup, check for restored state
    restored = manager.load_restored_state()
    if restored:
        # Resume from previous session
        ...

    # After each candle closes
    manager.save_checkpoint(current_state)
"""

import json
import os
import signal
import sys
import threading
from pathlib import Path
from typing import Callable

from utils.logging import get_logger

logger = get_logger(__name__)

# Environment variable name used to inject restored state into the process
RESTORED_STATE_ENV_VAR = "POSITIONAL_RESTORED_STATE"

# Fallback directory relative to project root
FALLBACK_STATE_DIR = Path(__file__).parent / "state"

# Maximum time allowed for SIGTERM handler to complete (seconds)
SIGTERM_TIMEOUT_SECONDS = 10


class PositionalStateManager:
    """Manages state persistence for positional strategy processes.

    Handles:
    - Reading restored state from environment variables on startup
    - Saving checkpoint state to DB after each candle closes
    - Installing a SIGTERM handler that saves state before process exit
    - Fallback file write if DB is unreachable during SIGTERM
    """

    def __init__(self, strategy_id: str):
        """Initialize the state manager for a given strategy.

        Args:
            strategy_id: Unique identifier for this strategy instance.
        """
        self.strategy_id = strategy_id
        self._get_current_state_fn: Callable | None = None
        self._sigterm_received = False
        self._save_lock = threading.Lock()

        logger.info(
            f"PositionalStateHelper: Initialized for strategy '{strategy_id}'"
        )

    def load_restored_state(self):
        """Read restored state from environment variables on process startup.

        The Strategy_Host injects serialized state as a JSON-encoded string in
        the POSITIONAL_RESTORED_STATE environment variable before starting
        the process.

        Returns:
            StrategyState object if restored state was found and valid, None otherwise.
        """
        from services.positional_state_serializer import (
            CURRENT_SCHEMA_VERSION,
            StrategyState,
            deserialize_state,
            StateValidationError,
        )

        raw_state = os.environ.get(RESTORED_STATE_ENV_VAR)
        if not raw_state:
            logger.info(
                f"PositionalStateHelper: No restored state found for strategy "
                f"'{self.strategy_id}' (env var not set)"
            )
            return None

        try:
            # The env var contains a JSON-encoded dict of {state_key: json_value}
            records = json.loads(raw_state)

            if not isinstance(records, dict):
                logger.error(
                    f"PositionalStateHelper: Restored state for '{self.strategy_id}' "
                    f"is not a dict, got {type(records).__name__}"
                )
                return None

            state = deserialize_state(records, expected_version=CURRENT_SCHEMA_VERSION)
            logger.info(
                f"PositionalStateHelper: Restored state loaded for strategy "
                f"'{self.strategy_id}' (schema v{state.schema_version})"
            )
            return state

        except StateValidationError as e:
            logger.error(
                f"PositionalStateHelper: Failed to deserialize restored state for "
                f"'{self.strategy_id}': {e} (invalid fields: {e.invalid_fields})"
            )
            return None
        except json.JSONDecodeError as e:
            logger.error(
                f"PositionalStateHelper: Failed to parse restored state JSON for "
                f"'{self.strategy_id}': {e}"
            )
            return None
        except Exception as e:
            logger.error(
                f"PositionalStateHelper: Unexpected error loading restored state for "
                f"'{self.strategy_id}': {e}"
            )
            return None

    def save_checkpoint(self, state) -> bool:
        """Save state to DB at candle close (periodic checkpoint).

        Called by the strategy script after each candle completes processing.
        Does NOT exit the process.

        Args:
            state: A StrategyState object representing the current strategy state.

        Returns:
            True if state was saved successfully to DB, False otherwise.
        """
        from services.positional_state_serializer import (
            CURRENT_SCHEMA_VERSION,
            serialize_state,
        )
        from database.positional_state_db import save_state, create_strategy_table

        with self._save_lock:
            try:
                # Ensure table exists
                create_strategy_table(self.strategy_id)

                # Serialize state to key-value format
                serialized = serialize_state(state)

                # Write to DB
                success = save_state(
                    self.strategy_id, serialized, CURRENT_SCHEMA_VERSION
                )

                if success:
                    logger.info(
                        f"PositionalStateHelper: Checkpoint saved for strategy "
                        f"'{self.strategy_id}'"
                    )
                else:
                    logger.warning(
                        f"PositionalStateHelper: Checkpoint save failed for strategy "
                        f"'{self.strategy_id}' (DB write returned False)"
                    )
                return success

            except Exception as e:
                logger.error(
                    f"PositionalStateHelper: Checkpoint save error for strategy "
                    f"'{self.strategy_id}': {e}"
                )
                return False

    def install_sigterm_handler(self, get_current_state_fn: Callable) -> None:
        """Install a SIGTERM handler that saves state before process exit.

        The handler will:
        1. Call get_current_state_fn() to get the current StrategyState
        2. Serialize and write it to the DB
        3. If DB write fails, write to a fallback JSON file
        4. Exit the process with code 0

        Args:
            get_current_state_fn: A callable that returns the current StrategyState.
                Must complete quickly (< 2 seconds) as the total SIGTERM handling
                budget is 10 seconds.
        """
        self._get_current_state_fn = get_current_state_fn

        # Install the signal handler
        signal.signal(signal.SIGTERM, self._sigterm_handler)

        logger.info(
            f"PositionalStateHelper: SIGTERM handler installed for strategy "
            f"'{self.strategy_id}'"
        )

    def _sigterm_handler(self, signum, frame) -> None:
        """Handle SIGTERM by saving state with fallback to file.

        Must complete within 10 seconds. Attempts DB write first, falls back
        to file if DB is unreachable.
        """
        if self._sigterm_received:
            # Avoid re-entrant calls
            logger.warning(
                f"PositionalStateHelper: Duplicate SIGTERM received for "
                f"'{self.strategy_id}', ignoring"
            )
            return

        self._sigterm_received = True
        logger.info(
            f"PositionalStateHelper: SIGTERM received for strategy "
            f"'{self.strategy_id}', saving state..."
        )

        try:
            self._save_state_on_sigterm()
        except Exception as e:
            logger.error(
                f"PositionalStateHelper: Unhandled error in SIGTERM handler for "
                f"'{self.strategy_id}': {e}"
            )
        finally:
            logger.info(
                f"PositionalStateHelper: Exiting process for strategy "
                f"'{self.strategy_id}'"
            )
            sys.exit(0)

    def _save_state_on_sigterm(self) -> None:
        """Internal: serialize state and attempt DB write, with file fallback."""
        from services.positional_state_serializer import (
            CURRENT_SCHEMA_VERSION,
            serialize_state,
        )
        from database.positional_state_db import save_state, create_strategy_table

        if self._get_current_state_fn is None:
            logger.error(
                f"PositionalStateHelper: No get_current_state_fn registered for "
                f"'{self.strategy_id}', cannot save state on SIGTERM"
            )
            return

        # Get current state from the strategy
        try:
            state = self._get_current_state_fn()
        except Exception as e:
            logger.error(
                f"PositionalStateHelper: get_current_state_fn() failed for "
                f"'{self.strategy_id}': {e}"
            )
            return

        if state is None:
            logger.warning(
                f"PositionalStateHelper: get_current_state_fn() returned None for "
                f"'{self.strategy_id}', nothing to save"
            )
            return

        # Serialize the state
        try:
            serialized = serialize_state(state)
        except Exception as e:
            logger.error(
                f"PositionalStateHelper: State serialization failed for "
                f"'{self.strategy_id}': {e}"
            )
            return

        # Attempt DB write
        db_success = False
        with self._save_lock:
            try:
                create_strategy_table(self.strategy_id)
                db_success = save_state(
                    self.strategy_id, serialized, CURRENT_SCHEMA_VERSION
                )
            except Exception as e:
                logger.error(
                    f"PositionalStateHelper: DB write failed on SIGTERM for "
                    f"'{self.strategy_id}': {e}"
                )

        if db_success:
            logger.info(
                f"PositionalStateHelper: State saved to DB on SIGTERM for strategy "
                f"'{self.strategy_id}'"
            )
            return

        # Fallback: write to JSON file
        logger.warning(
            f"PositionalStateHelper: DB unreachable on SIGTERM for "
            f"'{self.strategy_id}', writing fallback file"
        )
        self._write_fallback_file(serialized)

    def _write_fallback_file(self, serialized_state: dict) -> bool:
        """Write serialized state to a fallback JSON file.

        File path: strategies/state/{strategy_id}_fallback.json

        Args:
            serialized_state: Dict of {state_key: json_encoded_value} to write.

        Returns:
            True if file was written successfully, False otherwise.
        """
        try:
            # Ensure the state directory exists
            FALLBACK_STATE_DIR.mkdir(parents=True, exist_ok=True)

            fallback_path = FALLBACK_STATE_DIR / f"{self.strategy_id}_fallback.json"

            with open(fallback_path, "w", encoding="utf-8") as f:
                json.dump(serialized_state, f, indent=2)

            logger.info(
                f"PositionalStateHelper: Fallback state written to "
                f"'{fallback_path}' for strategy '{self.strategy_id}'"
            )
            return True

        except Exception as e:
            logger.error(
                f"PositionalStateHelper: Failed to write fallback file for "
                f"'{self.strategy_id}': {e}"
            )
            return False
