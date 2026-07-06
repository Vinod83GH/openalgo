# Requirements Document

## Introduction

The Paper Trade Journal is a standalone, broker-agnostic and script-agnostic service that provides structured trade lifecycle logging for Analyzer mode (paper testing). Unlike the existing `analyzer_logs` table which captures raw API request/response data, this journal provides a higher-level, structured trade record with entry/exit lifecycle, P&L calculation, and per-strategy filtering. Any strategy script, API endpoint, or webhook can log trades via REST API endpoints during paper testing sessions.

## Glossary

- **Journal_Service**: The Paper Trade Journal service (`services/paper_trade_journal.py`) that handles trade logging, querying, and summary calculations
- **Journal_Database**: The dedicated database module (`database/paper_trade_db.py`) with its own table separate from existing `analyzer_logs`
- **Trade_Record**: A single structured trade entry in the journal capturing the full lifecycle from entry to exit
- **Strategy_Script**: Any external script (running as a subprocess) that communicates with the app via REST API endpoints
- **Analyzer_Mode**: The paper testing mode detected via `get_analyze_mode()` from `database/settings_db.py`
- **Trade_Direction**: The market bias for a trade — one of BULLISH, BEARISH, or NEUTRAL
- **Exit_Reason**: The reason a trade was closed — one of SL (stop-loss), TARGET, TIME (time-based exit), or MANUAL
- **Custom_Metadata**: A JSON field allowing strategies to store arbitrary extra data (e.g., candle levels, strike selection logic)
- **API_Endpoint**: REST API routes exposed under `/api/v1/paperjournal/` for trade operations

## Requirements

### Requirement 1: Separate Database Table with Nullable Columns

**User Story:** As a developer, I want the paper trade journal to use its own database table with all trade data columns nullable, so that any interface can log only the data it has available without schema enforcement errors.

#### Acceptance Criteria

1. THE Journal_Database SHALL define a `paper_trades` table separate from the existing `analyzer_logs` table
2. THE Journal_Database SHALL use SQLAlchemy with SQLite for development and PostgreSQL for production, following the existing engine pattern used by `kill_switch_db.py`
3. THE Journal_Database SHALL make all trade data columns nullable except for the auto-generated primary key, the creation timestamp, and the strategy_name column which SHALL be non-nullable
4. WHEN the application starts, THE Journal_Database SHALL create the `paper_trades` table if it does not exist using the `init_db_with_logging` helper
5. THE Journal_Database SHALL include columns for: trade_date, strategy_name, direction, entry_time, entry_spot_price, entry_option_symbol, entry_option_price, entry_quantity, entry_action, exit_time, exit_spot_price, exit_option_price, exit_reason, pnl, and custom_metadata
6. THE Journal_Database SHALL store custom_metadata as a JSON-serialized Text column

### Requirement 2: Open a Trade via REST API

**User Story:** As a strategy script author, I want to open a new trade record via a POST request, so that I can log trade entries during paper testing without importing app modules directly.

#### Acceptance Criteria

1. WHEN a POST request is received at `/api/v1/paperjournal/trade` with valid API key authentication, THE Journal_Service SHALL create a new Trade_Record and return the generated trade ID
2. THE Journal_Service SHALL accept the following optional fields in the request body: trade_date, strategy_name, direction, entry_time, entry_spot_price, entry_option_symbol, entry_option_price, entry_quantity, entry_action, and custom_metadata
3. WHEN custom_metadata is provided as a JSON object, THE Journal_Service SHALL serialize and store it in the custom_metadata column
4. WHEN a trade is created successfully, THE API_Endpoint SHALL return HTTP 201 with the response containing the trade ID and status "success"
5. IF the API key is missing or invalid, THEN THE API_Endpoint SHALL return HTTP 401 with an error message

### Requirement 3: Close or Update a Trade via REST API

**User Story:** As a strategy script author, I want to update an existing trade with exit data via a PATCH request, so that I can record trade exits and have P&L calculated automatically.

#### Acceptance Criteria

1. WHEN a PATCH request is received at `/api/v1/paperjournal/trade/<trade_id>` with valid API key authentication, THE Journal_Service SHALL update the specified Trade_Record with the provided exit fields
2. THE Journal_Service SHALL accept the following optional fields for update: exit_time, exit_spot_price, exit_option_price, exit_reason, and custom_metadata
3. WHEN both entry_option_price and exit_option_price are available on a Trade_Record and entry_quantity is set, THE Journal_Service SHALL calculate pnl as: (exit_option_price - entry_option_price) × entry_quantity for BUY entries, or (entry_option_price - exit_option_price) × entry_quantity for SELL entries
4. WHEN custom_metadata is provided in the update request and the Trade_Record already has custom_metadata, THE Journal_Service SHALL merge the new metadata with the existing metadata
5. IF the specified trade_id does not exist, THEN THE API_Endpoint SHALL return HTTP 404 with an error message
6. WHEN a trade is updated successfully, THE API_Endpoint SHALL return HTTP 200 with the updated Trade_Record

### Requirement 4: Query Trades via REST API

**User Story:** As a developer, I want to query trades with date and strategy filters via a GET request, so that I can view per-day trade lists and filter by strategy.

#### Acceptance Criteria

1. WHEN a GET request is received at `/api/v1/paperjournal/trades` with valid API key authentication, THE Journal_Service SHALL return a list of Trade_Records matching the provided filters
2. THE Journal_Service SHALL support filtering by: start_date, end_date, and strategy_name as query parameters
3. WHEN start_date and end_date are both provided, THE Journal_Service SHALL return Trade_Records with trade_date within that range (inclusive)
4. WHEN only start_date is provided, THE Journal_Service SHALL return Trade_Records from that date onward
5. WHEN strategy_name is provided, THE Journal_Service SHALL return only Trade_Records matching that strategy_name
6. WHEN no filters are provided, THE Journal_Service SHALL return Trade_Records for the current date
7. THE Journal_Service SHALL order results by entry_time descending (most recent first)

### Requirement 5: Get Trade Summary and Statistics

**User Story:** As a developer, I want to retrieve summary statistics (total P&L, win/loss count, win rate) for a date range, so that I can evaluate strategy performance during paper testing.

#### Acceptance Criteria

1. WHEN a GET request is received at `/api/v1/paperjournal/summary` with valid API key authentication, THE Journal_Service SHALL return aggregated trade statistics
2. THE Journal_Service SHALL calculate and return: total_trades, total_pnl, winning_trades (pnl > 0), losing_trades (pnl < 0), and win_rate (winning_trades / total_trades with non-null pnl × 100)
3. THE Journal_Service SHALL support filtering the summary by: start_date, end_date, and strategy_name query parameters
4. WHEN no date filters are provided, THE Journal_Service SHALL return summary statistics for the current date
5. THE Journal_Service SHALL also return a per-strategy breakdown with the same statistics grouped by strategy_name

### Requirement 6: Broker-Agnostic and Script-Agnostic Design

**User Story:** As a developer, I want the journal service to work with any strategy script or webhook regardless of the broker being used, so that the journal is a universal paper testing tool.

#### Acceptance Criteria

1. THE Journal_Service SHALL authenticate requests using only the existing API key mechanism without requiring broker-specific credentials
2. THE Journal_Service SHALL accept trades from any source (strategy scripts, webhooks, manual API calls) without requiring a specific caller identity beyond the API key
3. THE Journal_Service SHALL store the strategy_name as a free-form string provided by the caller with no predefined list of valid strategies
4. THE Journal_Database SHALL contain no foreign key references to broker-specific tables

### Requirement 7: Integration with first_min_candle_nifty.py Strategy

**User Story:** As a user running the FirstMinCandle strategy, I want the script to automatically log trades to the paper journal when running in Analyzer mode, so that I get structured trade records without manual logging.

#### Acceptance Criteria

1. WHEN the first_min_candle_nifty.py script detects Analyzer_Mode is active (by querying the application mode via REST API or environment variable), THE Strategy_Script SHALL log trades to the paper journal
2. WHEN an entry order is placed in Analyzer_Mode, THE Strategy_Script SHALL call POST `/api/v1/paperjournal/trade` with: strategy_name, direction, entry_time, entry_spot_price, entry_option_symbol, entry_quantity, and entry_action
3. WHEN a position is exited in Analyzer_Mode, THE Strategy_Script SHALL call PATCH `/api/v1/paperjournal/trade/<trade_id>` with: exit_time, exit_spot_price, exit_option_price (if available), and exit_reason
4. THE Strategy_Script SHALL include custom_metadata containing: first_candle_high, first_candle_low, first_candle_close, first_candle_midpoint, and bias
5. WHILE in live trading mode (Analyzer_Mode is inactive), THE Strategy_Script SHALL skip all paper journal logging

### Requirement 8: Mode Detection for Paper Journal Logging

**User Story:** As a strategy script author, I want a reliable way to detect whether the app is in Analyzer mode, so that paper journal logging only happens during paper testing.

#### Acceptance Criteria

1. THE Journal_Service SHALL provide a GET endpoint at `/api/v1/paperjournal/status` that returns whether the application is currently in Analyzer_Mode
2. WHEN a Strategy_Script queries the status endpoint, THE Journal_Service SHALL return the current mode (analyze or live) so the script can decide whether to log trades
3. THE API_Endpoint SHALL authenticate the status request using the standard API key mechanism
