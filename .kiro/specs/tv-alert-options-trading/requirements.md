# Requirements Document

## Introduction

This feature automates options trading based on TradingView alerts. When a TradingView webhook arrives with a SPOT chart type signal, the system resolves the appropriate In-The-Money (ITM) option strike 2 levels deep, and places a bracket order with the active broker. The system integrates with the existing webhook infrastructure, option symbol resolution service, and order placement pipeline.

## Glossary

- **TV_Alert_Service**: The service component that receives, validates, and processes TradingView alert webhooks for options trading
- **Option_Resolver**: The component responsible for resolving the correct ITM option strike using the existing option_symbol_service
- **Order_Placer**: The component that places orders with the active broker using the existing place_order_service
- **Alert_Store**: The database component that persists TV alert records and their processing outcomes
- **CMP**: Current Market Price of the underlying symbol at the time of the alert
- **ITM**: In The Money — for CALL options, strikes below CMP; for PUT options, strikes above CMP
- **ITM2**: Two strikes In The Money from the ATM (At The Money) strike
- **Bracket_Order**: An order with entry, stop-loss, and target prices attached as a single unit
- **Signal**: Trading direction indicator — "BUY" triggers a CALL option, "SELL" triggers a PUT option
- **Chart_Type**: Indicates whether the TradingView alert is for a SPOT chart or an OPTION chart

## Requirements

### Requirement 1: TradingView Alert Webhook Reception

**User Story:** As a trader, I want to receive automated trading signals from TradingView via webhook, so that my options trades are executed without manual intervention.

#### Acceptance Criteria

1. WHEN a POST request arrives at the TV alert webhook endpoint, THE TV_Alert_Service SHALL authenticate the request using the API key from the request payload following the existing `get_auth_token_broker` pattern
2. WHEN a valid webhook payload is received, THE TV_Alert_Service SHALL validate the presence of all required fields: cmp, symbol, charttype, signal, option_type, sl, and target
3. IF any required field is missing from the webhook payload, THEN THE TV_Alert_Service SHALL return an HTTP 400 response with a descriptive error message identifying the missing fields
4. WHEN a valid alert is received, THE TV_Alert_Service SHALL log the incoming alert payload using the existing logger pattern
5. IF the signal field contains a value other than "BUY" or "SELL" (case-insensitive), THEN THE TV_Alert_Service SHALL return an HTTP 400 response indicating an invalid signal value
6. IF the charttype field contains a value other than "SPOT" or "OPTION" (case-insensitive), THEN THE TV_Alert_Service SHALL return an HTTP 400 response indicating an invalid chart type value
7. WHEN the API key authentication fails, THE TV_Alert_Service SHALL return an HTTP 403 response with an "Invalid API key" error message

### Requirement 2: ITM Strike Resolution for SPOT Alerts

**User Story:** As a trader, I want the system to automatically find the correct ITM option strike 2 levels deep for the option type specified in my alert, so that I can trade both CALL and PUT options on BUY or SELL signals.

#### Acceptance Criteria

1. WHEN charttype is "SPOT", THE TV_Alert_Service SHALL require an additional `option_type` field ("CE" or "PE") in the webhook payload to determine which option chain to resolve
2. WHEN charttype is "SPOT" and option_type is "CE", THE Option_Resolver SHALL resolve a CALL option 2 strikes ITM using the option_symbol_service with offset "ITM2"
3. WHEN charttype is "SPOT" and option_type is "PE", THE Option_Resolver SHALL resolve a PUT option 2 strikes ITM using the option_symbol_service with offset "ITM2"
4. THE signal field ("BUY" or "SELL") SHALL determine the order action on the resolved option contract — BUY means buy the option, SELL means sell the option — independent of option_type
5. WHEN resolving the option strike, THE Option_Resolver SHALL use the CMP value from the alert payload as the underlying_ltp parameter to avoid redundant quote API calls
6. WHEN resolving the option strike, THE Option_Resolver SHALL determine the nearest available expiry for the given symbol from the database
7. IF the option strike resolution fails (no strikes found, offset out of range, or symbol not found), THEN THE Option_Resolver SHALL return a descriptive error and log the failure details
8. WHEN charttype is "OPTION", THE TV_Alert_Service SHALL treat the symbol field as the direct option symbol and skip ITM resolution

### Requirement 3: Order Placement with Stop-Loss and Target in Same API Call

**User Story:** As a trader, I want orders placed with SL and target as part of a single order API call, so that my risk management is atomic and guaranteed at order creation time.

#### Acceptance Criteria

1. WHEN the option strike is resolved, THE Order_Placer SHALL place a single order API call that includes entry price type, stop-loss, and target in the same request
2. THE Order_Placer SHALL pass the signal value ("BUY" or "SELL") directly as the order action — BUY signal buys the option, SELL signal sells the option
3. WHEN placing the order, THE Order_Placer SHALL include the SL value from the alert as the stoploss parameter in the order request
4. WHEN placing the order, THE Order_Placer SHALL include the TARGET value from the alert as the target/squareoff parameter in the order request
5. THE Order_Placer SHALL use LIMIT or MARKET price type for entry as configured, with SL and TARGET attached as bracket order legs in the same API call
6. WHEN placing the order, THE Order_Placer SHALL use the configured quantity (lot size) from the TV alert configuration for that user
7. WHEN placing the order, THE Order_Placer SHALL use the configured product type (MIS or NRML) and exchange (NFO or BFO) from the TV alert configuration
8. IF the order placement fails, THEN THE Order_Placer SHALL log the error details and emit an OrderFailedEvent via the event bus
9. IF the broker does not support bracket orders with SL+Target in a single call, THEN THE Order_Placer SHALL log a warning and place a plain entry order noting that SL/Target were not attached

### Requirement 4: Database Persistence of Alert Records

**User Story:** As a trader, I want every alert and its outcome persisted to the database, so that I can audit my automated trades and debug issues.

#### Acceptance Criteria

1. WHEN a TV alert webhook is received, THE Alert_Store SHALL create a new record with a unique alert_id, timestamp, and the full incoming payload
2. WHEN processing completes, THE Alert_Store SHALL update the record with the resolved option symbol, order_id, and status ("success" or "failed")
3. IF processing fails at any step, THEN THE Alert_Store SHALL update the record with status "failed" and store the error_message describing the failure reason
4. THE Alert_Store SHALL follow the existing database patterns using SQLAlchemy declarative base, scoped_session, and init_db initialization
5. THE Alert_Store SHALL use asynchronous logging via ThreadPoolExecutor following the async_log_order pattern to avoid blocking the webhook response

### Requirement 5: Monitoring and Event Emission

**User Story:** As a system operator, I want visibility into alert processing outcomes, so that I can monitor the system health and respond to failures promptly.

#### Acceptance Criteria

1. WHEN an order is placed successfully, THE TV_Alert_Service SHALL emit an OrderPlacedEvent via the event bus with mode, api_type, symbol, exchange, action, quantity, order_id, and request/response data
2. WHEN an order placement fails, THE TV_Alert_Service SHALL emit an OrderFailedEvent via the event bus with mode, api_type, request data, error message, symbol, and exchange
3. THE TV_Alert_Service SHALL log each processing step (alert received, validation passed, strike resolved, order placed/failed) using the existing structured logger

### Requirement 6: Configuration Management

**User Story:** As a trader, I want to configure trading parameters for my TV alert automation through the Admin UI, so that I can control quantity, product type, and exchange without redeploying or changing environment files.

#### Acceptance Criteria

1. THE TV_Alert_Service SHALL allow configuring the default quantity (number of lots) for option orders via the Admin settings panel
2. THE TV_Alert_Service SHALL allow configuring the product type (MIS for intraday or NRML for positional) for option orders via the Admin settings panel
3. THE TV_Alert_Service SHALL allow configuring the exchange (NFO for NSE derivatives or BFO for BSE derivatives) for option orders via the Admin settings panel
4. THE TV_Alert_Service SHALL support enabling or disabling the TV alert options trading feature via the Admin settings panel
5. WHEN the feature is disabled in Admin settings, THE TV_Alert_Service SHALL reject incoming webhooks with an appropriate message and HTTP 403 status
6. THE TV_Alert_Service SHALL store configuration in the database settings table following the existing Settings model pattern with getter/setter functions and caching
