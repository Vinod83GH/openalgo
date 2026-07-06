# Implementation Plan: Paper Trade Journal

## Overview

Implement the Paper Trade Journal as a standalone, broker-agnostic service for structured trade logging during Analyzer mode. Implementation proceeds in layers: database model → service logic → REST API blueprint → app registration → strategy script integration.

## Tasks

- [x] 1. Create the database model and CRUD helpers (`database/paper_trade_db.py`)
  - Define `PaperTrade` SQLAlchemy model with columns: `id` (PK, autoincrement), `created_at` (DateTime, non-nullable, default=func.now()), `trade_date` (Date, nullable), `strategy_name` (String(128), non-nullable), `direction` (String(16), nullable), `entry_time` (DateTime, nullable), `entry_spot_price` (Numeric(18,4), nullable), `entry_option_symbol` (String(64), nullable), `entry_option_price` (Numeric(18,4), nullable), `entry_quantity` (Integer, nullable), `entry_action` (String(8), nullable), `exit_time` (DateTime, nullable), `exit_spot_price` (Numeric(18,4), nullable), `exit_option_price` (Numeric(18,4), nullable), `exit_reason` (String(32), nullable), `pnl` (Numeric(18,4), nullable), `custom_metadata` (Text, nullable)
  - Set up a dedicated `engine`, `db_session`, and `Base` following the same pattern as `database/kill_switch_db.py`
  - Add indexes: `idx_paper_trades_date` on `trade_date`, `idx_paper_trades_strategy` on `strategy_name`, `idx_paper_trades_date_strategy` composite on `(trade_date, strategy_name)`
  - Implement `init_db()` using `init_db_with_logging` helper
  - Implement `create_trade(**fields) -> PaperTrade` — inserts a new trade record with provided fields
  - Implement `get_trade(trade_id: int) -> PaperTrade | None` — fetches a single trade by ID
  - Implement `update_trade(trade_id: int, **fields) -> PaperTrade | None` — updates specified fields on an existing trade, returns None if not found
  - Implement `query_trades(start_date=None, end_date=None, strategy_name=None) -> list[PaperTrade]` — filters by date range and/or strategy, defaults to current date when no filters provided, orders by entry_time descending
  - Implement `get_trade_summary(start_date=None, end_date=None, strategy_name=None) -> dict` — returns aggregated stats: total_trades, total_pnl, winning_trades, losing_trades, win_rate, per_strategy breakdown
  - _Requirements: 1.1, 1.2, 1.3, 1.4, 1.5, 1.6_

  - [ ]* 1.1 Write property test for nullable columns accepting any subset (Property 1)
    - **Property 1: Nullable columns accept any subset of fields**
    - **Validates: Requirement 1.3**
    - Use `@given(fields=st.fixed_dictionaries({}, optional={...}))` with an in-memory SQLite session
    - Assert that `create_trade(**fields)` succeeds and returns a valid PaperTrade with a positive ID

  - [ ]* 1.2 Write property test for custom metadata JSON round-trip (Property 2)
    - **Property 2: Custom metadata JSON round-trip**
    - **Validates: Requirement 1.6, 2.3**
    - Use `@given(metadata=st.dictionaries(keys=st.text(min_size=1, max_size=32), values=st.one_of(st.integers(), st.floats(allow_nan=False), st.text(max_size=64), st.booleans())))` 
    - Create trade with custom_metadata=json.dumps(metadata), read back, deserialize, assert equal

  - [ ]* 1.3 Write property test for unique trade IDs (Property 3)
    - **Property 3: Trade creation returns unique IDs**
    - **Validates: Requirement 2.1, 2.4**
    - Use `@given(num_trades=st.integers(min_value=2, max_value=20))`
    - Create num_trades records, collect all IDs, assert all unique and positive

- [x] 2. Implement the service layer (`services/paper_trade_journal_service.py`)
  - Implement `open_trade(trade_data: dict) -> dict` — validates optional enum fields (direction, entry_action), serializes custom_metadata to JSON string if present, calls `create_trade`, returns `{"status": "success", "data": {"trade_id": id}}`
  - Implement `close_trade(trade_id: int, update_data: dict) -> dict` — fetches trade (returns error dict if not found), merges custom_metadata (shallow merge: `{**existing, **new}`), calculates P&L when entry_option_price + exit_option_price + entry_quantity are all present (BUY: `(exit - entry) × qty`; SELL: `(entry - exit) × qty`), calls `update_trade`, returns updated trade as dict
  - Implement `list_trades(start_date=None, end_date=None, strategy_name=None) -> list[dict]` — delegates to `query_trades`, serializes each PaperTrade to dict (including JSON-deserialized custom_metadata)
  - Implement `get_summary(start_date=None, end_date=None, strategy_name=None) -> dict` — calls `get_trade_summary`, returns formatted summary dict with per_strategy breakdown
  - Implement `get_journal_status() -> dict` — calls `get_analyze_mode()` from `database/settings_db.py`, returns `{"mode": "analyze"|"live", "journal_active": bool}`
  - _Requirements: 2.1, 2.2, 2.3, 2.4, 3.1, 3.2, 3.3, 3.4, 3.5, 3.6, 5.1, 5.2, 5.3, 5.4, 5.5, 8.1, 8.2_

  - [ ]* 2.1 Write property test for P&L calculation — BUY trades (Property 4)
    - **Property 4: P&L calculation correctness for BUY trades**
    - **Validates: Requirement 3.3**
    - Use `@given(entry_price=st.floats(min_value=0.01, max_value=1e5), exit_price=st.floats(min_value=0.01, max_value=1e5), quantity=st.integers(min_value=1, max_value=10000))`
    - Create trade with entry_action="BUY", entry_option_price=entry_price, entry_quantity=quantity
    - Close trade with exit_option_price=exit_price
    - Assert pnl == (exit_price - entry_price) * quantity (within floating point tolerance)

  - [ ]* 2.2 Write property test for P&L calculation — SELL trades (Property 5)
    - **Property 5: P&L calculation correctness for SELL trades**
    - **Validates: Requirement 3.3**
    - Use `@given(entry_price=st.floats(min_value=0.01, max_value=1e5), exit_price=st.floats(min_value=0.01, max_value=1e5), quantity=st.integers(min_value=1, max_value=10000))`
    - Create trade with entry_action="SELL", entry_option_price=entry_price, entry_quantity=quantity
    - Close trade with exit_option_price=exit_price
    - Assert pnl == (entry_price - exit_price) * quantity (within floating point tolerance)

  - [ ]* 2.3 Write property test for P&L NULL when incomplete (Property 6)
    - **Property 6: P&L remains NULL when data is incomplete**
    - **Validates: Requirement 3.3**
    - Use `@given(entry_price=st.one_of(st.none(), st.floats(min_value=0.01)), exit_price=st.one_of(st.none(), st.floats(min_value=0.01)), quantity=st.one_of(st.none(), st.integers(min_value=1)))`
    - `assume(entry_price is None or exit_price is None or quantity is None)`
    - Assert pnl remains None after close_trade

  - [ ]* 2.4 Write property test for metadata shallow merge (Property 7)
    - **Property 7: Custom metadata shallow merge on update**
    - **Validates: Requirement 3.4**
    - Use `@given(existing=st.dictionaries(st.text(min_size=1, max_size=16), st.integers()), update=st.dictionaries(st.text(min_size=1, max_size=16), st.integers()))`
    - Create trade with custom_metadata=existing, close with custom_metadata=update
    - Assert result metadata == {**existing, **update}

  - [ ]* 2.5 Write property test for summary statistics consistency (Property 10)
    - **Property 10: Summary statistics consistency**
    - **Validates: Requirement 5.2**
    - Use `@given(pnl_values=st.lists(st.floats(min_value=-1e5, max_value=1e5, allow_nan=False), min_size=1, max_size=50))`
    - Create trades with each pnl value, call get_summary
    - Assert: winning_trades + losing_trades <= total_trades, total_pnl == sum(pnl_values), win_rate == winning/total_with_pnl * 100

  - [ ]* 2.6 Write property test for strategy name acceptance (Property 11)
    - **Property 11: Strategy name accepts any string**
    - **Validates: Requirement 6.3**
    - Use `@given(strategy_name=st.text(min_size=1, max_size=128))`
    - Assert open_trade with that strategy_name succeeds

- [x] 3. Create the REST API blueprint (`blueprints/paper_journal.py`)
  - Create Flask blueprint `paper_journal_bp` with url_prefix `/api/v1/paperjournal`
  - Implement POST `/trade` route — extract `apikey` from JSON body, validate via `verify_api_key`, call `open_trade`, return 201 on success
  - Implement PATCH `/trade/<int:trade_id>` route — extract `apikey` from JSON body, validate, call `close_trade`, return 200 on success or 404 if not found
  - Implement GET `/trades` route — extract `apikey` from query params, validate, parse `start_date`, `end_date`, `strategy_name` from query params, call `list_trades`, return 200
  - Implement GET `/summary` route — extract `apikey` from query params, validate, parse date/strategy filters, call `get_summary`, return 200
  - Implement GET `/status` route — extract `apikey` from query params, validate, call `get_journal_status`, return 200
  - Handle errors: 401 for invalid API key, 400 for invalid date format, 500 for unexpected errors
  - _Requirements: 2.1, 2.4, 2.5, 3.1, 3.5, 3.6, 4.1, 4.2, 4.3, 4.4, 4.5, 4.6, 4.7, 5.1, 5.2, 5.3, 5.4, 5.5, 6.1, 6.2, 8.1, 8.2, 8.3_

- [x] 4. Register blueprint and initialize database in `app.py`
  - Import `paper_journal_bp` from `blueprints.paper_journal`
  - Register the blueprint with the Flask app
  - Import `init_db` from `database.paper_trade_db` and call it during app initialization (following existing pattern for other db modules)
  - _Requirements: 1.4_

- [x] 5. Integrate Paper Journal client into `first_min_candle_nifty.py`
  - Add `PaperJournalClient` class at the top of the script with methods: `is_active()`, `open_trade(**kwargs)`, `close_trade(trade_id, **kwargs)`
  - `is_active()` calls GET `/api/v1/paperjournal/status?apikey=...` and returns True if mode is "analyze"
  - Initialize the client after API client setup: `journal = PaperJournalClient(api_key=API_KEY, host=HOST)`
  - In `place_entry()`: after successful order placement, if `journal.is_active()`, call `journal.open_trade()` with strategy_name, direction, entry_time, entry_spot_price, entry_option_symbol, entry_quantity, entry_action, and custom_metadata (first_candle_high, first_candle_low, first_candle_close, first_candle_mid, bias)
  - In `place_exit()`: if journal is active and trade_id exists, call `journal.close_trade(trade_id)` with exit_time, exit_spot_price, and exit_reason
  - Store `trade_id` in module-level state variable for use during exit
  - _Requirements: 7.1, 7.2, 7.3, 7.4, 7.5, 8.1, 8.2_

- [x] 6. Write integration tests
  - `test/test_paper_journal_api.py`: end-to-end tests for the full trade lifecycle via REST API
  - Test: create trade → update with exit → query → verify summary stats
  - Test: authentication failure returns 401
  - Test: PATCH non-existent trade returns 404
  - Test: date filtering returns correct subset
  - Test: strategy filtering returns exact matches
  - Test: no-filter query defaults to today's trades
  - Test: summary with no trades returns zeros
  - _Requirements: 2.5, 3.5, 4.6, 5.4, 6.1_

## Notes

- Tasks marked with `*` are optional and can be skipped for faster MVP
- Each task references specific requirements for traceability
- Property tests validate universal correctness properties from the design document
- Unit/integration tests validate specific examples and edge cases
- The database layer follows the same pattern as `database/kill_switch_db.py`
- All REST endpoints use API key authentication via `verify_api_key`
- P&L is auto-calculated server-side only when all required fields (entry_option_price, exit_option_price, entry_quantity) are present

## Task Dependency Graph

```json
{
  "waves": [
    { "id": 0, "tasks": ["1.1", "1.2", "1.3"] },
    { "id": 1, "tasks": ["2.1", "2.2", "2.3", "2.4", "2.5", "2.6"] }
  ]
}
```
