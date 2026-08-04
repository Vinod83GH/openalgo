# Implementation Plan: Positional Strategy State UI

## Overview

This plan implements the positional strategy state UI feature: extending the Python Strategy management interface with positional status badges, a state detail panel, manual exit with confirmation, auto-refresh polling, entry window progress, and editable datetime configuration. The frontend is React + TypeScript using shadcn/ui components, and the backend APIs for state/exit are already implemented. One new backend endpoint (PUT `/python/strategy/:id/config/datetime`) is needed for datetime config updates.

## Tasks

- [x] 1. Extend type definitions and API client
  - [x] 1.1 Add positional strategy types to `frontend/src/types/python-strategy.ts`
    - Add `PositionalStatus` type union (suspended, running, error, state_save_failed, requires_manual_review, entry_expired, completed, suspended_stale)
    - Add `strategy_type` and `positional_status` optional fields to `PythonStrategy` interface
    - Add `PositionalState` interface for State_API response
    - Add `DatetimeConfigUpdate` interface for config update request
    - Add `POSITIONAL_STATUS_COLORS`, `POSITIONAL_STATUS_LABELS`, and `POSITIONAL_STATUS_TOOLTIPS` maps
    - _Requirements: 1.1, 1.2, 1.3, 1.4, 1.5, 1.6, 1.7_

  - [x] 1.2 Add API client methods to `frontend/src/api/python-strategy.ts`
    - Add `getPositionalState(strategyId)` method calling GET `/python/strategy/:id/state`
    - Add `exitPosition(strategyId)` method calling POST `/python/strategy/:id/state/exit`
    - Add `updateDatetimeConfig(strategyId, config)` method calling PUT `/python/strategy/:id/config/datetime`
    - _Requirements: 2.2, 3.3, 6.4_

- [x] 2. Add utility functions and route configuration
  - [x] 2.1 Create utility functions file `frontend/src/pages/python-strategy/positional-utils.ts`
    - Implement `formatINR(value: number): string` for INR currency formatting
    - Implement `formatIST(isoString: string): string` for ISO to "DD MMM YYYY HH:MM" IST conversion
    - Implement `getDaysRemaining(endDateStr: string): number` for entry window countdown
    - Implement `pluralizeDays(n: number): string` for singular/plural "day"/"days"
    - Implement `isValidDatetimeFormat(value: string): boolean` for YYYY-MM-DD HH:MM validation
    - Implement `isChronologicalOrder(start, end, exit): { valid: boolean; error?: string }` for ordering validation
    - Implement `isFutureDatetime(value: string): boolean` for future date check
    - _Requirements: 2.4, 5.1, 5.2, 5.3, 5.6, 6.2, 6.3, 6.8_

  - [x] 2.2 Add route for PositionalStrategyState in `frontend/src/App.tsx`
    - Add lazy import for `PositionalStrategyState` component
    - Add route `/python/:strategyId/state` inside the Layout wrapper alongside existing python strategy routes
    - _Requirements: 2.1, 2.8_

- [x] 3. Implement positional status badges on strategy list
  - [x] 3.1 Modify `frontend/src/pages/python-strategy/PythonStrategyIndex.tsx` for positional badges
    - Import `POSITIONAL_STATUS_COLORS`, `POSITIONAL_STATUS_LABELS`, `POSITIONAL_STATUS_TOOLTIPS` from types
    - Conditionally use positional status maps when `strategy_type === "positional"` and `positional_status` is defined
    - Add Tooltip wrapper for `suspended_stale` and `requires_manual_review` statuses
    - Add click handler on positional strategy cards to navigate to `/python/:strategyId/state`
    - Retain existing badge behaviour for non-positional (intraday) strategies
    - _Requirements: 1.1, 1.2, 1.3, 1.4, 1.5, 1.6, 1.7_

  - [x]* 3.2 Write property tests for status badge mapping (Properties 1 & 2)
    - **Property 1: Positional Status Badge Mapping Completeness** — verify all PositionalStatus values produce non-empty label and colour
    - **Validates: Requirements 1.1, 1.2, 1.3, 1.4, 1.5, 1.6**
    - **Property 2: Strategy Type Gating for Badge Selection** — verify positional maps used iff strategy_type === "positional"
    - **Validates: Requirements 1.7**

- [x] 4. Implement PositionalStrategyState page component
  - [x] 4.1 Create `frontend/src/pages/python-strategy/PositionalStrategyState.tsx` with core layout
    - Implement page header with ArrowLeft back navigation to `/python` and strategy name display
    - Implement state fetching on mount using `getPositionalState` API
    - Display loading spinner while fetching
    - Display error state with retry button on API failure
    - Display "not available for non-positional strategies" message when applicable
    - Show `is_live` false notice ("showing persisted snapshot")
    - _Requirements: 2.1, 2.2, 2.7, 2.8, 2.9_

  - [x] 4.2 Implement position state display section in PositionalStrategyState
    - When `position_status === "no_position"`: show "No position open" message with entry window info
    - When `position_status === "position_open"`: show entry_price (INR), entry_timestamp (IST), instrument_symbol, quantity, unrealized_pnl (green/red colour), high_watermark, trailing_active indicator
    - When `position_status === "position_closed"`: show final trade details with "Position Closed" badge
    - Format all currency values using `formatINR`, timestamps using `formatIST`
    - _Requirements: 2.3, 2.4, 2.5, 2.6_

  - [x]* 4.3 Write property tests for utility functions (Properties 5, 6, 7, 8, 9, 11)
    - **Property 5: Days Remaining Calculation and Pluralization**
    - **Validates: Requirements 5.1, 5.2, 5.3**
    - **Property 6: Date Formatting to DD MMM YYYY**
    - **Validates: Requirements 5.6**
    - **Property 7: Datetime Format Validation**
    - **Validates: Requirements 6.2**
    - **Property 8: Chronological Ordering Validation**
    - **Validates: Requirements 6.3**
    - **Property 9: Future Datetime Validation for Exit**
    - **Validates: Requirements 6.8**
    - **Property 11: Currency Formatting for P&L Display**
    - **Validates: Requirements 2.4**

- [x] 5. Checkpoint - Ensure all tests pass
  - Ensure all tests pass, ask the user if questions arise.

- [x] 6. Implement manual exit with confirmation
  - [x] 6.1 Add manual exit button and confirmation dialog to PositionalStrategyState
    - Render "Manual Exit" button (destructive/red variant) only when `position_status === "position_open"`
    - On button click, show confirmation Dialog with interpolated text: "Are you sure you want to exit this position? This will place a market sell order for {quantity} units of {instrument_symbol}."
    - On confirm: call `exitPosition` API, show loading state on button, disable button during request
    - On success: show success toast, refetch state, update panel
    - On error: show error toast with backend message, keep state unchanged
    - Hide button when `position_status` is "no_position" or "position_closed"
    - _Requirements: 3.1, 3.2, 3.3, 3.4, 3.5, 3.6, 3.7_

  - [x]* 6.2 Write property tests for manual exit visibility and dialog (Properties 3 & 4)
    - **Property 3: Manual Exit Button Visibility** — button visible iff position_status === "position_open"
    - **Validates: Requirements 3.1, 3.6**
    - **Property 4: Exit Confirmation Dialog Text Interpolation** — dialog text contains exact instrument_symbol and quantity
    - **Validates: Requirements 3.2**

- [x] 7. Implement auto-refresh polling
  - [x] 7.1 Add auto-refresh logic to PositionalStrategyState
    - Implement 30-second polling interval using `setInterval` / `useEffect`
    - Listen to `visibilitychange` event: stop polling when tab hidden, resume when visible
    - Show subtle refresh indicator (spinning icon) during poll without disrupting layout
    - On poll failure: retain last data, show "Data may be stale" warning badge, continue next poll
    - Add manual refresh button that triggers immediate fetch and resets countdown
    - Skip re-render when `last_updated` timestamp matches previous response
    - Clean up interval and event listeners on unmount
    - _Requirements: 4.1, 4.2, 4.3, 4.4, 4.5, 4.6, 4.7_

  - [x]* 7.2 Write property test for no re-render on unchanged state (Property 10)
    - **Property 10: No Re-render on Unchanged State** — if two consecutive responses have same last_updated, state data should not update
    - **Validates: Requirements 4.7**

- [x] 8. Implement entry window progress display
  - [x] 8.1 Add entry window progress section to PositionalStrategyState
    - When `position_status === "no_position"` and entry window not expired: show "{N} days remaining" (plural) or "1 day remaining" (singular)
    - When entry window expired: show "Entry Expired" with orange badge
    - When `position_status === "position_open"` or `"position_closed"`: hide entry window section
    - Display entry window start and end dates formatted as "DD MMM YYYY"
    - _Requirements: 5.1, 5.2, 5.3, 5.4, 5.5, 5.6_

- [x] 9. Implement editable datetime configuration
  - [x] 9.1 Create backend endpoint PUT `/python/strategy/<strategy_id>/config/datetime` in `blueprints/python_strategy.py`
    - Accept JSON body with optional fields: `entry_start_dt`, `entry_end_dt`, `exit_dt`
    - Validate format (YYYY-MM-DD HH:MM), chronological ordering, and future constraint for exit_dt
    - Update the strategy's env_vars (STRATEGY_ENTRY_START_DATE_TIME, STRATEGY_ENTRY_END_DATE_TIME, STRATEGY_EXIT_DATE_TIME)
    - Return 409 if strategy process is currently running and datetime change is not allowed
    - Return success response on valid update
    - _Requirements: 6.4, 6.5_

  - [x] 9.2 Add datetime config editing UI to PositionalStrategyState
    - When `position_status === "no_position"`: show editable datetime inputs for entry_start, entry_end, and exit_dt pre-filled with current values
    - When `position_status === "position_open"`: show entry_start and entry_end as read-only, exit_dt as editable
    - When `position_status === "position_closed"`: show all fields as read-only
    - Validate format inline on change (YYYY-MM-DD HH:MM pattern)
    - Validate chronological ordering inline (entry_start < entry_end < exit_dt) with specific error messages
    - Validate exit_dt is in the future when position is open
    - Save button calls `updateDatetimeConfig` API, shows success toast on success
    - On save error: show error toast, revert fields to last saved values
    - _Requirements: 6.1, 6.2, 6.3, 6.4, 6.5, 6.6, 6.7, 6.8_

- [x] 10. Checkpoint - Ensure all tests pass
  - Ensure all tests pass, ask the user if questions arise.

- [x] 11. Integration wiring and final verification
  - [x] 11.1 Wire all components together and verify end-to-end navigation
    - Verify clicking a positional strategy card in PythonStrategyIndex navigates to the state panel
    - Verify back navigation returns to strategy list
    - Verify all sections render correctly based on position_status
    - Verify auto-refresh, manual exit, and datetime config flows work together
    - Ensure no console errors or TypeScript compilation issues
    - _Requirements: 2.1, 2.8, 1.7_

  - [x]* 11.2 Write unit tests for PositionalStrategyState component
    - Test loading state renders spinner
    - Test "no position" state renders correctly
    - Test "position_open" state renders all position fields
    - Test "position_closed" state renders final details
    - Test error state shows retry button
    - Test back navigation link renders correctly
    - Test is_live=false shows persisted snapshot notice
    - Test manual exit button hidden when no position
    - Test confirmation dialog shows on exit button click
    - Test exit button disabled during loading
    - Test positional strategy card navigation from list
    - _Requirements: 2.1, 2.2, 2.3, 2.4, 2.5, 2.6, 2.7, 2.8, 2.9, 3.1, 3.2, 3.6, 3.7_

  - [x]* 11.3 Write integration tests for auto-refresh and full flows
    - Test auto-refresh polls every 30 seconds (using fake timers)
    - Test polling stops on visibility hidden and resumes on visible
    - Test full exit flow: click → confirm → API success → toast → state refresh
    - Test full datetime config flow: edit → validate → save → toast
    - Test strategy list shows positional badges for positional strategies only
    - _Requirements: 4.1, 4.2, 4.3, 3.3, 3.4, 6.4, 1.7_

- [x] 12. Final checkpoint - Ensure all tests pass
  - Ensure all tests pass, ask the user if questions arise.

## Notes

- Tasks marked with `*` are optional and can be skipped for faster MVP
- Each task references specific requirements for traceability
- Checkpoints ensure incremental validation
- Property tests validate universal correctness properties using fast-check
- Unit tests validate specific examples and edge cases using React Testing Library
- Backend APIs for GET state and POST exit are already implemented by the positional-strategy-hosting spec
- The PUT datetime config endpoint (task 9.1) is the only new backend work needed
- The frontend follows established patterns from KillSwitch.tsx and PythonStrategyIndex.tsx

## Task Dependency Graph

```json
{
  "waves": [
    { "id": 0, "tasks": ["1.1"] },
    { "id": 1, "tasks": ["1.2", "2.1"] },
    { "id": 2, "tasks": ["2.2", "3.1"] },
    { "id": 3, "tasks": ["3.2", "4.1", "9.1"] },
    { "id": 4, "tasks": ["4.2", "4.3"] },
    { "id": 5, "tasks": ["6.1", "8.1"] },
    { "id": 6, "tasks": ["6.2", "7.1", "9.2"] },
    { "id": 7, "tasks": ["7.2", "11.1"] },
    { "id": 8, "tasks": ["11.2", "11.3"] }
  ]
}
```
