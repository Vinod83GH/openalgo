# Requirements Document

## Introduction

This feature extends the OpenAlgo Python strategy hosting system (`python_strategy.py` blueprint) to support positional (multi-day/multi-week) trading strategies for Indian stock markets. The current infrastructure runs strategies as subprocesses that get killed at market close, with all state held in-memory global variables — lost on restart. Positional strategies like TC_15min_Stocks.py need to persist state across overnight periods, weekends, and market holidays using the database (SQLAlchemy), so that a trade entered on Day 1 can be monitored and managed on Day 5 or Day 15 without manual intervention. "Suspended" means paused monitoring only — positions remain open at the broker and are never exited by the hosting system. Trade exits happen exclusively via stop-loss hit, profit target, trailing stop-loss, or manual exit.

## Glossary

- **Strategy_Host**: The Flask blueprint (`python_strategy.py`) responsible for managing strategy lifecycle (start, suspend, resume, schedule, state persistence)
- **Positional_State_DB**: A dedicated SQLAlchemy database table per strategy (table name: positional_state_{strategy_id}) that persists strategy runtime state properties between market sessions
- **Strategy_Process**: A subprocess running a Python trading strategy script, managed by the Strategy_Host
- **Market_Session**: A single trading day window from 9:15 AM to 3:30 PM IST, Monday through Friday, excluding market holidays
- **Positional_Trade**: A trade that spans multiple Market_Sessions, with entry on one day and exit potentially days or weeks later
- **Strategy_State**: The collection of runtime variables that define a strategy's current status — including candle data, bias, entry status, position details, stop-loss levels, and trailing parameters
- **Suspended**: A strategy status meaning monitoring is paused (process not running) but any open position remains active at the broker; the Strategy_Host does not exit positions on suspend
- **Session_Lifecycle**: The automated resume-at-open / suspend-at-close cycle that the Strategy_Host manages for each positional strategy
- **Candle_Timeframe**: The configurable interval (in minutes) for candle data used by a strategy (e.g., 5, 15, 30)
- **State_Schema_Version**: A version identifier in each persisted state record, enabling forward-compatible migrations
- **Entry_Window**: The datetime range (STRATEGY_ENTRY_START_DATE_TIME to STRATEGY_ENTRY_END_DATE_TIME) during which the strategy looks for trade entries across multiple market sessions
- **Exit_Conditions**: The set of conditions under which a position is closed — stop-loss hit, profit target reached, trailing stop-loss triggered, or manual exit command
- **NRML**: Normal product type for positional trades (carried overnight), as opposed to MIS (intraday squared-off at market close)

## Requirements

### Requirement 1: Database-Backed State Persistence

**User Story:** As a positional trader, I want my strategy's runtime state to be automatically saved to the database at market close and restored at market open, so that multi-day trades continue seamlessly without manual intervention.

#### Acceptance Criteria

1. WHEN a positional strategy process is suspended by the Strategy_Host at market close, THE Strategy_Host SHALL serialize the Strategy_State to the Positional_State_DB within 30 seconds and confirm successful write before the process terminates
2. IF the Strategy_Host fails to write Strategy_State to the Positional_State_DB during suspension (due to database unavailability, write error, or timeout), THEN THE Strategy_Host SHALL retry the write up to 3 times with 2-second intervals, and if all retries fail, SHALL log the error, set the strategy status to "state_save_failed", and terminate the process without deleting any previously persisted state
3. WHEN a positional strategy process is resumed by the Strategy_Host at market open, THE Strategy_Host SHALL restore the Strategy_State from the Positional_State_DB and inject it into the Strategy_Process as environment variables or startup parameters before execution begins
4. THE Positional_State_DB SHALL create a separate SQLAlchemy table per strategy_id (table name pattern: positional_state_{strategy_id}) with columns for: id (integer primary key), state_key (string, max 255 characters), state_value (text, max 65535 characters), schema_version (integer), created_at (datetime), updated_at (datetime)
5. WHEN state is persisted, THE Strategy_Host SHALL store each state property as a separate row keyed by state_key within the strategy's dedicated table
6. IF the persisted state records cannot be deserialized (missing required state_keys, state_value cannot be parsed to expected type, or schema_version is null), THEN THE Strategy_Host SHALL log the error with the affected state_keys, set the strategy status to "requires_manual_review", and refuse to auto-start the strategy
7. WHEN state records are written, THE Strategy_Host SHALL include a schema_version field as an integer in each record to enable forward-compatible migrations
8. IF the stored schema_version is lower than the current expected version, THEN THE Strategy_Host SHALL attempt an automated migration, log the migration result (success or failure with affected state_keys), and IF the migration fails, THEN THE Strategy_Host SHALL set the strategy status to "requires_manual_review" and refuse to auto-start the strategy

### Requirement 2: Positional Strategy Configuration

**User Story:** As a positional trader, I want to configure my strategy with multi-day entry windows, exit dates, and per-stock candle timeframes, so that the strategy knows which calendar days to look for entries and when to force-exit positions.

#### Acceptance Criteria

1. THE Strategy_Host SHALL support a strategy_type field in the strategy configuration with valid values limited to "intraday" and "positional"
2. WHEN a strategy is configured as positional, THE Strategy_Host SHALL read STRATEGY_ENTRY_START_DATE_TIME from the strategy environment variables as a full datetime string in the format YYYY-MM-DD HH:MM (24-hour, IST timezone)
3. WHEN a strategy is configured as positional, THE Strategy_Host SHALL read STRATEGY_ENTRY_END_DATE_TIME from the strategy environment variables as a full datetime string in the format YYYY-MM-DD HH:MM (24-hour, IST timezone)
4. WHEN a strategy is configured as positional, THE Strategy_Host SHALL read STRATEGY_EXIT_DATE_TIME from the strategy environment variables as a full datetime string in the format YYYY-MM-DD HH:MM (24-hour, IST timezone)
5. THE Strategy_Host SHALL allow configuration of CANDLE_TIMEFRAME_MIN as a per-strategy environment variable with valid values: 1, 2, 3, 5, 10, 15, 20, 30, 60 and a default of 15 when the variable is absent or empty
6. WHEN a strategy is configured as positional, THE Strategy_Host SHALL default STRATEGY_PRODUCT to "NRML" for positional order placement
7. WHEN a strategy is configured as positional, THE Strategy_Host SHALL validate that STRATEGY_ENTRY_END_DATE_TIME is chronologically after STRATEGY_ENTRY_START_DATE_TIME and that STRATEGY_EXIT_DATE_TIME is chronologically after STRATEGY_ENTRY_END_DATE_TIME
8. IF a positional strategy is started with STRATEGY_ENTRY_START_DATE_TIME, STRATEGY_ENTRY_END_DATE_TIME, or STRATEGY_EXIT_DATE_TIME missing, empty, or not matching the format YYYY-MM-DD HH:MM, THEN THE Strategy_Host SHALL refuse to start the strategy and log an error message indicating which datetime field is invalid
9. IF the chronological ordering validation in criterion 7 fails, THEN THE Strategy_Host SHALL refuse to start the strategy and log an error message indicating the ordering constraint that was violated
10. IF CANDLE_TIMEFRAME_MIN is set to a value not in the allowed list (1, 2, 3, 5, 10, 15, 20, 30, 60), THEN THE Strategy_Host SHALL refuse to start the strategy and log an error message indicating the invalid timeframe value

### Requirement 3: Market-Aware Session Lifecycle

**User Story:** As a positional trader, I want my strategy to automatically resume monitoring at market open and suspend at market close each trading day, so that the strategy only runs during live market hours while positions remain open at the broker.

#### Acceptance Criteria

1. WHEN the market opens at 9:15 AM IST on a trading day, THE Strategy_Host SHALL automatically resume all positional strategies that have persisted state in the Positional_State_DB by loading the last saved state and starting the Strategy_Process within 30 seconds of the market open time
2. WHEN the market closes at 3:30 PM IST, THE Strategy_Host SHALL save the current strategy state to the Positional_State_DB, then stop the Strategy_Process within 60 seconds of initiating shutdown, and set the strategy status to "suspended"
3. IF the Strategy_Process does not terminate within 60 seconds of the shutdown signal at market close, THEN THE Strategy_Host SHALL force-terminate the process, save whatever state was last successfully captured to the Positional_State_DB, and set the strategy status to "suspended"
4. WHILE a positional strategy status is "suspended", THE Strategy_Host SHALL retain the strategy status as "suspended" and display it with a label distinguishable from "stopped", where "stopped" indicates the strategy is finished or manually halted
5. WHILE a positional strategy status is "suspended", THE Strategy_Host SHALL NOT exit any open positions at the broker — positions remain active overnight and across weekends
6. IF the current day is a market holiday or weekend according to the configured Market_Calendar, THEN THE Strategy_Host SHALL skip the auto-resume for positional strategies and retain the suspended status
7. IF auto-resume at market open fails due to corrupted persisted state or broker connectivity failure, THEN THE Strategy_Host SHALL set the strategy status to "error" with a message indicating the failure reason and shall NOT exit any open positions at the broker
8. WHEN the next trading day arrives after a holiday or weekend, THE Strategy_Host SHALL auto-resume the strategy using the last persisted state from the Positional_State_DB, following the same resume behaviour as criterion 1

### Requirement 4: Trade Exit Logic (No Exit on Suspend)

**User Story:** As a positional trader, I want my positions to be exited ONLY when a defined trading condition is met, so that overnight suspensions or system restarts never cause unwanted position closures.

#### Acceptance Criteria

1. THE Strategy_Process SHALL exit a position ONLY when one of these Exit_Conditions occurs: stop-loss hit, profit target reached, trailing stop-loss triggered, manual exit command, or STRATEGY_EXIT_DATE_TIME reached
2. WHEN the Strategy_Host suspends a positional strategy at market close, THE Strategy_Host SHALL NOT send any exit orders to the broker
3. WHEN the Strategy_Host application is shutting down (SIGTERM to main process), THE Strategy_Host SHALL save state to the Positional_State_DB and terminate the Strategy_Process without placing exit orders for positional strategies
4. WHEN a stop-loss is triggered (candle close crosses opposite side of defined candle), THE Strategy_Process SHALL place an exit order and update the state with exit_done = true and persist the updated state to the Positional_State_DB
5. WHEN a profit target is reached (option premium gains exceed STRATEGY_TARGET_PCT) and TRAIL_GAP is configured (value > 0), THE Strategy_Process SHALL activate trailing stop-loss mode rather than exiting immediately
6. WHEN the trailing stop-loss triggers (option premium drops TRAIL_GAP points below high watermark after target activation), THE Strategy_Process SHALL place an exit order and update the state with exit_done = true
7. WHEN the STRATEGY_EXIT_DATE_TIME arrives during any Market_Session, THE Strategy_Process SHALL force-exit the position as a time-based stop and mark the strategy as completed
8. IF a manual exit command is received via the state API, THE Strategy_Process SHALL exit the position immediately and mark the strategy as completed

### Requirement 5: Graceful Suspend with State Save

**User Story:** As a positional trader, I want my strategy state to be reliably saved during both planned suspensions and unexpected shutdowns, so that I never lose track of an active position.

#### Acceptance Criteria

1. WHEN the Strategy_Process receives SIGTERM from the Strategy_Host, THE Strategy_Process SHALL serialize its current Strategy_State and write it to the Positional_State_DB before exiting, completing the save within 10 seconds
2. WHEN the Strategy_Host initiates suspension, THE Strategy_Host SHALL send SIGTERM to the Strategy_Process and wait up to 10 seconds for the process to complete state save and exit
3. IF a Strategy_Process does not exit within 10 seconds after SIGTERM, THEN THE Strategy_Host SHALL force-kill the process, log a warning about potential state staleness, and set the strategy status to "suspended_stale"
4. WHEN the Strategy_Host starts and finds strategies with persisted state in the Positional_State_DB but no running process, THE Strategy_Host SHALL set those strategies to "suspended" status
5. WHEN a candle closes during strategy execution, THE Strategy_Process SHALL save its current state to the Positional_State_DB as a checkpoint, in addition to the final save on SIGTERM
6. IF the Strategy_Process cannot write state to the Positional_State_DB on SIGTERM (database unreachable), THEN THE Strategy_Process SHALL write the state as JSON to a fallback file at strategies/state/{strategy_id}_fallback.json and log the fallback location
7. WHEN the Strategy_Host detects a fallback state file on startup, THE Strategy_Host SHALL import it into the Positional_State_DB and delete the fallback file

### Requirement 6: Positional Strategy State API

**User Story:** As a trader using the web interface, I want to view my positional strategy's current state and position details, so that I can monitor multi-day trades without reading log files.

#### Acceptance Criteria

1. THE Strategy_Host SHALL expose a GET endpoint at /python/strategy/{strategy_id}/state that returns the current Strategy_State as JSON within 5 seconds of receiving the request
2. WHILE the strategy process is running, THE endpoint SHALL query the Strategy_Process for live in-memory state and return the response
3. WHILE the strategy process is not running, THE endpoint SHALL return the last persisted state from the Positional_State_DB
4. IF no state exists for the given strategy_id, THEN THE endpoint SHALL return a JSON response with status field set to "no_state" and an empty data object
5. IF the request lacks a valid session or the authenticated user does not own the specified strategy, THEN THE endpoint SHALL return an error response indicating unauthorized access without revealing whether the strategy exists
6. THE endpoint SHALL include in the response: position status as one of (no_position, position_open, position_closed), entry price, entry timestamp, instrument symbol, quantity, current unrealized P&L as a numeric value when position status is position_open, and last update timestamp in ISO 8601 format

### Requirement 7: Multi-Day Entry Window Monitoring

**User Story:** As a positional trader running a TC candle strategy on stocks, I want the strategy to look for entry candles across multiple days within the configured entry window, so that I don't miss setups that take days to develop.

#### Acceptance Criteria

1. WHEN a positional strategy resumes a session and has no entry yet (entry_done = false), THE Strategy_Process SHALL check if the current datetime is within the configured Entry_Window (between STRATEGY_ENTRY_START_DATE_TIME and STRATEGY_ENTRY_END_DATE_TIME)
2. WHEN the current date is within the Entry_Window and no defined candle exists yet (first_candle_high is null), THE Strategy_Process SHALL execute candle capture logic for the configured CANDLE_TIMEFRAME_MIN on the current trading day at the configured entry time
3. WHEN the Entry_Window spans multiple days and no entry occurs on the current day, THE Strategy_Process SHALL persist its state (including any captured candle data and bias) at market close and continue looking for entries on the next trading day
4. WHEN a breakout and retracement entry is confirmed, THE Strategy_Process SHALL persist the entry state (entry_done = true, option_symbol, actual_quantity, entry_option_price_saved) to the Positional_State_DB immediately so that subsequent sessions can monitor the position
5. IF the STRATEGY_ENTRY_END_DATE_TIME passes without an entry being taken, THEN THE Strategy_Process SHALL log the outcome with reason "entry window expired", set the strategy status to "entry_expired", and stop the session lifecycle (no further auto-resume)
6. WHEN a bias flip occurs during retracement wait (opposite side breaks out), THE Strategy_Process SHALL update the bias in state, reset the retracement tracking flags, and persist the change to the Positional_State_DB immediately

### Requirement 8: Position Monitoring Across Sessions

**User Story:** As a positional trader with an active position, I want stop-loss and trailing-stop monitoring to resume automatically each trading day, so that my position is protected during all market hours.

#### Acceptance Criteria

1. WHEN a positional strategy resumes a session with entry_done = true and exit_done = false, THE Strategy_Process SHALL begin candle-based stop-loss monitoring within 30 seconds of process start using the restored state (first_candle_high, first_candle_low, bias, option_symbol, actual_quantity)
2. WHEN monitoring resumes, THE Strategy_Process SHALL use the same first_candle_high and first_candle_low values from the original entry candle for stop-loss calculations regardless of how many sessions have passed
3. WHEN a candle close crosses the opposite side of the defined candle (bearish close below first_candle_low for a BULLISH trade, or bullish close above first_candle_high for a BEARISH trade), THE Strategy_Process SHALL trigger a stop-loss exit by placing a SELL order for the full actual_quantity
4. IF MAX_FLIP_ENTRIES has not been reached and a stop-loss is triggered, THEN THE Strategy_Process SHALL flip direction (BULLISH to BEARISH or vice versa), re-enter in the opposite direction with a new option symbol, increment the flip counter, and persist the updated state before the next monitoring cycle
5. WHILE a position is active across sessions, THE Strategy_Process SHALL track the high watermark of the option premium by comparing each polled LTP against the stored highest_premium and updating it when the current LTP exceeds the stored value
6. WHEN the high watermark exceeds the entry price by STRATEGY_TARGET_PCT (percentage of entry price), THE Strategy_Process SHALL activate trailing stop-loss mode and set the trailing stop-loss floor to STRATEGY_TRAIL_GAP points below the high watermark, with the floor never dropping below the activation price
7. IF the restored option_symbol no longer exists in the current master contract (e.g., option expired), THEN THE Strategy_Process SHALL log an error indicating the symbol is no longer valid and set the strategy status to "requires_manual_review"
8. WHEN the Strategy_Process persists state after any state change (entry, exit, flip, high watermark update), THE Strategy_Process SHALL write the complete state atomically so that a crash mid-write does not corrupt the persisted data

### Requirement 9: State Serialization Round-Trip

**User Story:** As a developer, I want state serialization and deserialization to be lossless, so that no trading parameters are corrupted during overnight persistence.

#### Acceptance Criteria

1. THE Strategy_Host SHALL serialize Strategy_State as JSON containing: schema_version (integer), strategy_id (string), timestamp (ISO 8601 string), candle_data (first_candle_high, first_candle_low, first_candle_close, first_candle_mid), trade_state (bias, entry_done, exit_done, option_symbol, option_exchange, actual_quantity, entry_option_price_saved, journal_trade_id, sl_count, cumulative_loss_pct, high_watermark, trailing_active), and configuration (all active STRATEGY_* values)
2. THE Strategy_Host SHALL guarantee that serializing a valid Strategy_State to JSON then deserializing from JSON produces a field-by-field equivalent Strategy_State object where each field has the same type and value as the original
3. THE Strategy_Host SHALL use a dedicated serializer module with explicit field mapping rather than generic pickling or dynamic attribute discovery
4. WHEN floating-point values are serialized (candle prices, percentages), THE serializer SHALL preserve precision to at least 6 decimal places to prevent rounding errors in financial calculations
5. WHEN deserializing state, THE serializer SHALL preserve Python types: integers remain integers (not floats), booleans remain booleans (not integers), None remains None (not the string "null"), and strings remain strings
6. IF deserialized JSON is missing required fields or contains unexpected null values for non-nullable fields, THEN THE serializer SHALL raise a validation error identifying the missing or invalid fields rather than silently using defaults
