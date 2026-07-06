# Design Document: Paper Journal UI

## Overview

The Paper Journal UI is a React page at `/paper-journal` that displays paper trade journal data with filterable views, summary statistics, and CSV export. It follows established patterns from the Analyzer and KillSwitch pages, using shadcn/ui components with the `webClient` for session-based API calls.

## Architecture

### Component Hierarchy

```
App.tsx (route: /paper-journal)
└── PaperJournal.tsx (page component)
    ├── Filter Panel (Card)
    │   ├── Start Date (native HTML date input)
    │   ├── End Date (native HTML date input)
    │   ├── Strategy Dropdown (Select)
    │   └── Apply Button (Button)
    ├── Summary Cards (grid of Cards)
    │   ├── Total Trades
    │   ├── Total P&L (green/red colored)
    │   ├── Win Rate %
    │   ├── Winning Trades
    │   └── Losing Trades
    ├── CSV Export Button
    └── Trade Table (Table)
        └── Rows (one per trade)
```

### Data Flow

```
[Page Mount] → fetchStrategies() + fetchData(today, today)
[Apply Click] → fetchData(startDate, endDate, strategy?)
[Export Click] → generateCSV(currentTrades)
```

## Components

### PaperJournal Page (`frontend/src/pages/PaperJournal.tsx`)

Single page component following the Analyzer pattern. Uses `useState` for local state and `useEffect` for auto-fetch on mount.

```typescript
import { Download, Filter, FileText, TrendingUp, TrendingDown, Activity, Target } from 'lucide-react'
import { useEffect, useState } from 'react'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'
import {
  Table, TableBody, TableCell, TableHead, TableHeader, TableRow,
} from '@/components/ui/table'
import { Label } from '@/components/ui/label'
import { webClient } from '@/api/client'
import { showToast } from '@/utils/toast'
```

**State:**
```typescript
interface PaperTrade {
  trade_id: number
  created_at: string | null
  trade_date: string | null
  strategy_name: string
  direction: string | null
  entry_time: string | null
  entry_spot_price: number | null
  entry_option_symbol: string | null
  entry_option_price: number | null
  entry_quantity: number | null
  entry_action: string | null
  exit_time: string | null
  exit_spot_price: number | null
  exit_option_price: number | null
  exit_reason: string | null
  pnl: number | null
  custom_metadata: Record<string, unknown> | null
}

interface TradeSummary {
  total_trades: number
  total_pnl: number
  winning_trades: number
  losing_trades: number
  win_rate: number
  per_strategy: Record<string, unknown>
}

// Component state
const [trades, setTrades] = useState<PaperTrade[]>([])
const [summary, setSummary] = useState<TradeSummary | null>(null)
const [strategies, setStrategies] = useState<string[]>([])
const [startDate, setStartDate] = useState<string>(getTodayString())
const [endDate, setEndDate] = useState<string>(getTodayString())
const [selectedStrategy, setSelectedStrategy] = useState<string>('all')
const [isLoading, setIsLoading] = useState(true)
const [error, setError] = useState<string | null>(null)
```

**Helper:**
```typescript
function getTodayString(): string {
  return new Date().toISOString().split('T')[0] // YYYY-MM-DD
}
```

### API Integration (`frontend/src/api/paper-journal.ts`)

Dedicated API module using `apiClient` (base URL `/api/v1`) for the paperjournal endpoints:

```typescript
import { apiClient } from './client'

export const paperJournalApi = {
  getStrategies: async (): Promise<string[]> => {
    const response = await apiClient.get<{ status: string; data: string[] }>(
      '/paperjournal/strategies'
    )
    return response.data.data || []
  },

  getTrades: async (params: {
    start_date: string
    end_date: string
    strategy_name?: string
  }): Promise<PaperTrade[]> => {
    const queryParams = new URLSearchParams()
    queryParams.append('start_date', params.start_date)
    queryParams.append('end_date', params.end_date)
    if (params.strategy_name && params.strategy_name !== 'all') {
      queryParams.append('strategy_name', params.strategy_name)
    }
    const response = await apiClient.get<{ status: string; data: PaperTrade[] }>(
      `/paperjournal/trades?${queryParams}`
    )
    return response.data.data || []
  },

  getSummary: async (params: {
    start_date: string
    end_date: string
    strategy_name?: string
  }): Promise<TradeSummary> => {
    const queryParams = new URLSearchParams()
    queryParams.append('start_date', params.start_date)
    queryParams.append('end_date', params.end_date)
    if (params.strategy_name && params.strategy_name !== 'all') {
      queryParams.append('strategy_name', params.strategy_name)
    }
    const response = await apiClient.get<{ status: string; data: TradeSummary }>(
      `/paperjournal/summary?${queryParams}`
    )
    return response.data.data
  },
}
```

**Note:** The existing `apiClient` has `baseURL: /api/v1` and includes `withCredentials: true`. However, the paperjournal endpoints require an `apikey` query parameter for authentication. Since the frontend page is for authenticated web users, the backend strategies endpoint will be modified to support session-based auth (checking `session['user']`) in addition to API key auth, consistent with how other page-level endpoints work in this project (Analyzer uses `fetch` with `credentials: 'include'` to session-authenticated routes).

**Revised approach:** Following the Analyzer pattern, the new `/strategies` endpoint and the existing `/trades` and `/summary` endpoints will be called using `apiClient` which sends cookies. The backend route will accept either API key OR session-based auth.

### Backend: Strategies Endpoint

Add to `blueprints/paper_journal.py`:

```python
@paper_journal_bp.route("/strategies", methods=["GET"])
@limiter.limit(API_RATE_LIMIT)
def list_strategies_route():
    """GET /api/v1/paperjournal/strategies — list distinct strategy names."""
    try:
        api_key = _validate_api_key_from_params()
        if not api_key:
            return jsonify({"status": "error", "message": "Invalid API key"}), 401

        strategies = get_distinct_strategies()

        return jsonify({"status": "success", "data": strategies}), 200

    except Exception as e:
        logger.exception(f"Error listing strategies: {e}")
        return jsonify({"status": "error", "message": "Internal server error"}), 500
```

Add to `database/paper_trade_db.py`:

```python
def get_distinct_strategies() -> list[str]:
    """Return distinct strategy names from the paper_trades table, ordered alphabetically."""
    results = (
        db_session.query(PaperTrade.strategy_name)
        .distinct()
        .order_by(PaperTrade.strategy_name)
        .all()
    )
    return [row[0] for row in results if row[0]]
```

Add to `services/paper_trade_journal_service.py`:

```python
from database.paper_trade_db import get_distinct_strategies

def list_strategies() -> list[str]:
    """Return all distinct strategy names."""
    return get_distinct_strategies()
```

### Navigation Config Update

Add to `profileMenuItems` in `frontend/src/config/navigation.ts`:

```typescript
{ href: '/paper-journal', label: 'Paper Journal', icon: BookOpen },
```

The `BookOpen` icon is already imported in the navigation file (used for external docs link).

### Route Registration

Add to `App.tsx` within the `<Layout>` protected routes:

```typescript
const PaperJournal = lazy(() => import('@/pages/PaperJournal'))

// Inside <Route element={<Layout />}>:
<Route path="/paper-journal" element={<PaperJournal />} />
```

## Interfaces

### API Request/Response Contracts

**GET `/api/v1/paperjournal/strategies`**
```
Request:  GET /api/v1/paperjournal/strategies?apikey=<key>
Response: { "status": "success", "data": ["strategy1", "strategy2"] }
Error:    { "status": "error", "message": "Invalid API key" }  (401)
```

**GET `/api/v1/paperjournal/trades`** (existing)
```
Request:  GET /api/v1/paperjournal/trades?apikey=<key>&start_date=YYYY-MM-DD&end_date=YYYY-MM-DD&strategy_name=<name>
Response: { "status": "success", "data": [PaperTrade, ...] }
```

**GET `/api/v1/paperjournal/summary`** (existing)
```
Request:  GET /api/v1/paperjournal/summary?apikey=<key>&start_date=YYYY-MM-DD&end_date=YYYY-MM-DD&strategy_name=<name>
Response: { "status": "success", "data": TradeSummary }
```

### TypeScript Types

```typescript
// frontend/src/types/paper-journal.ts

export interface PaperTrade {
  trade_id: number
  created_at: string | null
  trade_date: string | null
  strategy_name: string
  direction: string | null
  entry_time: string | null
  entry_spot_price: number | null
  entry_option_symbol: string | null
  entry_option_price: number | null
  entry_quantity: number | null
  entry_action: string | null
  exit_time: string | null
  exit_spot_price: number | null
  exit_option_price: number | null
  exit_reason: string | null
  pnl: number | null
  custom_metadata: Record<string, unknown> | null
}

export interface TradeSummary {
  total_trades: number
  total_pnl: number
  winning_trades: number
  losing_trades: number
  win_rate: number
  per_strategy: Record<string, {
    total_trades: number
    total_pnl: number
    winning_trades: number
    losing_trades: number
    win_rate: number
  }>
}
```

## Data Models

### PaperTrade (existing SQLAlchemy model)

| Column              | Type            | Nullable |
|---------------------|-----------------|----------|
| id                  | Integer (PK)    | No       |
| created_at          | DateTime(tz)    | No       |
| trade_date          | Date            | Yes      |
| strategy_name       | String(128)     | No       |
| direction           | String(16)      | Yes      |
| entry_time          | DateTime(tz)    | Yes      |
| entry_spot_price    | Numeric(18,4)   | Yes      |
| entry_option_symbol | String(64)      | Yes      |
| entry_option_price  | Numeric(18,4)   | Yes      |
| entry_quantity      | Integer         | Yes      |
| entry_action        | String(8)       | Yes      |
| exit_time           | DateTime(tz)    | Yes      |
| exit_spot_price     | Numeric(18,4)   | Yes      |
| exit_option_price   | Numeric(18,4)   | Yes      |
| exit_reason         | String(32)      | Yes      |
| pnl                 | Numeric(18,4)   | Yes      |
| custom_metadata     | Text            | Yes      |

No schema changes required. The existing `paper_trades` table and indexes are sufficient.

## CSV Export Logic

The CSV export runs entirely client-side from the currently loaded `trades` array:

```typescript
function exportToCSV(trades: PaperTrade[]): void {
  const headers = [
    'Date', 'Strategy', 'Direction', 'Entry Time', 'Entry Spot',
    'Option Symbol', 'Entry Price', 'Exit Time', 'Exit Spot',
    'Exit Price', 'P&L', 'Exit Reason'
  ]

  const rows = trades.map(trade => [
    trade.trade_date ?? '',
    trade.strategy_name,
    trade.direction ?? '',
    trade.entry_time ?? '',
    trade.entry_spot_price?.toString() ?? '',
    trade.entry_option_symbol ?? '',
    trade.entry_option_price?.toString() ?? '',
    trade.exit_time ?? '',
    trade.exit_spot_price?.toString() ?? '',
    trade.exit_option_price?.toString() ?? '',
    trade.pnl?.toString() ?? '',
    trade.exit_reason ?? '',
  ])

  const csvContent = [headers, ...rows]
    .map(row => row.map(cell => `"${cell}"`).join(','))
    .join('\n')

  const blob = new Blob([csvContent], { type: 'text/csv;charset=utf-8;' })
  const url = URL.createObjectURL(blob)
  const link = document.createElement('a')
  link.href = url
  link.download = `paper-journal-${startDate}-to-${endDate}.csv`
  link.click()
  URL.revokeObjectURL(url)
}
```

## Error Handling

| Scenario | Behavior |
|----------|----------|
| Strategies fetch fails | Dropdown shows only "All Strategies"; no toast (silent fallback) |
| Trades fetch fails | Show error toast; set `error` state; display error message in table area |
| Summary fetch fails | Summary cards show 0/placeholder values |
| 401 on any request | `apiClient` interceptor redirects to `/login` |
| Network timeout | Same as fetch failure |

## P&L Color Logic

Applied consistently across Summary Cards and Trade Table:

```typescript
function getPnlColorClass(pnl: number | null): string {
  if (pnl === null || pnl === 0) return ''
  return pnl > 0 ? 'text-green-600' : 'text-red-600'
}
```

## Correctness Properties

*A property is a characteristic or behavior that should hold true across all valid executions of a system — essentially, a formal statement about what the system should do. Properties serve as the bridge between human-readable specifications and machine-verifiable correctness guarantees.*

### Property 1: Filter parameters are forwarded to API calls

*For any* combination of start_date, end_date, and strategy_name selected in the Filter Panel, when the Apply button is clicked, both the `/trades` and `/summary` API calls SHALL include those exact parameter values in the request query string.

**Validates: Requirements 5.2, 5.3**

### Property 2: Summary cards faithfully display API data

*For any* valid TradeSummary response from the API, the Summary Cards SHALL display the exact values for total_trades, total_pnl, win_rate, winning_trades, and losing_trades without transformation.

**Validates: Requirements 7.1, 7.2, 7.5, 7.6, 7.7**

### Property 3: P&L color coding is consistent with sign

*For any* numeric P&L value displayed in either the Summary Cards or Trade Table, the value SHALL be rendered with green color class when positive and red color class when negative.

**Validates: Requirements 7.3, 7.4, 8.3, 8.4**

### Property 4: Trade table row count equals API response length

*For any* list of trades returned from the API, the Trade Table SHALL render exactly that many data rows (excluding the header row and any empty-state message).

**Validates: Requirements 8.2**

### Property 5: CSV export is a faithful representation of displayed trades

*For any* set of trades currently displayed in the Trade Table, the generated CSV SHALL contain a header row matching the table columns and exactly one data row per trade, with field values matching the displayed data.

**Validates: Requirements 9.2, 9.3, 9.4**

### Property 6: Strategies endpoint returns distinct names from trade data

*For any* set of trades in the paper_trades table, the GET `/api/v1/paperjournal/strategies` endpoint SHALL return a deduplicated list containing exactly the set of unique strategy_name values present in the table.

**Validates: Requirements 10.2, 10.3**
