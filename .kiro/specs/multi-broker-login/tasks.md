# Implementation Plan: Multi-Broker Login

## Overview

Decouple OpenAlgo's app authentication from broker authentication, enabling standalone app login, per-user broker credential storage, and broker session management (connect/disconnect/switch) without re-entering credentials. Implementation progresses from data layer → backend APIs → frontend changes → wiring.

## Tasks

- [x] 1. Create Broker Credentials Database Module
  - [x] 1.1 Create `database/broker_credentials_db.py` with BrokerCredential model
    - Define SQLAlchemy model with columns: id, username, broker_name, api_key, api_secret_encrypted, client_id, redirect_url, additional_config, created_at, updated_at
    - Add UniqueConstraint on (username, broker_name)
    - Add index on username
    - Implement `init_db()` using existing `db_init_helper` pattern
    - Reuse Fernet encryption from `database/auth_db.py` (same key derivation)
    - Implement `encrypt_secret(value)` and `decrypt_secret(encrypted_value)` helpers
    - _Requirements: 5.2, 5.6_

  - [x] 1.2 Implement CRUD helpers for broker credentials
    - `save_credentials(username, broker_name, api_key, api_secret, client_id, redirect_url, additional_config)` — upsert encrypted credentials
    - `get_credentials(username, broker_name)` — return decrypted credentials dict or None
    - `get_all_credentials(username)` — return list of all broker creds for user (secrets masked)
    - `delete_credentials(username, broker_name)` — remove stored credentials
    - `mask_secret(value, show_chars=4)` — return masked string for API responses
    - _Requirements: 5.2, 5.3, 5.5, 5.6, 5.7_

  - [ ]* 1.3 Write property tests for broker credentials module
    - **Property 10: Credential save/retrieve round trip**
    - **Property 11: Multiple brokers per user storage**
    - **Property 12: API secret encryption round trip**
    - **Validates: Requirements 5.2, 5.3, 5.5, 5.6**

- [x] 2. Checkpoint - Ensure credential storage tests pass
  - Ensure all tests pass, ask the user if questions arise.

- [x] 3. Create Broker Credential Store Blueprint (REST API)
  - [x] 3.1 Create `blueprints/broker_credentials_store.py` with CRUD endpoints
    - `GET /api/broker-credentials/list` — return all saved broker creds for current user (masked secrets)
    - `GET /api/broker-credentials/<broker>` — return credentials for specific broker (masked)
    - `POST /api/broker-credentials/<broker>` — save/update credentials (validate non-empty api_key, api_secret)
    - `DELETE /api/broker-credentials/<broker>` — remove saved credentials
    - All endpoints require `session["user"]` (return 401 if missing)
    - Validate required fields, return 400 on empty/whitespace api_key or api_secret
    - _Requirements: 5.1, 5.2, 5.4, 5.7, 5.8_

  - [ ]* 3.2 Write property tests for credential store API
    - **Property 13: Sensitive fields masked in API response**
    - **Property 14: Invalid credentials rejected without auth trigger**
    - **Validates: Requirements 5.7, 5.8**

- [x] 4. Create Broker Session Blueprint
  - [x] 4.1 Create `blueprints/broker_session.py` with connect/disconnect/status endpoints
    - `POST /broker-session/connect` — load credentials from DB, set env vars in memory, delegate to `broker_auth_functions`, call `handle_auth_success` on success
    - `POST /broker-session/disconnect` — revoke token via `upsert_auth(username, "", "", revoke=True)`, clear `session["logged_in"]`, `session["broker"]`, `session["AUTH_TOKEN"]`, preserve `session["user"]`
    - `GET /broker-session/status` — return active broker info or null
    - Enforce single-active-broker: if already connected, disconnect old before connecting new
    - All endpoints require `session["user"]`
    - _Requirements: 2.2, 2.4, 3.1, 3.2, 3.3, 3.4, 4.1, 4.2, 5.9_

  - [ ]* 4.2 Write property tests for broker session management
    - **Property 3: Broker disconnect preserves app session**
    - **Property 5: Successful broker auth establishes active broker session**
    - **Property 6: Failed broker auth preserves pre-auth state**
    - **Property 7: Single active broker invariant**
    - **Property 8: Broker switch revokes old and activates new**
    - **Property 9: Broker disconnect revokes token**
    - **Validates: Requirements 1.3, 2.2, 2.4, 2.5, 3.1, 3.2, 3.3, 3.4, 4.1, 4.2, 4.4**

- [x] 5. Modify Auth Blueprint for Decoupled Login
  - [x] 5.1 Update `blueprints/auth.py` login and session-status
    - `POST /auth/login` — on success, set `session["user"]` only, do NOT set `session["logged_in"]`, return `{"status": "success", "redirect": "/broker-select"}`
    - `GET /auth/session-status` — return `authenticated`, `logged_in`, `user`, `broker`, and `available_brokers` fields
    - `POST /auth/logout` — clear entire session (app + broker), revoke broker token if active
    - Ensure existing `check_session_validity` decorator still works with new two-level auth
    - _Requirements: 1.1, 1.2, 1.3, 1.4, 1.5, 7.1, 7.2, 7.3, 7.4_

  - [ ]* 5.2 Write property tests for auth blueprint changes
    - **Property 1: App login establishes user session without broker session**
    - **Property 2: Invalid login preserves existing session state**
    - **Property 4: App logout clears both app and broker session**
    - **Property 17: Session status accurately reflects auth state**
    - **Validates: Requirements 1.1, 1.4, 1.5, 7.1, 7.2, 7.3, 7.4**

- [x] 6. Checkpoint - Ensure all backend tests pass
  - Ensure all tests pass, ask the user if questions arise.

- [x] 7. Modify Broker Login Blueprint
  - [x] 7.1 Update `blueprints/brlogin.py` to load credentials from DB
    - Modify `broker_callback` to retrieve credentials from `broker_credentials_db` instead of `.env` when session user has stored creds
    - Fall back to `.env` credentials if no DB credentials exist (backward compatibility)
    - Ensure OAuth callbacks still work (session["user"] must be set before callback)
    - _Requirements: 2.3, 5.9, 6.3_

- [x] 8. Frontend: Update Auth Store
  - [x] 8.1 Modify `frontend/src/stores/authStore.ts` (or equivalent)
    - Add `isBrokerConnected` boolean separate from `isAuthenticated`
    - `isAuthenticated` = true when `session-status` returns `authenticated: true`
    - `isBrokerConnected` = true when `session-status` returns `logged_in: true`
    - Add `availableBrokers` array from session-status response
    - Add `connectBroker(broker)` and `disconnectBroker()` actions calling broker-session API
    - _Requirements: 7.1, 7.2, 7.3, 7.4_

- [x] 9. Frontend: Modify Broker Selection Page
  - [x] 9.1 Update `frontend/src/pages/BrokerSelect.tsx` for inline credential entry
    - Show all supported brokers (from `available_brokers` in session-status)
    - On broker select, show inline credential form (API key, secret, client ID, redirect URL)
    - Fetch and pre-populate saved credentials via `GET /api/broker-credentials/<broker>`
    - Mask sensitive fields in display
    - On submit: save credentials via POST → trigger connect via `/broker-session/connect` → redirect to dashboard
    - Validate non-empty required fields before submit
    - _Requirements: 5.1, 5.4, 5.5, 5.7, 5.8_

- [x] 10. Frontend: Update Dashboard for Degraded State
  - [x] 10.1 Modify Dashboard to show warning banner when no broker connected
    - When `isAuthenticated && !isBrokerConnected`: show prominent warning banner with link to broker selection
    - Skip data-fetching API calls when `!isBrokerConnected`
    - Show empty data panels instead of loading spinners
    - _Requirements: 4.3_

- [x] 11. Checkpoint - Ensure frontend builds without errors
  - Ensure all tests pass, ask the user if questions arise.

- [x] 12. Wire Everything in app.py
  - [x] 12.1 Register new blueprints and init new DB table
    - Import and register `broker_credentials_store_bp` in `app.py`
    - Import and register `broker_session_bp` in `app.py`
    - Add `broker_credentials_init_db` to the parallel DB init list in `setup_environment()`
    - Exempt broker-session endpoints from CSRF if needed (they use session auth)
    - _Requirements: 6.1, 6.2, 6.3_

- [x] 13. Trading Compatibility Guard
  - [x] 13.1 Add broker-required guard to trading endpoints
    - Ensure trading endpoints (orders, positions, etc.) return 401 with "Broker login required" when `session["logged_in"]` is False
    - Verify existing `check_session_validity` decorator or add explicit checks
    - _Requirements: 6.4_

  - [ ]* 13.2 Write property tests for trading compatibility
    - **Property 15: Active broker provides context to trading calls**
    - **Property 16: Trading without broker returns error**
    - **Validates: Requirements 6.1, 6.2, 6.4**

- [x] 14. Final checkpoint - Ensure all tests pass
  - Ensure all tests pass, ask the user if questions arise.

## Notes

- Tasks marked with `*` are optional and can be skipped for faster MVP
- Each task references specific requirements for traceability
- Checkpoints ensure incremental validation
- Property tests validate universal correctness properties from the design document
- Backend uses Python (Flask + SQLAlchemy + Hypothesis for property tests)
- Frontend uses TypeScript/React (fast-check for property tests if applicable)
- Existing `.env`-based broker config remains as fallback for backward compatibility
