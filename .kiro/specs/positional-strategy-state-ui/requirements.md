# Requirements Document

## Introduction

This feature adds positional strategy awareness to the existing Python Strategy management interface. It introduces a state detail panel for positional strategies, a "suspended" status badge distinct from "stopped", auto-refreshing state data, a manual exit button with confirmation, and entry window progress display. The frontend is a React + TypeScript application using shadcn/ui components, following the patterns established in KillSwitch.tsx and PythonStrategyIndex.tsx. The backend APIs (GET `/strategy/<strategy_id>/state` and POST `/strategy/<strategy_id>/state/exit`) are already implemented by the positional-strategy-hosting spec.

## Glossary

- **Strategy_List_Page**: The PythonStrategyIndex component (`frontend/src/pages/python-strategy/PythonStrategyIndex.tsx`) that displays all Python strategies as cards with status badges and action buttons
- **State_Panel**: A detail panel or page component that displays the current positional strategy state — position status, entry price, instrument, quantity, unrealized P&L, high watermark, and trailing status
- **Status_Badge**: A visual indicator rendered as a Badge component showing the current strategy status (running, stopped, suspended, error, entry_expired, completed, suspended_stale, requires_manual_review)
- **State_API**: The GET `/strategy/<strategy_id>/state` backend endpoint that returns current positional strategy state as JSON
- **Exit_API**: The POST `/strategy/<strategy_id>/state/exit` backend endpoint that triggers manual position exit
- **Auto_Refresh**: A periodic polling mechanism that fetches fresh state data from the State_API at a configured interval while the State_Panel is open
- **Confirmation_Dialog**: A modal dialog component (using Dialog from shadcn/ui) that requires explicit user confirmation before executing a destructive action
- **Entry_Window**: The datetime range during which the strategy looks for trade entries, defined by STRATEGY_ENTRY_START_DATE_TIME and STRATEGY_ENTRY_END_DATE_TIME in the strategy configuration
- **Positional_Strategy**: A strategy with strategy_type "positional" that spans multiple market sessions, as opposed to "intraday" strategies that close within a single session
- **High_Watermark**: The highest option premium value recorded since position entry, used for trailing stop-loss calculations
- **Trailing_Status**: A boolean indicator showing whether the trailing stop-loss mode has been activated (target reached and TRAIL_GAP > 0)

## Requirements

### Requirement 1: Suspended Status Badge on Strategy List

**User Story:** As a positional trader, I want to see a distinct "Suspended" status badge on the strategy list for positional strategies that are paused overnight, so that I can distinguish them from strategies that have been manually stopped or finished.

#### Acceptance Criteria

1. WHEN the Strategy_List_Page renders a Positional_Strategy with positional_status "suspended", THE Status_Badge SHALL display the text "Suspended" with a distinct colour (amber/yellow) that is visually different from both the "Running" badge (green) and the "Stopped" badge (grey)
2. WHEN the Strategy_List_Page renders a Positional_Strategy with positional_status "error", THE Status_Badge SHALL display "Error" with a red/destructive colour consistent with existing error badge styling
3. WHEN the Strategy_List_Page renders a Positional_Strategy with positional_status "entry_expired", THE Status_Badge SHALL display "Entry Expired" with an orange colour
4. WHEN the Strategy_List_Page renders a Positional_Strategy with positional_status "completed", THE Status_Badge SHALL display "Completed" with a blue colour
5. WHEN the Strategy_List_Page renders a Positional_Strategy with positional_status "suspended_stale", THE Status_Badge SHALL display "Suspended (Stale)" with an amber colour and a tooltip explaining that the last state save may be incomplete
6. WHEN the Strategy_List_Page renders a Positional_Strategy with positional_status "requires_manual_review", THE Status_Badge SHALL display "Needs Review" with a red colour and a tooltip explaining that manual intervention is required
7. THE Strategy_List_Page SHALL render positional status badges only for strategies where strategy_type equals "positional" — intraday strategies SHALL continue using the existing status labels unchanged

### Requirement 2: Positional Strategy State Detail Panel

**User Story:** As a positional trader, I want to view a detailed state panel when clicking on a positional strategy, so that I can see entry price, instrument, quantity, unrealized P&L, high watermark, and trailing status without reading logs.

#### Acceptance Criteria

1. WHEN a user clicks on a Positional_Strategy card in the Strategy_List_Page, THE application SHALL navigate to the State_Panel for that strategy
2. WHEN the State_Panel loads, THE State_Panel SHALL call the State_API with the strategy_id and display the response data within 5 seconds
3. WHEN the State_API returns position_status "no_position", THE State_Panel SHALL display a message indicating no position is currently open and show any available entry window information
4. WHEN the State_API returns position_status "position_open", THE State_Panel SHALL display: entry_price formatted as currency (INR), entry_timestamp formatted in IST (DD MMM YYYY HH:MM), instrument_symbol as text, quantity as integer, unrealized_pnl formatted as currency with green colour for positive values and red colour for negative values, and last_updated timestamp in IST
5. WHEN the State_API returns position_status "position_open", THE State_Panel SHALL display: high_watermark value formatted as currency, and trailing_active as a visual indicator (badge or icon) showing whether trailing stop-loss mode is active
6. WHEN the State_API returns position_status "position_closed", THE State_Panel SHALL display the final trade details (entry_price, instrument_symbol, quantity) with a "Position Closed" indicator
7. IF the State_API returns an error response or the request fails, THEN THE State_Panel SHALL display an error message with a retry button and SHALL NOT show stale data from a previous request
8. THE State_Panel SHALL include a back navigation link to return to the Strategy_List_Page, consistent with the ArrowLeft pattern used in KillSwitch.tsx
9. WHEN the State_API returns is_live as false (strategy process not running), THE State_Panel SHALL display a notice indicating the state is from the last persisted snapshot rather than live data

### Requirement 3: Manual Exit Button with Confirmation

**User Story:** As a positional trader, I want a Manual Exit button on the state panel that closes my position via the backend API, so that I can exit a trade immediately without accessing broker terminals or log files.

#### Acceptance Criteria

1. WHILE position_status is "position_open", THE State_Panel SHALL display a "Manual Exit" button styled as a destructive action (red variant)
2. WHEN the user clicks the Manual Exit button, THE State_Panel SHALL display a Confirmation_Dialog with the text "Are you sure you want to exit this position? This will place a market sell order for {quantity} units of {instrument_symbol}."
3. WHEN the user confirms the exit in the Confirmation_Dialog, THE State_Panel SHALL call the Exit_API with the strategy_id and display a loading state on the button until the response is received
4. WHEN the Exit_API returns a success response, THE State_Panel SHALL display a success toast notification, refresh the state data from the State_API, and update the panel to reflect the closed position
5. IF the Exit_API returns an error response, THEN THE State_Panel SHALL display an error toast notification with the error message from the response and SHALL NOT change the displayed position state
6. WHILE position_status is "no_position" or "position_closed", THE State_Panel SHALL NOT display the Manual Exit button
7. WHILE an exit request is in progress (loading state), THE Manual Exit button SHALL be disabled to prevent duplicate exit requests

### Requirement 4: Auto-Refresh State Data

**User Story:** As a positional trader monitoring my strategy during market hours, I want the state panel to automatically refresh every 30 seconds, so that I see updated unrealized P&L and trailing status without manually refreshing.

#### Acceptance Criteria

1. WHILE the State_Panel is open and visible, THE State_Panel SHALL poll the State_API every 30 seconds and update the displayed data with the fresh response
2. WHEN the State_Panel is navigated away from or the browser tab becomes hidden, THE Auto_Refresh SHALL stop polling to avoid unnecessary network requests
3. WHEN the user navigates back to the State_Panel or the browser tab becomes visible again, THE Auto_Refresh SHALL resume polling at the 30-second interval
4. WHILE an Auto_Refresh poll is in progress, THE State_Panel SHALL display a subtle refresh indicator (spinning icon or pulsing dot) without disrupting the existing content layout
5. IF an Auto_Refresh poll fails due to network error, THEN THE State_Panel SHALL retain the last successfully fetched data, display a warning indicator that the data may be stale, and continue attempting the next scheduled poll
6. THE State_Panel SHALL provide a manual refresh button that triggers an immediate State_API call independent of the auto-refresh timer and resets the 30-second countdown
7. WHEN the State_API response data has not changed from the previous poll (same last_updated timestamp), THE State_Panel SHALL NOT re-render the data fields to avoid visual flicker

### Requirement 5: Entry Window Progress Display

**User Story:** As a positional trader waiting for a trade entry, I want to see how many days remain in the entry window or if it has expired, so that I know whether the strategy is still looking for entries.

#### Acceptance Criteria

1. WHEN the State_Panel displays a Positional_Strategy with position_status "no_position" and the entry window has not expired, THE State_Panel SHALL display the number of calendar days remaining in the entry window calculated as the difference between STRATEGY_ENTRY_END_DATE_TIME and the current date
2. WHEN the entry window has 1 day remaining, THE State_Panel SHALL display "1 day remaining" (singular form)
3. WHEN the entry window has more than 1 day remaining, THE State_Panel SHALL display "{N} days remaining" (plural form)
4. WHEN the current datetime has passed STRATEGY_ENTRY_END_DATE_TIME without an entry, THE State_Panel SHALL display "Entry Expired" with a visual indicator (orange badge or text) matching the entry_expired status styling
5. WHEN position_status is "position_open" or "position_closed", THE State_Panel SHALL NOT display entry window progress information since the entry has already occurred
6. THE State_Panel SHALL display the entry window dates (start and end) as a reference alongside the remaining days calculation, formatted as "DD MMM YYYY"

### Requirement 6: Editable Entry and Exit Datetime Configuration

**User Story:** As a positional trader, I want to edit the entry window dates (start/end) and exit datetime directly from the state panel, so that I can adjust my strategy timing without editing environment variables or restarting processes manually.

#### Acceptance Criteria

1. WHILE position_status is "no_position" (no entry taken), THE State_Panel SHALL display editable datetime fields for STRATEGY_ENTRY_START_DATE_TIME, STRATEGY_ENTRY_END_DATE_TIME, and STRATEGY_EXIT_DATE_TIME with the current configured values pre-filled
2. WHEN the user modifies any datetime field, THE State_Panel SHALL validate the format as YYYY-MM-DD HH:MM (24-hour, IST) and display an inline validation error if the format is invalid
3. WHEN the user modifies datetime fields, THE State_Panel SHALL validate chronological ordering (entry_start < entry_end < exit_dt) and display an inline error identifying which ordering constraint is violated
4. WHEN the user clicks a "Save" button after editing valid datetime values, THE State_Panel SHALL call the backend API to update the strategy configuration and display a success toast on completion
5. IF the backend returns an error when saving datetime changes, THEN THE State_Panel SHALL display an error toast with the error message and revert the fields to the last known saved values
6. WHILE position_status is "position_open" or "position_closed" (entry already taken), THE State_Panel SHALL display the entry datetime fields as read-only (non-editable) with a visual indicator that editing is locked
7. WHILE position_status is "position_open", THE State_Panel SHALL allow editing of STRATEGY_EXIT_DATE_TIME only, since the exit date may need adjustment after entry is taken
8. WHEN STRATEGY_EXIT_DATE_TIME is edited while a position is open, THE State_Panel SHALL validate that the new exit datetime is in the future (after the current datetime) before allowing save

