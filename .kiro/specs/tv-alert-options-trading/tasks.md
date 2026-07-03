# Implementation Plan: TV Alert Options Trading

## Overview

This plan implements an automated options trading pipeline triggered by TradingView webhook alerts. The implementation adds a Flask blueprint with a POST endpoint, integrates with existing option symbol resolution and order placement services, adds database configuration fields to the Settings model, and provides an Admin UI section for configuration management.

## Tasks

- [x] 1. Add TV Alert configuration to the Settings model and database layer
  - [x] 1.1 Add TV alert columns to the Settings model in `database/settings_db.py`
    - Add columns: `tv_alert_strategy` (String, default "TV-Alert-Options"), `tv_alert_quantity` (Integer, default 1), `tv_alert_product` (String, default "MIS"), `tv_alert_exchange` (String, default "NFO"), `tv_alert_enabled` (Boolean, default True)
    - Implement `get_tv_alert_config()` function with TTL cache following `get_security_settings()` pattern
    - Implement `set_tv_alert_config()` function with cache invalidation following `set_security_settings()` pattern
    - _Requirements: 6.1, 6.2, 6.3, 6.4, 6.5, 6.6_

  - [x] 1.2 Add Admin API endpoints for TV Alert settings in `blueprints/admin.py`
    - Add `GET /admin/api/tv-alert-settings` endpoint to retrieve current config
    - Add `POST /admin/api/tv-alert-settings` endpoint to update config with validation (quantity > 0, product in MIS/NRML, exchange in NFO/BFO)
    - Use `check_session_validity` decorator following existing admin endpoint pattern
    - _Requirements: 6.1, 6.2, 6.3, 6.4, 6.6_

- [x] 2. Implement the TV Alert Options blueprint core logic
  - [x] 2.1 Create `blueprints/tv_alert_options.py` with payload validation
    - Create blueprint with `tv_alert_options_bp` and Namespace registration
    - Implement `validate_tv_alert_payload(data)` function that checks required fields (cmp, symbol, charttype, signal, option_type, sl, target) and validates enums (signal: BUY/SELL, charttype: SPOT/OPTION, option_type: CE/PE) case-insensitively
    - Return descriptive error messages identifying missing or invalid fields
    - _Requirements: 1.2, 1.3, 1.5, 1.6, 2.1_

  - [ ]* 2.2 Write property test for payload field presence validation
    - **Property 1: Payload field presence validation**
    - Use Hypothesis to generate random subsets of required fields; verify validator returns False and error message contains every missing field name
    - **Validates: Requirements 1.2, 1.3**

  - [ ]* 2.3 Write property test for enum field rejection
    - **Property 2: Enum field rejection**
    - Use Hypothesis to generate random strings (not matching valid enums) and mixed-case valid variants; verify rejection with appropriate error for invalid values and acceptance for valid ones
    - **Validates: Requirements 1.5, 1.6, 2.1**

  - [x] 2.4 Implement authentication and feature gate in the blueprint
    - Implement API key authentication using `get_auth_token_broker(api_key)` from `database/auth_db`
    - Return HTTP 403 with "Invalid API key" on auth failure
    - Check `tv_alert_enabled` from settings config; return HTTP 403 with "TV Alert Options trading is disabled" if disabled
    - _Requirements: 1.1, 1.7, 6.5_

  - [x] 2.5 Implement strategy gate check
    - Implement `check_strategy_active(strategy_name, user_id)` using existing `Strategy` model from `database/strategy_db`
    - If strategy not found or `is_active == False`, return HTTP 200 with `{"status": "ignored", "message": "..."}` (non-error to prevent TradingView retries)
    - _Requirements: 6.4, 6.5_

  - [ ]* 2.6 Write property test for strategy gate
    - **Property 6: Strategy gate blocks inactive strategies**
    - Use Hypothesis to generate random active/inactive states; verify inactive strategies result in ignored response and no order placement call
    - **Validates: Requirements 6.4, 6.5**

- [x] 3. Implement option symbol resolution and order placement
  - [x] 3.1 Implement nearest expiry resolution and ITM2 option symbol resolution
    - Implement `get_nearest_expiry(symbol, exchange)` querying SymToken table for nearest future expiry in DDMMMYY format
    - Implement `resolve_option_symbol(symbol, cmp, option_type, api_key, exchange)` calling `option_symbol_service.get_option_symbol()` with offset "ITM2" and `ltp_override=cmp`
    - For `charttype == "OPTION"`, bypass resolution and use symbol field directly
    - Return descriptive errors on resolution failures (no strikes found, offset out of range, symbol not found)
    - _Requirements: 2.2, 2.3, 2.5, 2.6, 2.7, 2.8_

  - [ ]* 3.2 Write property test for nearest expiry resolution
    - **Property 5: Nearest expiry resolution**
    - Use Hypothesis to generate random lists of dates with a reference "today"; verify the resolver always picks the nearest future expiry
    - **Validates: Requirements 2.6**

  - [x] 3.3 Implement order data construction and placement
    - Implement `build_order_data(api_key, resolved_symbol, signal, sl, target, exchange)` constructing order dict with signal as action, configured quantity/product/exchange, and SL/target fields
    - Call `place_order_service.place_order()` with constructed order data
    - Handle broker bracket order support: if not supported, log warning and place plain MARKET order
    - _Requirements: 3.1, 3.2, 3.3, 3.4, 3.5, 3.6, 3.7, 3.9_

  - [ ]* 3.4 Write property test for signal passthrough as order action
    - **Property 3: Signal passthrough as order action**
    - Use Hypothesis to generate all combinations of signal (BUY/SELL) × option_type (CE/PE); verify order action equals signal value independent of option_type
    - **Validates: Requirements 2.4, 3.2**

  - [ ]* 3.5 Write property test for SL and target preservation
    - **Property 4: SL and target preservation in order data**
    - Use Hypothesis to generate random positive floats for sl/target; verify order data contains exact same sl and target values
    - **Validates: Requirements 3.3, 3.4**

- [x] 4. Checkpoint - Core backend logic complete
  - Ensure all tests pass, ask the user if questions arise.

- [x] 5. Implement logging, event bus integration, and wire the endpoint
  - [x] 5.1 Implement async logging and event bus emission
    - Log incoming alert payload at INFO level on receipt
    - Call `async_log_order("tv_alert_options", request_data, response_data)` via ThreadPoolExecutor for all requests (success and failure)
    - Emit `OrderPlacedEvent` on success with mode, api_type, symbol, exchange, action, quantity, order_id, and request/response data
    - Emit `OrderFailedEvent` on failure with mode, api_type, request data, error message, symbol, and exchange
    - _Requirements: 1.4, 3.8, 4.1, 4.2, 4.3, 4.5, 5.1, 5.2, 5.3_

  - [x] 5.2 Wire the `process_tv_alert` main handler and POST endpoint
    - Implement `process_tv_alert(data)` orchestrating the full flow: auth → validate → feature gate → strategy gate → resolve → build order → place order → log → emit event → respond
    - Register the POST route at `/api/v1/tv-alert-options` on the blueprint Resource class
    - Exempt blueprint from CSRF (API-key authenticated)
    - _Requirements: 1.1, 1.2, 1.4, 4.4_

  - [x] 5.3 Register the blueprint in `app.py`
    - Import and register `tv_alert_options_bp` in the Flask app
    - Add restx namespace for the TV alert API
    - Initialize any required database setup in the app startup sequence
    - _Requirements: 1.1_

  - [ ]* 5.4 Write unit tests for the full endpoint flow
    - Test authentication (valid key, invalid key, missing key)
    - Test feature disabled rejection (tv_alert_enabled=False → 403)
    - Test strategy inactive → 200 ignored response
    - Test OPTION charttype bypass (symbol used directly)
    - Test order placement success path with mocked broker
    - Test order placement failure with event emission verification
    - Test async logging verification
    - _Requirements: 1.1, 1.7, 2.8, 3.8, 4.5, 5.1, 5.2, 6.5_

- [x] 6. Implement Admin UI for TV Alert configuration
  - [x] 6.1 Create `frontend/src/pages/admin/TvAlertOptions.tsx` page component
    - Create a React component with form fields for: strategy name (text), quantity (number), product (select: MIS/NRML), exchange (select: NFO/BFO), enabled toggle (switch)
    - Fetch current settings on mount from `GET /admin/api/tv-alert-settings`
    - Submit updates to `POST /admin/api/tv-alert-settings`
    - Show success/error toast notifications on save
    - Follow the same styling pattern as `KillSwitch.tsx` and other admin pages
    - _Requirements: 6.1, 6.2, 6.3, 6.4, 6.6_

  - [x] 6.2 Register the TV Alert Options page in admin routing
    - Add route entry in `frontend/src/pages/admin/index.ts` exports
    - Add navigation link in `AdminIndex.tsx` for the TV Alert Options section
    - Ensure the page is accessible at the expected admin route
    - _Requirements: 6.1, 6.6_

- [x] 7. Final checkpoint - Full integration complete
  - Ensure all tests pass, ask the user if questions arise.

## Notes

- Tasks marked with `*` are optional and can be skipped for faster MVP
- Each task references specific requirements for traceability
- Checkpoints ensure incremental validation
- Property tests validate universal correctness properties from the design document using Hypothesis
- Unit tests validate specific examples and edge cases
- The implementation uses Python following the existing project patterns (Flask blueprints, SQLAlchemy, flask-restx)
- All new code integrates with existing services (option_symbol_service, place_order_service, event_bus, async_log_order) — no new database tables are created beyond adding columns to the Settings model

## Task Dependency Graph

```json
{
  "waves": [
    { "id": 0, "tasks": ["1.1"] },
    { "id": 1, "tasks": ["1.2", "2.1"] },
    { "id": 2, "tasks": ["2.2", "2.3", "2.4", "2.5"] },
    { "id": 3, "tasks": ["2.6", "3.1"] },
    { "id": 4, "tasks": ["3.2", "3.3"] },
    { "id": 5, "tasks": ["3.4", "3.5", "5.1"] },
    { "id": 6, "tasks": ["5.2"] },
    { "id": 7, "tasks": ["5.3", "5.4"] },
    { "id": 8, "tasks": ["6.1"] },
    { "id": 9, "tasks": ["6.2"] }
  ]
}
```
