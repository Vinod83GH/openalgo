# Implementation Plan: Kill Switch

## Overview

Implement the Kill Switch feature as a broker-agnostic risk management layer. The broker owns deactivation state — our app only calls ACTIVATE and polls status. Implementation proceeds in layers: database model → Dhan broker adapter → service logic → background monitor → REST API blueprint → order middleware → React UI → wiring in app.py.

## Tasks

- [x] 1. Create the database model and CRUD helpers (`database/kill_switch_db.py`)
  - Define `KillSwitchConfig` SQLAlchemy model with columns: `id`, `broker_name` (unique, indexed), `enabled`, `profit_threshold`, `loss_threshold`, `kill_switch_status` (string, default "DEACTIVATED")
  - Set up a dedicated `db_session` and `engine` following the same pattern as `database/settings_db.py`
  - Implement `get_kill_switch_config(broker_name)` — creates default record if none exists
  - Implement `upsert_kill_switch_config(broker_name, **fields)` — update or insert config fields
  - Implement `update_kill_switch_status_cache(broker_name, status)` — updates `kill_switch_status` field and invalidates TTLCache
  - Implement `is_kill_switch_active(broker_name) -> bool` — returns `True` when `kill_switch_status == "ACTIVATED"`
  - Implement `invalidate_kill_switch_cache(broker_name)` — removes entry from TTLCache
  - Add `TTLCache` (TTL=60s) keyed by `f"kill_switch:{broker_name}"` wrapping `get_kill_switch_config` and `is_kill_switch_active`
  - Implement `init_db()` to create the table if it does not exist
  - _Requirements: 1.1, 1.2, 1.3, 1.4, 1.5_

  - [ ]* 1.1 Write property test for default config creation (Property 1)
    - **Property 1: Default config for new broker**
    - **Validates: Requirements 1.2**
    - Use `@given(broker_name=st.text(min_size=1, max_size=64))` with an in-memory SQLite session
    - Assert `enabled=False`, `profit_threshold=0`, `loss_threshold=0`, `kill_switch_status="DEACTIVATED"`

  - [ ]* 1.2 Write property test for config isolation per broker (Property 2)
    - **Property 2: Config isolation per broker**
    - **Validates: Requirements 1.5, 6.4**
    - Use `@given(broker_a=st.text(min_size=1, max_size=32), broker_b=st.text(min_size=1, max_size=32), threshold=st.floats(min_value=0, max_value=1e6))`
    - Assume `broker_a != broker_b`; update one broker's threshold and assert the other is unchanged

- [x] 2. Implement the Dhan kill switch broker adapter (`broker/dhan/api/kill_switch_api.py`)
  - Implement `get_kill_switch_status(access_token: str) -> str` — `GET https://api.dhan.co/v2/killswitch`; parse response and return `"ACTIVATED"` or `"DEACTIVATED"`
  - Implement `activate_kill_switch(access_token: str) -> dict` — `POST https://api.dhan.co/v2/killswitch?killSwitchStatus=ACTIVATE`; return broker response dict
  - Implement `set_pnl_exit(access_token: str, profit_threshold: float, loss_threshold: float) -> dict` — `POST https://api.dhan.co/v2/pnlExit` with threshold body; return broker response dict
  - All requests use headers: `Accept: application/json`, `access-token: <access_token>`; POST requests also include `Content-Type: application/json`
  - Raise a descriptive exception on non-2xx HTTP responses
  - _Requirements: 6.1, 6.2_

  - [ ]* 2.1 Write unit tests for Dhan adapter HTTP calls
    - Mock `requests` and assert correct URL, headers, and body for each of the three functions
    - Test non-2xx response raises exception
    - _Requirements: 6.2_

- [x] 3. Implement the service layer (`services/kill_switch_service.py`)
  - Define `KillSwitchAdapter` protocol with methods: `get_kill_switch_status(access_token)`, `activate_kill_switch(access_token)`, `set_pnl_exit(access_token, profit_threshold, loss_threshold)`
  - Implement `_get_adapter(broker: str) -> KillSwitchAdapter` — returns the correct adapter instance for the given broker name (e.g., returns Dhan adapter for `"dhan"`)
  - Implement `get_kill_switch_status(broker_name, auth_token, broker) -> dict` — calls `adapter.get_kill_switch_status`, updates local cache, fetches current P&L via `positionbook_service.get_positionbook`; returns full status dict
  - Implement `update_kill_switch_config(broker_name, enabled, profit_threshold, loss_threshold, auth_token, broker) -> dict` — validates thresholds ≥ 0, calls `upsert_kill_switch_config`, calls `adapter.set_pnl_exit`, invalidates cache
  - Implement `activate_kill_switch(broker_name, auth_token, broker) -> dict` — calls `adapter.activate_kill_switch`, updates local status cache to "ACTIVATED"
  - Implement `get_broker_kill_switch_status(broker_name, auth_token, broker) -> str` — calls `adapter.get_kill_switch_status`, updates local status cache, returns status string
  - Implement `evaluate_pnl_thresholds(broker_name, current_pnl, auth_token, broker) -> bool` — checks enabled flag, profit/loss thresholds (skip if threshold=0), calls `activate_kill_switch` if breached, logs structured warning; returns True if activation was triggered
  - _Requirements: 2.4, 2.5, 2.7, 3.2, 3.3, 3.4, 3.5, 3.6, 3.7, 4.1, 6.1, 6.2_

  - [ ]* 3.1 Write property test for profit threshold activation (Property 7)
    - **Property 7: Profit threshold triggers broker activation**
    - **Validates: Requirements 3.2, 3.4**
    - Use `@given(threshold=st.floats(min_value=0.01, max_value=1e6), pnl=st.floats(min_value=0.01, max_value=2e6))`
    - `assume(pnl >= threshold)`; mock adapter; assert `activate_kill_switch` was called on the adapter
    - Also test `threshold=0` never triggers activation

  - [ ]* 3.2 Write property test for loss threshold activation (Property 8)
    - **Property 8: Loss threshold triggers broker activation**
    - **Validates: Requirements 3.3, 3.5**
    - Use `@given(threshold=st.floats(min_value=0.01, max_value=1e6), pnl=st.floats(min_value=-2e6, max_value=-0.01))`
    - `assume(pnl <= -threshold)`; mock adapter; assert `activate_kill_switch` was called on the adapter
    - Also test `threshold=0` never triggers activation

  - [ ]* 3.3 Write property test for valid threshold persistence (Property 3)
    - **Property 3: Valid threshold values persist**
    - **Validates: Requirements 2.4, 7.2**
    - Use `@given(profit=st.floats(min_value=0, max_value=1e7), loss=st.floats(min_value=0, max_value=1e7))`
    - Call `update_kill_switch_config`, then `get_kill_switch_config`; assert stored values match submitted values

  - [ ]* 3.4 Write property test for invalid threshold rejection (Property 4)
    - **Property 4: Invalid threshold values are rejected**
    - **Validates: Requirements 2.5**
    - Use `@given(threshold=st.one_of(st.floats(max_value=-0.01), st.text()))`
    - Assert `update_kill_switch_config` raises a validation error and stored thresholds remain unchanged

- [x] 4. Implement the PnL monitor background thread (`services/pnl_monitor.py`)
  - Define `PnLMonitor(threading.Thread)` as a daemon thread with `POLL_INTERVAL_SECONDS=55`, `MARKET_OPEN=time(9,15)`, `MARKET_CLOSE=time(15,30)` (all IST / `Asia/Kolkata`)
  - Implement `_is_market_hours() -> bool` — returns True only between 09:15 and 15:30 IST
  - Implement `_compute_pnl(positions: list[dict]) -> float` — sums `float(p.get("pnl", 0))` across all position records
  - Implement `_poll_all_active_brokers()` — queries all `KillSwitchConfig` records where `enabled=True`; for each:
    1. Call `get_broker_kill_switch_status` to update local cache
    2. If status is "DEACTIVATED", fetch positions via `positionbook_service.get_positionbook`; on API error log WARNING and skip; on success call `evaluate_pnl_thresholds`
  - Implement `run()` — loop: if `_is_market_hours()` call `_poll_all_active_brokers()`, sleep `POLL_INTERVAL_SECONDS`; catch and log all exceptions without crashing the thread
  - No daily reset logic needed — broker resets automatically; monitor simply re-polls status
  - _Requirements: 3.1, 3.7, 4.1, 4.2, 4.3, 4.4, 4.5_

  - [ ]* 4.1 Write property test for P&L computation (Property 9)
    - **Property 9: P&L computation from position book**
    - **Validates: Requirements 4.1**
    - Use `@given(positions=st.lists(st.fixed_dictionaries({"pnl": st.floats(-1e6, 1e6)})))`
    - Assert `_compute_pnl(positions) == sum(float(p["pnl"]) for p in positions)`

  - [ ]* 4.2 Write unit tests for market hours check and status polling
    - Test `_is_market_hours()` returns False before 09:15, True at 09:15, True at 15:29, False at 15:30
    - Test `_poll_all_active_brokers()` calls `get_broker_kill_switch_status` for each enabled broker
    - Test that `evaluate_pnl_thresholds` is only called when broker status is "DEACTIVATED"
    - _Requirements: 4.3, 4.4_

- [x] 5. Checkpoint — Ensure all tests pass
  - Ensure all tests pass, ask the user if questions arise.

- [x] 6. Implement the REST API blueprint (`blueprints/kill_switch.py`)
  - Create Flask blueprint `kill_switch_bp` with `url_prefix="/admin"`
  - Protect all routes with `@check_session_validity` and `@limiter.limit(API_RATE_LIMIT)`
  - Implement `GET /admin/api/kill-switch` — reads `broker` and `auth_token` from session, calls `get_kill_switch_status`, returns JSON response with all required fields (`broker_name`, `enabled`, `profit_threshold`, `loss_threshold`, `kill_switch_status`, `current_pnl`)
  - Implement `POST /admin/api/kill-switch/config` — parses `enabled`, `profit_threshold`, `loss_threshold` from JSON body, calls `update_kill_switch_config` (which also calls `set_pnl_exit`), returns success or 400 on validation failure
  - Implement `POST /admin/api/kill-switch/activate` — calls `activate_kill_switch` for session broker, returns success JSON
  - Return 401 for unauthenticated requests (handled by `check_session_validity`)
  - _Requirements: 7.1, 7.2, 7.3, 7.4, 7.5, 7.6_

  - [ ]* 6.1 Write property test for GET endpoint field completeness (Property 13)
    - **Property 13: GET endpoint returns all required fields**
    - **Validates: Requirements 7.1**
    - Use `@given(...)` with a mocked authenticated session and mocked service layer
    - Assert response JSON contains all of: `broker_name`, `enabled`, `profit_threshold`, `loss_threshold`, `kill_switch_status`, `current_pnl`

  - [ ]* 6.2 Write unit tests for activate endpoint and config save (Properties 5 & 6)
    - **Property 5: Manual activation calls broker ACTIVATE API** — **Validates: Requirements 2.7, 7.3**
    - **Property 6: Status cache reflects broker-reported state** — **Validates: Requirements 4.3**
    - Test POST `/activate` results in adapter `activate_kill_switch` being called
    - Test POST `/config` results in adapter `set_pnl_exit` being called with correct thresholds

  - [ ]* 6.3 Write unit test for unauthenticated request rejection (Property 14)
    - **Property 14: Unauthenticated requests return 401**
    - **Validates: Requirements 7.4**
    - Test all three endpoints return 401 when called without a valid session

- [x] 7. Implement the order middleware and integrate into `blueprints/orders.py`
  - Add `check_kill_switch_active(broker_name: str) -> tuple[bool, dict | None]` to `blueprints/kill_switch.py` (or a shared utils module importable by orders)
  - The function calls `is_kill_switch_active(broker_name)` from the DB module; if True returns `(True, {"status": "error", "message": "Order blocked: Kill Switch is ACTIVATED"})`; otherwise returns `(False, None)`
  - In `blueprints/orders.py`, import `check_kill_switch_active` and call it at the top of order-placement routes (`close_position`, `close_all_positions`, `cancel_all_orders_ui`, `cancel_order_ui`) — if blocked, log the attempt (symbol, action, quantity where available) and return the error response with HTTP 403
  - Read-only routes (`orderbook`, `tradebook`, `positions`, `holdings`, exports) must NOT be gated
  - _Requirements: 5.1, 5.2, 5.3, 5.4_

  - [ ]* 7.1 Write property test for order blocking when ACTIVATED (Property 11)
    - **Property 11: Order blocking when kill switch is ACTIVATED**
    - **Validates: Requirements 5.1**
    - Use `@given(order_data=st.fixed_dictionaries({"symbol": st.text(min_size=1), "action": st.sampled_from(["BUY", "SELL"]), "quantity": st.integers(min_value=1)}))`
    - Mock `is_kill_switch_active` to return True; assert order routes return 403 and broker API is not called

  - [ ]* 7.2 Write unit test for read-only operations permitted when ACTIVATED (Property 12)
    - **Property 12: Read-only operations permitted when ACTIVATED**
    - **Validates: Requirements 5.4**
    - Mock `is_kill_switch_active` to return True; assert `GET /positions`, `GET /orderbook`, `GET /holdings` return 200

- [x] 8. Checkpoint — Ensure all tests pass
  - Ensure all tests pass, ask the user if questions arise.

- [x] 9. Implement the React admin UI (`frontend/src/pages/admin/KillSwitch.tsx`)
  - Follow the same structure as `MarketTimings.tsx` and `FreezeQty.tsx` — use `Card`, `Button`, `Input`, `Label`, `Badge` from `@/components/ui/`
  - Use `lucide-react` icons: `Shield` (DEACTIVATED/normal), `ShieldOff` (ACTIVATED/blocked), `AlertTriangle` (warning)
  - On mount, call `GET /admin/api/kill-switch` to load current status; poll every 30 seconds while mounted
  - Display current broker-reported status badge ("ACTIVATED" / "DEACTIVATED") and broker name
  - Render "Profit Threshold" and "Loss Threshold" numeric inputs with a Save button that calls `POST /admin/api/kill-switch/config` (which also registers thresholds with broker via pnlExit)
  - Render an enable/disable toggle that calls `POST /admin/api/kill-switch/config` with the toggled `enabled` value
  - Render an "Activate Kill Switch" button that calls `POST /admin/api/kill-switch/activate`; disable when status is already "ACTIVATED"
  - No "Deactivate" or "Reset" buttons — broker handles reset automatically
  - Show inline validation error for negative threshold inputs before submitting
  - _Requirements: 2.1, 2.2, 2.3, 2.4, 2.5, 2.6, 2.7, 2.8, 2.9, 4.3_

- [x] 10. Wire everything together in `app.py` and register the route
  - Import `kill_switch_bp` from `blueprints.kill_switch` and register it with `app.register_blueprint(kill_switch_bp)`
  - Import `init_db as ensure_kill_switch_tables_exists` from `database.kill_switch_db` and add it to the `db_init_functions` list in `_init_databases_and_schedulers`
  - Import `PnLMonitor` from `services.pnl_monitor`; after DB init completes inside `_init_databases_and_schedulers`, instantiate and start the monitor: `pnl_monitor = PnLMonitor(daemon=True); pnl_monitor.start()`
  - Add the kill switch page route to the React frontend router (add `/admin/kill-switch` to the existing React SPA routes in `blueprints/react_app.py` or the frontend router config)
  - _Requirements: 1.3, 3.1, 4.4, 6.1, 6.3_

- [x] 11. Final checkpoint — Ensure all tests pass
  - Ensure all tests pass, ask the user if questions arise.

## Notes

- Tasks marked with `*` are optional and can be skipped for faster MVP
- Property-based tests use Hypothesis; each test file must include the comment `# Feature: kill-switch, Property N: <property_text>` above each `@given` test
- The TTLCache in `kill_switch_db.py` is the hot path for order middleware — keep it simple and thread-safe using `cachetools.TTLCache` with a `threading.Lock`
- The `kill_switch_status` column is a short-lived cache of broker state, not the source of truth — the broker API is authoritative
- The PnL monitor needs access to auth tokens per broker; sessions without an auth token should be skipped with a DEBUG log
- All monetary thresholds are stored as `Numeric(18,4)` in the DB but handled as Python `float` in service/monitor logic
- The broker resets the kill switch automatically before 09:00 IST — no reset API call or local reset logic is needed
