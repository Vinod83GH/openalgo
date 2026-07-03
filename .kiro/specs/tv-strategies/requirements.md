# Requirements Document

## Introduction

This feature replaces the global TV alert options trading configuration (stored in the Settings table) with a per-strategy model. Each strategy is a named configuration record that defines trading parameters (lot size, strike selection, product, exchange, active days, enabled state). The TradingView webhook payload includes a "strategy" field that maps to a strategy record in the database. Alert processing uses the matched strategy's configuration instead of the old global settings. A new CRUD admin UI replaces the deprecated `/admin/tv-alert-options` page, and the API endpoint is renamed from `/api/v1/tv-alert-options` to `/api/v1/tv-alert-triggers`.

## Glossary

- **Strategy_Service**: The backend service layer responsible for CRUD operations on TvStrategy records and for looking up strategy configuration during alert processing.
- **TvStrategy**: A database model representing a named strategy configuration with fields: name, active_days, lot_size, strike_selection, enabled, product, exchange.
- **Admin_API**: The Flask admin blueprint that exposes JSON endpoints for the React frontend to manage TvStrategy records.
- **Trigger_Endpoint**: The flask-restx namespace registered at `/api/v1/tv-alert-triggers` that receives TradingView webhook payloads and processes alerts.
- **Admin_UI**: The React frontend pages at `/admin/tv-strategies` (list) and `/admin/tv-strategies/:strategyName` (edit) for managing strategy configurations.
- **Active_Days**: A set of weekday flags (Monday through Friday) indicating on which days a strategy should process incoming alerts.
- **Strike_Selection**: A string value from the range ITM5 to OTM5 (e.g., ITM2, ATM, OTM3) that determines which option strike to select relative to the current market price.
- **Lot_Size**: A positive integer representing the number of lots to trade when an alert fires for a strategy.

## Requirements

### Requirement 1: TvStrategy Database Model

**User Story:** As a system administrator, I want strategy configurations stored as individual database records, so that each TradingView alert strategy can have independent trading parameters.

#### Acceptance Criteria

1. THE Strategy_Service SHALL store each TvStrategy record with the fields: name (unique string), active_days (set of weekdays from Monday to Friday), lot_size (positive integer), strike_selection (string from ITM5 to OTM5), enabled (boolean), product (one of MIS or NRML), and exchange (one of NFO, BFO, MCX, or CDS).
2. THE Strategy_Service SHALL enforce uniqueness on the TvStrategy name field.
3. THE Strategy_Service SHALL default the enabled field to true when creating a new TvStrategy record.
4. THE Strategy_Service SHALL default the active_days field to Monday through Friday when creating a new TvStrategy record.
5. THE Strategy_Service SHALL reject any lot_size value less than 1.

### Requirement 2: Strategy CRUD Admin API

**User Story:** As a system administrator, I want API endpoints to create, read, update, and delete strategy configurations, so that I can manage strategies from the admin UI.

#### Acceptance Criteria

1. WHEN a GET request is received at the strategies list endpoint, THE Admin_API SHALL return all TvStrategy records as a JSON array.
2. WHEN a GET request is received at the single strategy endpoint with a valid strategy name, THE Admin_API SHALL return the full TvStrategy record as JSON.
3. WHEN a POST request is received at the strategies list endpoint with valid fields, THE Admin_API SHALL create a new TvStrategy record and return it with HTTP 201.
4. WHEN a PUT request is received at the single strategy endpoint with valid fields, THE Admin_API SHALL update the existing TvStrategy record and return the updated record.
5. WHEN a DELETE request is received at the single strategy endpoint with a valid strategy name, THE Admin_API SHALL remove the TvStrategy record and return HTTP 200 with a success message.
6. IF a POST request provides a strategy name that already exists, THEN THE Admin_API SHALL return HTTP 409 with an error message indicating the name is taken.
7. IF a GET, PUT, or DELETE request references a strategy name that does not exist, THEN THE Admin_API SHALL return HTTP 404 with an error message.
8. IF a POST or PUT request provides a lot_size value less than 1, THEN THE Admin_API SHALL return HTTP 400 with a validation error message.
9. IF a POST or PUT request provides an invalid exchange value, THEN THE Admin_API SHALL return HTTP 400 with a validation error listing valid exchanges.
10. IF a POST or PUT request provides an invalid product value, THEN THE Admin_API SHALL return HTTP 400 with a validation error listing valid products.
11. IF a POST or PUT request provides a strike_selection value outside the ITM5 to OTM5 range, THEN THE Admin_API SHALL return HTTP 400 with a validation error listing valid strike selections.

### Requirement 3: Endpoint Rename

**User Story:** As a developer, I want the TV alert webhook endpoint renamed to reflect its trigger-based purpose, so that the API naming is consistent with the new strategy architecture.

#### Acceptance Criteria

1. THE Trigger_Endpoint SHALL be registered at the path `/api/v1/tv-alert-triggers`.
2. THE Trigger_Endpoint SHALL accept POST requests with JSON payloads containing a "strategy" field.
3. WHEN a POST request is received at the old path `/api/v1/tv-alert-options`, THE Trigger_Endpoint SHALL return HTTP 404 (no backwards-compatible redirect).

### Requirement 4: Alert Processing with Strategy Lookup

**User Story:** As a trader, I want incoming TradingView alerts to use my per-strategy configuration for lot size, strike selection, product, and exchange, so that each strategy operates independently.

#### Acceptance Criteria

1. WHEN a webhook payload is received, THE Trigger_Endpoint SHALL extract the "strategy" field value and look up the corresponding TvStrategy record by name.
2. IF the "strategy" field value does not match any TvStrategy record, THEN THE Trigger_Endpoint SHALL return HTTP 400 with the error message "Unknown strategy: {name}".
3. WHILE a TvStrategy record has its enabled field set to false, THE Trigger_Endpoint SHALL reject alerts for that strategy with HTTP 200 and a message indicating the strategy is disabled.
4. WHEN a TvStrategy record is enabled and the current weekday is included in the active_days set, THE Trigger_Endpoint SHALL proceed with order processing using that strategy configuration.
5. WHILE the current weekday is not included in the active_days set of the matched TvStrategy, THE Trigger_Endpoint SHALL reject the alert with HTTP 200 and a message indicating the day is not active.
6. WHEN processing an alert, THE Trigger_Endpoint SHALL use the lot_size from the matched TvStrategy as the order quantity.
7. WHEN processing a SPOT_OPTIONS alert, THE Trigger_Endpoint SHALL use the strike_selection from the matched TvStrategy instead of the hardcoded ITM2 offset.
8. WHEN processing an alert, THE Trigger_Endpoint SHALL use the product value from the matched TvStrategy for the order product type.
9. WHEN processing an alert, THE Trigger_Endpoint SHALL use the exchange value from the matched TvStrategy for the order exchange.

### Requirement 5: Admin UI — Strategy List Page

**User Story:** As a system administrator, I want a list page showing all configured strategies, so that I can quickly view and manage them.

#### Acceptance Criteria

1. THE Admin_UI SHALL render a strategy list page at the route `/admin/tv-strategies`.
2. THE Admin_UI SHALL display each strategy's name, enabled status, active_days, lot_size, product, and exchange in the list.
3. WHEN the administrator clicks a strategy row, THE Admin_UI SHALL navigate to the edit page at `/admin/tv-strategies/{strategy-name}`.
4. THE Admin_UI SHALL provide a button to create a new strategy that navigates to a creation form.
5. THE Admin_UI SHALL provide a delete action for each strategy in the list with a confirmation prompt.

### Requirement 6: Admin UI — Strategy Edit Page

**User Story:** As a system administrator, I want an edit form for individual strategy configuration, so that I can update trading parameters per strategy.

#### Acceptance Criteria

1. THE Admin_UI SHALL render an edit form at the route `/admin/tv-strategies/:strategyName`.
2. THE Admin_UI SHALL display editable fields for: name, active_days (Monday through Friday checkboxes), lot_size (numeric input), strike_selection (dropdown from ITM5 to OTM5), enabled (toggle switch), product (dropdown: MIS/NRML), and exchange (dropdown: NFO/BFO/MCX/CDS).
3. WHEN the administrator saves the form with valid values, THE Admin_UI SHALL send a PUT request to the Admin_API and display a success notification.
4. IF the form submission returns a validation error, THEN THE Admin_UI SHALL display the error message without clearing the form.
5. THE Admin_UI SHALL validate that lot_size is a positive integer before sending the request.

### Requirement 7: Deprecation of Global TV Settings

**User Story:** As a system administrator, I want the old global TV alert settings removed from the admin interface, so that all configuration is done per-strategy.

#### Acceptance Criteria

1. THE Admin_UI SHALL remove the `/admin/tv-alert-options` page from the frontend router.
2. THE Admin_API SHALL remove the `/admin/api/tv-alert-settings` GET and POST endpoints.
3. THE Strategy_Service SHALL not read tv_alert_strategy, tv_alert_quantity, tv_alert_product, tv_alert_exchange, or tv_alert_enabled columns from the Settings table during alert processing.
