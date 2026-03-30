# Requirements Document

## Introduction

The Kill Switch feature provides automated and manual risk management controls for broker accounts in the OpenAlgo trading platform. It allows administrators to configure daily Profit & Loss (P&L) thresholds that, when breached, automatically activate the broker's kill switch via the broker's own API. The broker (Dhan) owns and manages the deactivation state — our app calls ACTIVATE on the broker's kill switch API when a threshold is breached or when the admin manually triggers it. The broker resets the kill switch automatically before the next market open, so no local reset logic is needed. Separate profit and loss thresholds can be configured independently. The Kill Switch is scoped to the currently active broker session — if the user switches brokers, each broker maintains its own independent kill switch state. The feature is designed to be broker-agnostic: the core kill switch logic is decoupled from any specific broker implementation via an abstract `KillSwitchAdapter` interface, so new brokers can be integrated by supplying their own adapter without modifying the kill switch engine.

---

## Glossary

- **Kill_Switch**: The system component responsible for monitoring P&L thresholds and triggering broker-side kill switch activation.
- **Kill_Switch_Config**: The persisted configuration record containing the P&L thresholds, enabled state, and the broker name it is scoped to. Deactivation state is fetched live from the broker API, not stored locally.
- **PnL_Monitor**: The background service that polls the broker's kill switch status periodically and syncs it to a local cache.
- **KillSwitchAdapter**: The abstract interface (protocol) that each broker-specific kill switch module must implement. Dhan's implementation lives at `broker/dhan/api/kill_switch_api.py`.
- **Broker_Adapter**: The broker-specific module (under `/broker/<name>/api/`) that implements order placement, position retrieval, and kill switch operations via the broker's API.
- **Admin_UI**: The admin section of the React frontend where the Kill Switch is configured and controlled.
- **ACTIVATED**: The broker-reported state in which the broker account is blocked from placing new orders.
- **DEACTIVATED**: The broker-reported state in which the broker account is permitted to place orders normally.
- **Profit_Threshold**: A non-negative monetary amount (in the account's base currency). Kill switch activation triggers when today's P&L is greater than or equal to `+profit_threshold`. A value of 0 disables profit-side activation.
- **Loss_Threshold**: A non-negative monetary amount (in the account's base currency). Kill switch activation triggers when today's P&L is less than or equal to `-loss_threshold`. A value of 0 disables loss-side activation.
- **Active_Broker**: The broker session currently selected and in use by the logged-in user, identified by broker name.
- **Trading_Day**: The calendar date in IST (Asia/Kolkata) from market open (09:15) to market close (15:30).
- **IST**: Indian Standard Time (UTC+5:30), the timezone used throughout the platform.
- **pnlExit**: The Dhan broker API endpoint (`POST /v2/pnlExit`) used to register profit and loss thresholds with the broker directly. The broker monitors P&L and activates the kill switch itself when thresholds are breached.

---

## Requirements

### Requirement 1: Kill Switch Configuration Storage

**User Story:** As an administrator, I want to persist Kill Switch settings so that the configured thresholds and enabled state survive application restarts.

#### Acceptance Criteria

1. THE Kill_Switch_Config SHALL store the following fields: `broker_name` (string, identifying the Active_Broker this config belongs to), `enabled` (boolean), `profit_threshold` (decimal, ≥ 0), and `loss_threshold` (decimal, ≥ 0). Deactivation state is NOT stored locally — it is fetched live from the broker's kill switch status API.
2. WHEN the application starts and no Kill_Switch_Config record exists for the Active_Broker, THE Kill_Switch SHALL create a default record with `enabled = false`, `profit_threshold = 0`, and `loss_threshold = 0`.
3. THE Kill_Switch_Config SHALL be stored in the application's existing SQLAlchemy-managed database, following the same session and engine patterns used by other database modules.
4. WHEN Kill_Switch_Config is read, THE Kill_Switch SHALL use a short-lived in-memory cache (TTL ≤ 60 seconds) to reduce database query frequency, consistent with the caching pattern used in `settings_db.py`.
5. THE Kill_Switch_Config SHALL be keyed by `broker_name` so that each broker session maintains an independent configuration.

---

### Requirement 2: Admin UI — Kill Switch Configuration Panel

**User Story:** As an administrator, I want a dedicated Kill Switch section on the admin page so that I can view broker-reported status, set the P&L thresholds, and manually activate the broker's kill switch.

#### Acceptance Criteria

1. THE Admin_UI SHALL display the current Kill Switch status as either "ACTIVATED" or "DEACTIVATED", fetched live from the broker's kill switch status API, along with the Active_Broker name.
2. THE Admin_UI SHALL provide a numeric input field labelled "Profit Threshold" for the administrator to set the profit-side activation threshold (non-negative decimal).
3. THE Admin_UI SHALL provide a separate numeric input field labelled "Loss Threshold" for the administrator to set the loss-side activation threshold (non-negative decimal).
4. WHEN the administrator submits new threshold values, THE Kill_Switch SHALL validate that both `profit_threshold` and `loss_threshold` are non-negative numbers, persist them to Kill_Switch_Config for the Active_Broker, and call the broker's `pnlExit` API to register the thresholds with the broker directly.
5. IF the administrator submits a threshold value that is negative or non-numeric, THEN THE Kill_Switch SHALL return a 400 error response with a descriptive message and SHALL NOT update the stored thresholds or call the broker API.
6. THE Admin_UI SHALL provide a toggle or button to enable or disable the Kill Switch feature (i.e., set `enabled = true/false`).
7. THE Admin_UI SHALL provide an "Activate Kill Switch" button that immediately calls the broker's ACTIVATE API for the Active_Broker.
8. WHEN the broker-reported kill switch status is "ACTIVATED", THE Admin_UI SHALL display the activated state clearly. No manual deactivation button is shown — the broker resets automatically before the next market open.
9. THE Admin_UI SHALL use the same CSS classes, component patterns (Card, Button, Input, Label, Badge, Table from `@/components/ui/`), icon library (lucide-react), and naming conventions as the existing admin pages (e.g., `FreezeQty.tsx`, `MarketTimings.tsx`) in the `frontend/src/pages/admin/` directory.

---

### Requirement 3: P&L Threshold Activation via Broker API

**User Story:** As an administrator, I want the system to automatically activate the broker's kill switch when today's P&L breaches the configured threshold, so that losses or runaway profits are capped without manual intervention.

#### Acceptance Criteria

1. WHILE the Kill Switch is `enabled` and the broker-reported status is "DEACTIVATED" (i.e., not yet activated), THE PnL_Monitor SHALL evaluate the current intraday P&L against the configured thresholds at a regular interval not exceeding 60 seconds.
2. WHEN today's intraday P&L is greater than or equal to `+profit_threshold` and `profit_threshold` is greater than 0, THE Kill_Switch SHALL call the broker's ACTIVATE API to activate the kill switch.
3. WHEN today's intraday P&L is less than or equal to `-loss_threshold` and `loss_threshold` is greater than 0, THE Kill_Switch SHALL call the broker's ACTIVATE API to activate the kill switch.
4. IF `profit_threshold` is 0, THEN THE Kill_Switch SHALL NOT trigger activation based on the profit side, regardless of the `enabled` flag.
5. IF `loss_threshold` is 0, THEN THE Kill_Switch SHALL NOT trigger activation based on the loss side, regardless of the `enabled` flag.
6. WHEN threshold-based activation is triggered, THE Kill_Switch SHALL log a structured warning message including the breach direction (profit/loss), the applicable threshold value, and the actual P&L value.
7. THE Kill_Switch SHALL also call the broker's `pnlExit` API when thresholds are saved, so the broker can monitor and activate the kill switch independently of our polling cycle.

---

### Requirement 4: Real-Time P&L Tracking and Status Polling

**User Story:** As an administrator, I want the system to track today's intraday P&L and display the current broker kill switch status in real time.

#### Acceptance Criteria

1. THE PnL_Monitor SHALL compute today's intraday P&L as the sum of realised P&L from closed positions and unrealised P&L from open positions, using data sourced from the Active_Broker's position book API.
2. WHEN the broker's position book API returns an error, THE PnL_Monitor SHALL log the error and retain the last successfully computed P&L value without triggering activation.
3. THE PnL_Monitor SHALL poll the broker's kill switch status API periodically and cache the result so that the Admin_UI and order middleware can read the current status without making a live broker API call on every request.
4. WHILE the trading day is outside market hours (before 09:15 IST or after 15:30 IST), THE PnL_Monitor SHALL suspend P&L polling and SHALL NOT trigger threshold evaluation.
5. THE broker resets the kill switch automatically before 09:00 IST on the next calendar day. Our app does NOT need to call any reset or deactivate API — it only needs to re-poll the broker's status API to reflect the updated state.

---

### Requirement 5: Order Blocking When Kill Switch Is Activated

**User Story:** As a risk manager, I want all new order placement attempts to be blocked when the broker's kill switch is activated, so that no trades can be executed during an activated state.

#### Acceptance Criteria

1. WHILE the broker-reported kill switch status is "ACTIVATED", THE Kill_Switch SHALL intercept any order placement request and return an error response indicating the account is blocked.
2. WHEN an order placement is blocked by the Kill Switch, THE Kill_Switch SHALL log the blocked attempt including the symbol, action, and quantity.
3. THE Kill_Switch SHALL implement order blocking as a broker-agnostic middleware layer, so that the blocking logic does not need to be duplicated in each Broker_Adapter.
4. WHILE the broker-reported kill switch status is "ACTIVATED", THE Kill_Switch SHALL permit read-only operations (position queries, order book queries, fund queries) to proceed normally.

---

### Requirement 6: Broker-Agnostic Architecture

**User Story:** As a developer, I want the Kill Switch logic to be independent of any specific broker implementation so that new brokers can be added without modifying the core kill switch engine.

#### Acceptance Criteria

1. THE Kill_Switch SHALL define an abstract `KillSwitchAdapter` protocol/interface in `services/kill_switch_service.py` with methods: `get_kill_switch_status(access_token)`, `activate_kill_switch(access_token)`, and `set_pnl_exit(access_token, profit_threshold, loss_threshold)`.
2. THE Dhan broker SHALL implement the `KillSwitchAdapter` interface in `broker/dhan/api/kill_switch_api.py`, calling the Dhan v2 kill switch and pnlExit endpoints.
3. WHEN a new broker is added to the `/broker` directory, THE Kill_Switch SHALL apply to that broker by implementing the `KillSwitchAdapter` interface without requiring changes to the Kill_Switch module itself.
4. THE Kill_Switch configuration and state SHALL be stored per Active_Broker (keyed by broker name), so that switching brokers presents the kill switch state specific to that broker session.

---

### Requirement 7: Kill Switch Status API

**User Story:** As a frontend developer, I want JSON API endpoints for all Kill Switch operations so that the React Admin_UI can read and update Kill Switch state without page reloads.

#### Acceptance Criteria

1. THE Kill_Switch SHALL expose a `GET /admin/api/kill-switch` endpoint that returns the current `broker_name`, `enabled`, `profit_threshold`, `loss_threshold`, `kill_switch_status` (broker-reported: "ACTIVATED" | "DEACTIVATED"), and `current_pnl` fields for the Active_Broker.
2. THE Kill_Switch SHALL expose a `POST /admin/api/kill-switch/config` endpoint that accepts `enabled`, `profit_threshold`, and `loss_threshold`, updates Kill_Switch_Config for the Active_Broker, and calls the broker's `pnlExit` API to register the thresholds.
3. THE Kill_Switch SHALL expose a `POST /admin/api/kill-switch/activate` endpoint that immediately calls the broker's ACTIVATE API for the Active_Broker.
4. WHEN any Kill Switch API endpoint is called by an unauthenticated request, THE Kill_Switch SHALL return a 401 response.
5. THE Kill_Switch API endpoints SHALL be protected by the same session validity check (`check_session_validity`) used by all other admin API endpoints.
6. THE Kill_Switch API endpoints SHALL be subject to the application's standard rate limiting policy defined by `API_RATE_LIMIT` in the environment configuration.
