# Requirements Document

## Introduction

The Paper Journal UI is a frontend page at `/paper-journal` that displays paper trade journal data in a filterable, exportable table with summary statistics. It integrates with the existing Paper Trade Journal backend API (`/api/v1/paperjournal/`) and follows established page patterns (KillSwitch, Analyzer). The page is accessible via the profile dropdown menu in the navigation bar.

## Glossary

- **Paper_Journal_Page**: The React page component rendered at the `/paper-journal` route, responsible for displaying trade journal data with filters, summary cards, and a trade table.
- **Filter_Panel**: The section of the Paper_Journal_Page containing date range inputs, strategy dropdown, and an Apply button for filtering trade data.
- **Summary_Cards**: A row of Card components displaying aggregated trade statistics (Total Trades, Total P&L, Win Rate, Winning Trades, Losing Trades).
- **Trade_Table**: A Table component displaying individual trade records with columns for all trade fields.
- **Strategy_Dropdown**: A Select component populated with distinct strategy names fetched from the backend.
- **CSV_Export**: A button that triggers download of the currently filtered trade data as a CSV file.
- **Navigation_Config**: The `navigation.ts` configuration file that defines profile dropdown menu items.
- **apiClient**: The existing Axios-based HTTP client configured for authenticated API calls to `/api/v1` endpoints.
- **webClient**: The existing Axios-based HTTP client for session-based routes with CSRF support.

## Requirements

### Requirement 1: Navigation Entry

**User Story:** As a user, I want to access the Paper Journal page from the profile dropdown menu, so that I can quickly navigate to my paper trade history.

#### Acceptance Criteria

1. THE Navigation_Config SHALL include a menu item with href `/paper-journal`, label "Paper Journal", and an appropriate Lucide icon in the profileMenuItems array.
2. WHEN a user clicks the "Paper Journal" menu item, THE Paper_Journal_Page SHALL render at the `/paper-journal` route.

### Requirement 2: Page Layout and Structure

**User Story:** As a user, I want the Paper Journal page to follow the same layout conventions as existing pages, so that the experience is consistent.

#### Acceptance Criteria

1. THE Paper_Journal_Page SHALL render a page header with title and description text.
2. THE Paper_Journal_Page SHALL render the Filter_Panel above the Summary_Cards.
3. THE Paper_Journal_Page SHALL render the Summary_Cards above the Trade_Table.
4. THE Paper_Journal_Page SHALL use shadcn/ui Card, Table, Select, Button, and Badge components.
5. THE Paper_Journal_Page SHALL follow the container and spacing patterns used by the Analyzer and KillSwitch pages.

### Requirement 3: Date Range Filter

**User Story:** As a user, I want to filter trades by date range, so that I can review my trading performance for specific time periods.

#### Acceptance Criteria

1. THE Filter_Panel SHALL display a Start Date input and an End Date input using native HTML date input elements.
2. WHEN the Paper_Journal_Page loads, THE Filter_Panel SHALL set both Start Date and End Date to today's date as the default value.
3. THE Filter_Panel SHALL allow the user to select any valid date for Start Date and End Date independently.

### Requirement 4: Strategy Name Filter

**User Story:** As a user, I want to filter trades by strategy name, so that I can analyze the performance of individual strategies.

#### Acceptance Criteria

1. THE Filter_Panel SHALL display a Strategy_Dropdown with an "All Strategies" default option.
2. WHEN the Paper_Journal_Page loads, THE Paper_Journal_Page SHALL fetch distinct strategy names via GET `/api/v1/paperjournal/strategies`.
3. WHEN the strategy names are fetched successfully, THE Strategy_Dropdown SHALL populate its options with the returned strategy names.
4. IF the GET `/api/v1/paperjournal/strategies` request fails, THEN THE Strategy_Dropdown SHALL display only the "All Strategies" default option.

### Requirement 5: Apply Filter Action

**User Story:** As a user, I want to apply my selected filters to refresh the data, so that I see only the trades matching my criteria.

#### Acceptance Criteria

1. THE Filter_Panel SHALL display an Apply button.
2. WHEN the user clicks the Apply button, THE Paper_Journal_Page SHALL fetch trades from GET `/api/v1/paperjournal/trades` with the selected start_date, end_date, and strategy_name parameters.
3. WHEN the user clicks the Apply button, THE Paper_Journal_Page SHALL fetch summary data from GET `/api/v1/paperjournal/summary` with the same filter parameters.
4. WHILE the trade and summary data is being fetched, THE Paper_Journal_Page SHALL display a loading indicator.

### Requirement 6: Auto-Fetch on Page Load

**User Story:** As a user, I want to see today's trades immediately when I open the page, so that I do not need to manually apply filters for the current day.

#### Acceptance Criteria

1. WHEN the Paper_Journal_Page mounts, THE Paper_Journal_Page SHALL automatically fetch trades and summary data for today's date.
2. THE Paper_Journal_Page SHALL use the same API endpoints (GET `/api/v1/paperjournal/trades` and GET `/api/v1/paperjournal/summary`) with today's date as both start_date and end_date for the initial load.

### Requirement 7: Summary Cards Display

**User Story:** As a user, I want to see a high-level summary of my trading performance, so that I can quickly assess my results without examining individual trades.

#### Acceptance Criteria

1. THE Summary_Cards SHALL display a "Total Trades" card showing the total number of trades returned by the summary endpoint.
2. THE Summary_Cards SHALL display a "Total P&L" card showing the aggregate profit and loss value.
3. WHEN the Total P&L value is positive, THE Summary_Cards SHALL render the value in green color.
4. WHEN the Total P&L value is negative, THE Summary_Cards SHALL render the value in red color.
5. THE Summary_Cards SHALL display a "Win Rate %" card showing the win rate percentage.
6. THE Summary_Cards SHALL display a "Winning Trades" card showing the count of profitable trades.
7. THE Summary_Cards SHALL display a "Losing Trades" card showing the count of unprofitable trades.

### Requirement 8: Trade Table Display

**User Story:** As a user, I want to see detailed information about each trade in a table, so that I can review individual trade entries and exits.

#### Acceptance Criteria

1. THE Trade_Table SHALL display columns: Date, Strategy, Direction, Entry Time, Entry Spot, Option Symbol, Entry Price, Exit Time, Exit Spot, Exit Price, P&L, Exit Reason.
2. THE Trade_Table SHALL display one row per trade record returned from the API.
3. WHEN the P&L value for a trade is positive, THE Trade_Table SHALL render that P&L cell in green color.
4. WHEN the P&L value for a trade is negative, THE Trade_Table SHALL render that P&L cell in red color.
5. WHEN no trades match the current filters, THE Trade_Table SHALL display a message indicating no trades were found.
6. THE Trade_Table SHALL support horizontal scrolling on smaller viewports to accommodate all columns.

### Requirement 9: CSV Export

**User Story:** As a user, I want to export my filtered trade data as a CSV file, so that I can analyze trades in external tools like spreadsheets.

#### Acceptance Criteria

1. THE Paper_Journal_Page SHALL display a CSV Export button.
2. WHEN the user clicks the CSV Export button, THE Paper_Journal_Page SHALL generate a CSV file from the currently displayed trade data.
3. THE CSV file SHALL contain all columns displayed in the Trade_Table with matching headers.
4. THE CSV file SHALL contain only the trades currently displayed (matching the active filters).

### Requirement 10: Backend Strategies Endpoint

**User Story:** As a frontend developer, I want an API endpoint that returns distinct strategy names, so that the Strategy_Dropdown can be populated with valid options.

#### Acceptance Criteria

1. THE backend SHALL expose a GET `/api/v1/paperjournal/strategies` endpoint.
2. WHEN the endpoint receives a valid authenticated request, THE backend SHALL return a JSON response containing a list of distinct strategy_name values from the paper_trades table.
3. THE response SHALL follow the format `{"status": "success", "data": ["strategy1", "strategy2", ...]}`.
4. IF no trades exist in the paper_trades table, THEN THE endpoint SHALL return an empty list `{"status": "success", "data": []}`.
5. THE endpoint SHALL require API key authentication consistent with other paperjournal endpoints.

### Requirement 11: API Authentication

**User Story:** As a user, I want API calls from the Paper Journal page to be authenticated using the existing session mechanism, so that my data is protected.

#### Acceptance Criteria

1. THE Paper_Journal_Page SHALL use the existing webClient or apiClient for all API calls to the paperjournal endpoints.
2. THE Paper_Journal_Page SHALL rely on cookie-based session authentication (withCredentials) for API requests.
3. IF an API request returns a 401 status, THEN THE Paper_Journal_Page SHALL redirect the user to the login page.

### Requirement 12: Error Handling

**User Story:** As a user, I want to see meaningful feedback when something goes wrong, so that I understand the current state of the page.

#### Acceptance Criteria

1. IF the trades fetch request fails, THEN THE Paper_Journal_Page SHALL display an error message to the user.
2. IF the summary fetch request fails, THEN THE Summary_Cards SHALL display zero or placeholder values.
3. IF the strategies fetch request fails, THEN THE Strategy_Dropdown SHALL remain functional with only the "All Strategies" option available.
