# Implementation Plan: TV Alert Strategies Management

## Overview

Replace the global TV alert options configuration with a per-strategy model. Each TradingView alert maps to a named `TvStrategy` record with independent trading parameters (lot size, strike selection, product, exchange, active days, enabled state). Includes database model, CRUD admin API, endpoint rename, alert processing changes, new React admin pages, and removal of deprecated global settings.

## Tasks

- [x] 1. Create TvStrategy database model and service functions
  - [x] 1.1 Create `database/tv_strategy_db.py` with TvStrategy SQLAlchemy model
    - Define the `TvStrategy` model with columns: id (PK), name (unique, indexed), active_days (comma-separated string, default "Mon,Tue,Wed,Thu,Fri"), lot_size (integer, default 1), strike_selection (string, default "ITM2"), enabled (boolean, default True), product (string, default "MIS"), exchange (string, default "NFO")
    - Set up engine, scoped_session, and Base following the `kill_switch_db.py` pattern
    - Define constants: VALID_EXCHANGES, VALID_PRODUCTS, VALID_STRIKE_SELECTIONS, ALL_WEEKDAYS
    - _Requirements: 1.1, 1.2, 1.3, 1.4, 1.5_

  - [x] 1.2 Implement service functions in `database/tv_strategy_db.py`
    - Implement `init_db()` to create the tv_strategy table
    - Implement `get_strategy_by_name(name)` with TTLCache (60s, maxsize=128)
    - Implement `get_all_strategies()` returning all records ordered by name
    - Implement `create_strategy(name, **fields)` with validation
    - Implement `update_strategy(strategy, **fields)` with cache invalidation
    - Implement `delete_strategy(strategy)` with cache invalidation
    - Implement `_validate_fields(fields)` checking lot_size >= 1, valid exchange, product, strike_selection
    - _Requirements: 1.1, 1.2, 1.3, 1.4, 1.5_

  - [x] 1.3 Register `tv_strategy_db.init_db()` in the application startup
    - Add the init_db call alongside existing database initializations in `app.py`
    - _Requirements: 1.1_

  - [ ]* 1.4 Write property tests for TvStrategy model and service functions
    - **Property 1: Strategy persistence round-trip** — create with valid fields, read back, verify all fields match
    - **Property 2: Name uniqueness enforcement** — creating duplicate names raises error
    - **Property 3: Default field values on creation** — name-only creation yields enabled=True, active_days=all weekdays
    - **Property 4: Lot size validation rejects non-positive values** — lot_size < 1 raises ValueError
    - **Property 5: Invalid enum values rejected** — invalid exchange/product/strike_selection raises ValueError
    - **Validates: Requirements 1.1, 1.2, 1.3, 1.4, 1.5**

- [x] 2. Add CRUD API endpoints to admin blueprint
  - [x] 2.1 Add strategy CRUD endpoints in `blueprints/admin.py`
    - Import `get_all_strategies`, `get_strategy_by_name`, `create_strategy`, `update_strategy`, `delete_strategy` from `database/tv_strategy_db.py`
    - Add GET `/admin/api/tv-strategies` — list all strategies
    - Add GET `/admin/api/tv-strategies/<name>` — get single strategy by name
    - Add POST `/admin/api/tv-strategies` — create strategy (return 201, or 409 on duplicate)
    - Add PUT `/admin/api/tv-strategies/<name>` — update strategy (return 404 if not found)
    - Add DELETE `/admin/api/tv-strategies/<name>` — delete strategy (return 404 if not found)
    - Add `_serialize_strategy(s)` helper converting model to JSON dict (active_days as list)
    - Add `_extract_strategy_fields(data)` helper parsing request body
    - Return HTTP 400 for validation errors (lot_size, exchange, product, strike_selection)
    - _Requirements: 2.1, 2.2, 2.3, 2.4, 2.5, 2.6, 2.7, 2.8, 2.9, 2.10, 2.11_

  - [ ]* 2.2 Write property tests for admin CRUD endpoints
    - **Property 6: Non-existent strategy returns 404** — GET/PUT/DELETE for unknown name returns 404
    - **Property 7: Delete removes strategy** — after DELETE, GET returns 404 and list excludes it
    - **Validates: Requirements 2.5, 2.6, 2.7**

- [x] 3. Checkpoint - Ensure all tests pass
  - Ensure all tests pass, ask the user if questions arise.

- [x] 4. Rename endpoint and update alert processing
  - [x] 4.1 Rename namespace path in `restx_api/__init__.py`
    - Change `api.add_namespace(tv_alert_options_ns, path="/tv-alert-options")` to `api.add_namespace(tv_alert_options_ns, path="/tv-alert-triggers")`
    - The old `/api/v1/tv-alert-options` path will naturally return 404
    - _Requirements: 3.1, 3.2, 3.3_

  - [x] 4.2 Update alert processing in `blueprints/tv_alert_options.py` to use strategy lookup
    - Add `"strategy"` to REQUIRED_FIELDS list
    - Import `get_strategy_by_name` from `database/tv_strategy_db`
    - In `process_tv_alert()`: extract `data["strategy"]`, call `get_strategy_by_name(strategy_name)`
    - Return HTTP 400 with "Unknown strategy: {name}" if strategy not found
    - Return HTTP 200 with disabled message if `strategy.enabled` is False
    - Check current weekday against `strategy.active_days`; return HTTP 200 if day not active
    - Update `resolve_option_symbol()` to accept a `strike_offset` parameter (default "ITM2") and pass it to `get_option_symbol()` instead of hardcoded "ITM2"
    - Update `build_order_data()` to accept `lot_size`, `product` parameters from strategy
    - Remove calls to `get_tv_alert_config()` for quantity/product/exchange/enabled — use strategy record instead
    - Remove the `check_feature_enabled()` call and `check_strategy_active()` call (replaced by TvStrategy gates)
    - _Requirements: 4.1, 4.2, 4.3, 4.4, 4.5, 4.6, 4.7, 4.8, 4.9_

  - [ ]* 4.3 Write property tests for alert processing with strategy lookup
    - **Property 8: Unknown strategy in webhook returns 400** — non-existent strategy name yields 400
    - **Property 9: Disabled strategy rejects alerts gracefully** — enabled=False yields 200 with disabled message
    - **Property 10: Inactive day rejects alerts gracefully** — day not in active_days yields 200
    - **Property 11: Strategy configuration flows into order data** — lot_size, product, exchange match strategy
    - **Property 12: Strike selection flows into option symbol resolution** — strike_offset equals strategy.strike_selection
    - **Validates: Requirements 4.2, 4.3, 4.5, 4.6, 4.7, 4.8, 4.9**

- [x] 5. Checkpoint - Ensure all tests pass
  - Ensure all tests pass, ask the user if questions arise.

- [x] 6. Create frontend admin pages
  - [x] 6.1 Create `frontend/src/pages/admin/TvStrategies.tsx` (list page)
    - Fetch GET `/admin/api/tv-strategies` on mount
    - Display table with columns: Name, Enabled (badge), Active Days, Lot Size, Product, Exchange
    - Each row links to `/admin/tv-strategies/{name}` on click
    - "New Strategy" button navigates to `/admin/tv-strategies/new`
    - Delete button per row with confirmation dialog
    - Follow existing admin page patterns (KillSwitch.tsx, FreezeQty.tsx)
    - _Requirements: 5.1, 5.2, 5.3, 5.4, 5.5_

  - [x] 6.2 Create `frontend/src/pages/admin/TvStrategyEdit.tsx` (edit/create page)
    - If URL param `strategyName === "new"`, render blank creation form (POST on save)
    - Otherwise fetch GET `/admin/api/tv-strategies/{name}` and pre-fill form (PUT on save)
    - Fields: Name (text), Active Days (Mon–Fri checkboxes), Lot Size (numeric, min=1), Strike Selection (dropdown ITM5..OTM5), Enabled (toggle), Product (dropdown MIS/NRML), Exchange (dropdown NFO/BFO/MCX/CDS)
    - Client-side validation: lot_size >= 1 before submit
    - Display API error messages in toast without clearing form
    - Success notification on save, navigate back to list
    - _Requirements: 6.1, 6.2, 6.3, 6.4, 6.5_

  - [x] 6.3 Export new pages from `frontend/src/pages/admin/index.ts`
    - Add exports for TvStrategies and TvStrategyEdit
    - _Requirements: 5.1, 6.1_

- [x] 7. Register routes and remove deprecated code
  - [x] 7.1 Update `frontend/src/App.tsx` router
    - Remove the TvAlertOptions lazy import and its route (`/admin/tv-alert-options`)
    - Add lazy imports for TvStrategies and TvStrategyEdit
    - Add routes: `/admin/tv-strategies` → TvStrategies, `/admin/tv-strategies/:strategyName` → TvStrategyEdit
    - _Requirements: 5.1, 6.1, 7.1_

  - [x] 7.2 Register new React routes in `blueprints/react_app.py`
    - Add route `/admin/tv-strategies` → `serve_react_app()`
    - Add route `/admin/tv-strategies/<strategy_name>` → `serve_react_app()`
    - Remove the `/admin/tv-alert-options` route
    - _Requirements: 5.1, 6.1, 7.1_

  - [x] 7.3 Remove deprecated global TV settings from `blueprints/admin.py`
    - Delete `api_tv_alert_settings_get()` and `api_tv_alert_settings_update()` functions
    - Remove import of `get_tv_alert_config` and `set_tv_alert_config` from `database/settings_db`
    - _Requirements: 7.2, 7.3_

  - [x] 7.4 Delete deprecated frontend page
    - Delete `frontend/src/pages/admin/TvAlertOptions.tsx`
    - Remove its export from `frontend/src/pages/admin/index.ts`
    - _Requirements: 7.1_

- [x] 8. Final checkpoint - Ensure all tests pass
  - Ensure all tests pass, ask the user if questions arise.

## Notes

- Tasks marked with `*` are optional and can be skipped for faster MVP
- Each task references specific requirements for traceability
- Checkpoints ensure incremental validation
- Property tests validate universal correctness properties from the design document
- The project uses Python (Flask) for backend and TypeScript (React) for frontend
- Follow existing patterns: `kill_switch_db.py` for database module, `KillSwitch.tsx` for admin pages
- The `active_days` field is stored as comma-separated string ("Mon,Tue,Wed,Thu,Fri") for SQLite/PostgreSQL compatibility

## Task Dependency Graph

```json
{
  "waves": [
    { "id": 0, "tasks": ["1.1"] },
    { "id": 1, "tasks": ["1.2", "1.3"] },
    { "id": 2, "tasks": ["1.4", "2.1"] },
    { "id": 3, "tasks": ["2.2", "4.1", "4.2"] },
    { "id": 4, "tasks": ["4.3", "6.1", "6.2"] },
    { "id": 5, "tasks": ["6.3", "7.1", "7.2"] },
    { "id": 6, "tasks": ["7.3", "7.4"] }
  ]
}
```
