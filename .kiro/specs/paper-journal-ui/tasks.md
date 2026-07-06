# Implementation Plan: Paper Journal UI

## Overview

Add a Paper Journal page to the frontend that displays paper trade data with date/strategy filters, summary statistics cards, a trade table, and CSV export. Requires one new backend endpoint (`GET /strategies`) and a new React page wired into the existing routing and navigation.

## Tasks

- [ ] 1. Backend: Add strategies endpoint
  - [ ] 1.1 Add `get_distinct_strategies()` function to `database/paper_trade_db.py`
    - Query distinct `strategy_name` values from `paper_trades` table
    - Order alphabetically, filter out None values
    - _Requirements: 10.2, 10.3, 10.4_

  - [ ] 1.2 Add `list_strategies()` function to `services/paper_trade_journal_service.py`
    - Import and delegate to `get_distinct_strategies()`
    - _Requirements: 10.2_

  - [ ] 1.3 Add `GET /strategies` route to `blueprints/paper_journal.py`
    - Use `_validate_api_key_from_params()` for auth
    - Return `{"status": "success", "data": [...]}` format
    - Handle errors with 500 response
    - _Requirements: 10.1, 10.2, 10.3, 10.4, 10.5_

- [ ] 2. Frontend: Types and API module
  - [ ] 2.1 Create `frontend/src/types/paper-journal.ts`
    - Define `PaperTrade` interface with all trade fields
    - Define `TradeSummary` interface with summary fields and `per_strategy` breakdown
    - _Requirements: 8.1, 7.1_

  - [ ] 2.2 Create `frontend/src/api/paper-journal.ts`
    - Import `apiClient` from `@/api/client`
    - Implement `getStrategies()` — GET `/paperjournal/strategies`
    - Implement `getTrades(params)` — GET `/paperjournal/trades` with query params
    - Implement `getSummary(params)` — GET `/paperjournal/summary` with query params
    - Handle `strategy_name` param only when not "all"
    - _Requirements: 4.2, 5.2, 5.3, 6.2, 11.1, 11.2_

- [ ] 3. Frontend: PaperJournal page component
  - [ ] 3.1 Create `frontend/src/pages/PaperJournal.tsx` with filter panel, summary cards, trade table, and CSV export
    - Filter panel: native date inputs (default today), strategy Select dropdown, Apply button
    - Summary cards: Total Trades, Total P&L (green/red), Win Rate %, Winning Trades, Losing Trades
    - Trade table: all columns from requirement 8.1, P&L color coding, empty state message, horizontal scroll
    - CSV export button: client-side CSV generation from displayed trades
    - Auto-fetch on mount with today's date
    - Loading state and error handling
    - _Requirements: 2.1–2.5, 3.1–3.3, 4.1–4.4, 5.1–5.4, 6.1–6.2, 7.1–7.7, 8.1–8.6, 9.1–9.4, 12.1–12.3_

- [ ] 4. Frontend: Route and navigation wiring
  - [ ] 4.1 Add route and lazy import in `frontend/src/App.tsx`
    - Add `const PaperJournal = lazy(() => import('@/pages/PaperJournal'))` 
    - Add `<Route path="/paper-journal" element={<PaperJournal />} />` inside `<Layout>` protected routes
    - _Requirements: 1.2_

  - [ ] 4.2 Add nav entry in `frontend/src/config/navigation.ts`
    - Add `{ href: '/paper-journal', label: 'Paper Journal', icon: FileText }` to `profileMenuItems`
    - _Requirements: 1.1_

- [ ] 5. Checkpoint
  - Ensure all code compiles without errors (Python + TypeScript), ask the user if questions arise.

## Notes

- The backend uses API key auth via query param (`?apikey=...`); the frontend `apiClient` already appends this
- The design uses `apiClient` (base URL `/api/v1`, `withCredentials: true`) for all paperjournal calls
- No database migrations needed — the `paper_trades` table and indexes already exist
- The page follows Analyzer/KillSwitch patterns: single page component with local state, shadcn/ui components
- CSV export is entirely client-side from the in-memory trades array

## Task Dependency Graph

```json
{
  "waves": [
    { "id": 0, "tasks": ["1.1", "2.1"] },
    { "id": 1, "tasks": ["1.2", "2.2"] },
    { "id": 2, "tasks": ["1.3", "3.1"] },
    { "id": 3, "tasks": ["4.1", "4.2"] }
  ]
}
```
