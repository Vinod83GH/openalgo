# Implementation Plan: Positional Strategy Hosting

## Overview

Extend the OpenAlgo Python strategy hosting system to support positional (multi-day/multi-week) trading strategies with SQLAlchemy-backed state persistence. Implementation follows a bottom-up approach: database layer → serialization → configuration validation → lifecycle controller → strategy process integration → API endpoint → tests.

## Tasks

- [x] 1. Create database and serialization foundation
  - [x] 1.1 Create PositionalStateDB module (`database/positional_state_db.py`)
    - Define SQLAlchemy model with columns: id (Integer PK), state_key (String 255, unique), state_value (Text 65535), schema_version (Integer), created_at (DateTime), updated_at (DateTime)
    - Implement `create_strategy_table(strategy_id)` for dynamic per-strategy table creation (table name: `positional_state_{strategy_id}`)
    - Implement `save_state(strategy_id, state, schema_version)` with transaction-wrapped atomic write (delete-all + insert-all in one transaction)
    - Implement `load_state(strategy_id)` returning dict of {state_key: state_value} or None
    - Implement `delete_strategy_table(strategy_id)` for cleanup
    - Implement `get_all_strategies_with_state()` returning list of strategy_ids with persisted tables
    - Include retry logic: 3 retries with 2-second intervals on write failure
    - _Requirements: 1.4, 1.5, 1.1, 1.2_

  - [x] 1.2 Create StateSerializer module (`services/positional_state_serializer.py`)
    - Define `StrategyState` dataclass with all fields from design: schema_version, strategy_id, timestamp, candle data (first_candle_high/low/close/mid), trade state (bias, entry_done, exit_done, option_symbol, option_exchange, actual_quantity, entry_option_price_saved, journal_trade_id, sl_count, cumulative_loss_pct, high_watermark, trailing_active), and config dict
    - Implement `serialize_state(state: StrategyState) -> dict[str, str]` with explicit field mapping, float precision to 6 decimal places
    - Implement `deserialize_state(records: dict[str, str], expected_version: int) -> StrategyState` with type preservation (int stays int, bool stays bool, None stays None) and validation for missing/invalid fields
    - Implement `migrate_state(records, from_version, to_version)` for schema version migration
    - Raise validation errors identifying specific invalid fields on deserialization failure
    - _Requirements: 9.1, 9.2, 9.3, 9.4, 9.5, 9.6, 1.7, 1.8_

  - [x]* 1.3 Write property tests for state serialization round-trip
    - **Property 1: State Serialization Round-Trip**
    - **Validates: Requirements 9.2, 9.1, 9.4, 9.5, 1.5, 1.7, 8.2**

  - [x]* 1.4 Write property tests for corrupted state rejection
    - **Property 2: Deserialization Rejects Corrupted State**
    - **Validates: Requirements 1.6, 9.6**

  - [x]* 1.5 Write property test for atomic state writes
    - **Property 13: Atomic State Writes**
    - **Validates: Requirements 8.8**

  - [x]* 1.6 Write property test for schema migration validity
    - **Property 16: Schema Migration Produces Valid State**
    - **Validates: Requirements 1.8**

- [x] 2. Implement configuration validation
  - [x] 2.1 Create PositionalConfigValidator module (`services/positional_config_validator.py`)
    - Implement `validate_positional_config(env_vars: dict) -> tuple[bool, str | None]`
    - Validate datetime format YYYY-MM-DD HH:MM for STRATEGY_ENTRY_START_DATE_TIME, STRATEGY_ENTRY_END_DATE_TIME, STRATEGY_EXIT_DATE_TIME
    - Validate chronological ordering: entry_start < entry_end < exit_dt
    - Validate CANDLE_TIMEFRAME_MIN against allowed set {1, 2, 3, 5, 10, 15, 20, 30, 60}, default to 15 when absent/empty
    - Validate strategy_type is "intraday" or "positional"
    - Default STRATEGY_PRODUCT to "NRML" for positional strategies
    - Return specific error messages identifying which field/constraint failed
    - _Requirements: 2.1, 2.2, 2.3, 2.4, 2.5, 2.6, 2.7, 2.8, 2.9, 2.10_

  - [x]* 2.2 Write property test for datetime format validation
    - **Property 3: Datetime Parsing Validates Format**
    - **Validates: Requirements 2.2, 2.3, 2.4, 2.8**

  - [x]* 2.3 Write property test for chronological ordering
    - **Property 4: Chronological Ordering Validation**
    - **Validates: Requirements 2.7, 2.9**

  - [x]* 2.4 Write property test for candle timeframe allowlist
    - **Property 5: Candle Timeframe Allowlist Validation**
    - **Validates: Requirements 2.5, 2.10**

- [x] 3. Checkpoint - Ensure all tests pass
  - Ensure all tests pass, ask the user if questions arise.

- [x] 4. Implement session lifecycle controller
  - [x] 4.1 Add positional lifecycle scheduling to `blueprints/python_strategy.py`
    - Add `schedule_positional_lifecycle(strategy_id)` to register APScheduler jobs for 9:15 AM IST resume and 3:30 PM IST suspend
    - Add `positional_resume_all()` scheduled function that loads all strategies with persisted state and resumes them
    - Add `positional_suspend_all()` scheduled function that saves state and stops all positional processes
    - Check market calendar (via existing `database/market_calendar_db.py`) before resume — skip holidays/weekends
    - On resume failure (corrupted state, broker issue): set status "error", do NOT exit positions
    - _Requirements: 3.1, 3.2, 3.4, 3.5, 3.6, 3.7, 3.8_

  - [x] 4.2 Implement suspend and resume functions for positional strategies
    - Implement `suspend_positional_strategy(strategy_id)` — send SIGTERM, wait 10s, force-kill if needed, save state to DB
    - Implement `resume_positional_strategy(strategy_id)` — load state from DB, inject into process env, start subprocess
    - On SIGTERM timeout (10s): force-kill, set status "suspended_stale", log warning
    - On market close timeout (60s): force-terminate, save last captured state, set "suspended"
    - On suspension: set status to "suspended" (distinct from "stopped")
    - Integrate fallback file detection on startup: import `strategies/state/{strategy_id}_fallback.json` into DB, delete file
    - On startup with persisted state + no running process: set status "suspended"
    - _Requirements: 3.2, 3.3, 5.1, 5.2, 5.3, 5.4, 5.6, 5.7_

  - [x]* 4.3 Write property test for no exit orders on suspend
    - **Property 6: No Exit Orders on Suspend**
    - **Validates: Requirements 3.5, 4.2, 4.3**

  - [x]* 4.4 Write property test for holiday/weekend skip
    - **Property 7: Skip Resume on Non-Trading Days**
    - **Validates: Requirements 3.6, 3.8**

  - [x]* 4.5 Write property test for entry window datetime check
    - **Property 14: Entry Window Datetime Check**
    - **Validates: Requirements 7.1**

- [x] 5. Implement strategy process state integration
  - [x] 5.1 Add SIGTERM handler and checkpoint logic to strategy process template
    - Create helper module `strategies/positional_state_helper.py` for use by strategy scripts
    - Implement SIGTERM signal handler that serializes state and writes to DB within 10 seconds
    - Implement fallback write to `strategies/state/{strategy_id}_fallback.json` if DB unreachable
    - Implement candle-close checkpoint: save state to DB after each candle completes
    - On startup: read restored state from environment variables injected by Strategy_Host
    - _Requirements: 5.1, 5.5, 5.6, 1.1_

  - [x] 5.2 Implement entry window monitoring logic
    - Check if current datetime is within Entry_Window (STRATEGY_ENTRY_START_DATE_TIME to STRATEGY_ENTRY_END_DATE_TIME)
    - When in window and no defined candle: execute candle capture for configured CANDLE_TIMEFRAME_MIN
    - When entry window spans multiple days with no entry: persist state at market close, continue next day
    - On breakout+retracement entry confirmed: persist entry state (entry_done=true, option_symbol, actual_quantity, entry_option_price_saved) immediately
    - On entry window expiry without entry: log "entry window expired", set status "entry_expired", stop lifecycle
    - On bias flip during retracement: update bias in state, reset retracement flags, persist immediately
    - _Requirements: 7.1, 7.2, 7.3, 7.4, 7.5, 7.6_

  - [x] 5.3 Implement position monitoring and exit logic
    - On resume with entry_done=true, exit_done=false: begin candle-based stop-loss monitoring within 30s
    - Use original first_candle_high/low for SL calculations across all sessions
    - Stop-loss trigger: candle close crosses opposite side of defined candle → place exit order, set exit_done=true
    - Flip re-entry: if sl_count < MAX_FLIP_ENTRIES, flip direction, re-enter opposite, increment counter, persist
    - High watermark tracking: compare each polled LTP against stored highest, update when exceeded
    - Trailing stop-loss activation: when high_watermark exceeds entry_price * (1 + TARGET_PCT/100) and TRAIL_GAP > 0
    - Trailing floor: high_watermark - TRAIL_GAP, never below activation price
    - Trailing exit: when premium drops below floor → place exit, set exit_done=true
    - Time-based exit: at STRATEGY_EXIT_DATE_TIME → force-exit, mark completed
    - Expired option symbol detection: log error, set "requires_manual_review"
    - All state changes written atomically to DB
    - _Requirements: 4.1, 4.4, 4.5, 4.6, 4.7, 8.1, 8.2, 8.3, 8.4, 8.5, 8.6, 8.7, 8.8_

  - [x]* 5.4 Write property test for stop-loss trigger logic
    - **Property 8: Stop-Loss Triggers on Opposite-Side Candle Cross**
    - **Validates: Requirements 4.4, 8.3**

  - [x]* 5.5 Write property test for trailing stop-loss activation
    - **Property 9: Trailing Stop-Loss Activation at Target**
    - **Validates: Requirements 4.5, 8.6**

  - [x]* 5.6 Write property test for trailing stop-loss exit
    - **Property 10: Trailing Stop-Loss Exit on Watermark Drop**
    - **Validates: Requirements 4.6**

  - [x]* 5.7 Write property test for high watermark tracking
    - **Property 11: High Watermark Tracks Running Maximum**
    - **Validates: Requirements 8.5**

  - [x]* 5.8 Write property test for flip re-entry count guard
    - **Property 12: Flip Re-Entry Only When Count Below Maximum**
    - **Validates: Requirements 8.4**

- [x] 6. Checkpoint - Ensure all tests pass
  - Ensure all tests pass, ask the user if questions arise.

- [x] 7. Implement State API endpoint
  - [x] 7.1 Add GET `/python/strategy/<strategy_id>/state` endpoint to `blueprints/python_strategy.py`
    - Return live in-memory state when strategy process is running
    - Return last persisted state from Positional_State_DB when process not running
    - Return `{"status": "no_state", "data": {}}` when no state exists for strategy_id
    - Return 403 error for unauthorized access (user does not own strategy) without revealing strategy existence
    - Response includes: position_status (no_position/position_open/position_closed), entry_price, entry_timestamp, instrument_symbol, quantity, unrealized_pnl (when position_open), last_updated (ISO 8601)
    - Support manual exit command via POST to trigger position exit
    - _Requirements: 6.1, 6.2, 6.3, 6.4, 6.5, 6.6, 4.8_

  - [x]* 7.2 Write property test for state API response schema
    - **Property 15: State API Response Schema**
    - **Validates: Requirements 6.6**

- [x] 8. Integration wiring and startup recovery
  - [x] 8.1 Wire positional lifecycle into strategy start/stop/delete flows
    - Modify `start_strategy_process()` to call config validator for positional strategies before starting
    - Modify `start_strategy_process()` to call `create_strategy_table()` and `schedule_positional_lifecycle()` for positional strategies
    - Modify `stop_strategy_process()` to use `suspend_positional_strategy()` when strategy_type is positional
    - Modify `delete_strategy()` to call `delete_strategy_table()` for cleanup
    - Modify `cleanup_on_exit()` to save state for all positional strategies on app SIGTERM (no exit orders)
    - _Requirements: 2.1, 4.2, 4.3, 3.1, 3.2_

  - [x] 8.2 Implement startup recovery in `restore_strategy_states()`
    - Detect strategies with persisted state but no running process → set "suspended"
    - Detect and import fallback state files → write to DB, delete file
    - Schedule positional lifecycle jobs for all persisted positional strategies
    - _Requirements: 5.4, 5.7, 3.1_

  - [x] 8.3 Create `strategies/state/` directory and ensure it exists on startup
    - Add to `ensure_directories()` function
    - _Requirements: 5.6_

- [x] 9. Write unit and integration tests
  - [x]* 9.1 Write unit tests (`test/test_positional_state_unit.py`)
    - DB retry logic (mock failures for 1, 2, 3, 4 attempts)
    - Fallback file write and recovery
    - Strategy_type validation ("intraday" accepted, "positional" accepted, others rejected)
    - STRATEGY_PRODUCT defaults to NRML for positional
    - Suspend sets "suspended" status (distinct from "stopped")
    - Force-kill after timeout sets "suspended_stale"
    - Startup recovery (persisted state + no process → "suspended")
    - Entry window expiry → "entry_expired"
    - Manual exit via API → exit + "completed"
    - Time-based exit at STRATEGY_EXIT_DATE_TIME
    - API endpoint returns "no_state" for missing strategy
    - API endpoint returns 403 for unauthorized access
    - _Requirements: 1.2, 5.3, 5.4, 5.6, 5.7, 2.1, 2.6, 3.3, 6.4, 6.5, 7.5, 4.7_

  - [x]* 9.2 Write integration tests (`test/test_positional_integration.py`)
    - Full suspend→resume cycle with state verification
    - Market calendar integration (skip holidays)
    - SIGTERM handling in strategy process
    - Fallback file import on startup
    - Multi-day entry window (Day 1 no entry → Day 2 continues)
    - Position monitoring resume with restored candle data
    - _Requirements: 1.1, 1.3, 3.6, 5.1, 5.7, 7.3, 8.1_

- [x] 10. Final checkpoint - Ensure all tests pass
  - Ensure all tests pass, ask the user if questions arise.

## Notes

- Tasks marked with `*` are optional and can be skipped for faster MVP
- Each task references specific requirements for traceability
- Checkpoints ensure incremental validation
- Property tests validate universal correctness properties using Hypothesis (already configured in project)
- Unit tests validate specific examples and edge cases
- All property tests go in `test/test_positional_state_properties.py`
- The existing `database/market_calendar_db.py` is reused for holiday/weekend detection
- Existing APScheduler infrastructure in `python_strategy.py` is extended for positional lifecycle jobs

## Task Dependency Graph

```json
{
  "waves": [
    { "id": 0, "tasks": ["1.1", "1.2", "2.1"] },
    { "id": 1, "tasks": ["1.3", "1.4", "1.5", "1.6", "2.2", "2.3", "2.4"] },
    { "id": 2, "tasks": ["4.1", "4.2", "5.1"] },
    { "id": 3, "tasks": ["4.3", "4.4", "4.5", "5.2", "5.3"] },
    { "id": 4, "tasks": ["5.4", "5.5", "5.6", "5.7", "5.8", "7.1"] },
    { "id": 5, "tasks": ["7.2", "8.1", "8.2", "8.3"] },
    { "id": 6, "tasks": ["9.1", "9.2"] }
  ]
}
```
