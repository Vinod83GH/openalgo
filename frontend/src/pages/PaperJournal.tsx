import {
  Activity,
  Download,
  FileText,
  Filter,
  Target,
  TrendingDown,
  TrendingUp,
} from 'lucide-react'
import { useEffect, useState } from 'react'
import { paperJournalApi } from '@/api/paper-journal'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Label } from '@/components/ui/label'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui/table'
import type { PaperTrade, TradeSummary } from '@/types/paper-journal'
import { showToast } from '@/utils/toast'

function getTodayString(): string {
  return new Date().toISOString().split('T')[0]
}

function getPnlColorClass(pnl: number | null): string {
  if (pnl === null || pnl === 0) return ''
  return pnl > 0 ? 'text-green-600' : 'text-red-600'
}

function formatTime(isoString: string | null): string {
  if (!isoString) return '—'
  try {
    const date = new Date(isoString)
    return date.toLocaleTimeString('en-IN', {
      hour: '2-digit',
      minute: '2-digit',
      second: '2-digit',
      hour12: false,
    })
  } catch {
    return isoString
  }
}

export default function PaperJournal() {

  const [trades, setTrades] = useState<PaperTrade[]>([])
  const [summary, setSummary] = useState<TradeSummary | null>(null)
  const [strategies, setStrategies] = useState<string[]>([])
  const [startDate, setStartDate] = useState<string>(getTodayString())
  const [endDate, setEndDate] = useState<string>(getTodayString())
  const [selectedStrategy, setSelectedStrategy] = useState<string>('all')
  const [isLoading, setIsLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  const fetchStrategies = async () => {
    try {
      const data = await paperJournalApi.getStrategies()
      setStrategies(data)
    } catch {
      // Silent fallback — dropdown shows only "All Strategies"
    }
  }

  const fetchData = async (start: string, end: string, strategy?: string) => {
    setIsLoading(true)
    setError(null)
    try {
      const params = {
        start_date: start,
        end_date: end,
        strategy_name: strategy && strategy !== 'all' ? strategy : undefined,
      }
      const [tradesData, summaryData] = await Promise.all([
        paperJournalApi.getTrades(params),
        paperJournalApi.getSummary(params),
      ])
      setTrades(tradesData)
      setSummary(summaryData)
    } catch {
      setError('Failed to load trade data')
      showToast.error('Failed to load trade data')
    } finally {
      setIsLoading(false)
    }
  }

  useEffect(() => {
    fetchStrategies()
    fetchData(startDate, endDate)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  const handleApply = () => {
    fetchData(startDate, endDate, selectedStrategy)
  }

  const exportToCSV = () => {
    if (trades.length === 0) {
      showToast.error('No trades to export')
      return
    }

    const headers = [
      'Date',
      'Strategy',
      'Direction',
      'Entry Time',
      'Entry Spot',
      'Option Symbol',
      'Entry Price',
      'Exit Time',
      'Exit Spot',
      'Exit Price',
      'P&L',
      'Exit Reason',
    ]

    const rows = trades.map((trade) => [
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
      .map((row) => row.map((cell) => `"${cell}"`).join(','))
      .join('\n')

    const blob = new Blob([csvContent], { type: 'text/csv;charset=utf-8;' })
    const url = URL.createObjectURL(blob)
    const link = document.createElement('a')
    link.href = url
    link.download = `paper-journal-${startDate}-to-${endDate}.csv`
    link.click()
    URL.revokeObjectURL(url)
  }

  if (isLoading && trades.length === 0) {
    return (
      <div className="flex items-center justify-center py-16">
        <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-primary"></div>
      </div>
    )
  }

  return (
    <div className="container mx-auto py-6 px-4 space-y-6">
      {/* Header */}
      <div>
        <h1 className="text-2xl font-bold flex items-center gap-2">
          <FileText className="h-6 w-6" />
          Paper Journal
        </h1>
        <p className="text-muted-foreground mt-1">
          Review your paper trade history, filter by date and strategy, and export to CSV
        </p>
      </div>

      {/* Filter Panel */}
      <Card>
        <CardHeader className="pb-3">
          <CardTitle className="text-lg flex items-center gap-2">
            <Filter className="h-4 w-4" />
            Filters
          </CardTitle>
        </CardHeader>
        <CardContent>
          <div className="grid grid-cols-1 md:grid-cols-5 gap-4 items-end">
            <div className="space-y-2">
              <Label htmlFor="start-date" className="text-sm font-medium">
                Start Date
              </Label>
              <input
                id="start-date"
                type="date"
                value={startDate}
                onChange={(e) => setStartDate(e.target.value)}
                className="flex h-9 w-full rounded-md border border-input bg-transparent px-3 py-1 text-sm shadow-sm transition-colors file:border-0 file:bg-transparent file:text-sm file:font-medium placeholder:text-muted-foreground focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-ring disabled:cursor-not-allowed disabled:opacity-50"
              />
            </div>
            <div className="space-y-2">
              <Label htmlFor="end-date" className="text-sm font-medium">
                End Date
              </Label>
              <input
                id="end-date"
                type="date"
                value={endDate}
                onChange={(e) => setEndDate(e.target.value)}
                className="flex h-9 w-full rounded-md border border-input bg-transparent px-3 py-1 text-sm shadow-sm transition-colors file:border-0 file:bg-transparent file:text-sm file:font-medium placeholder:text-muted-foreground focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-ring disabled:cursor-not-allowed disabled:opacity-50"
              />
            </div>
            <div className="space-y-2">
              <Label className="text-sm font-medium">Strategy</Label>
              <Select value={selectedStrategy} onValueChange={setSelectedStrategy}>
                <SelectTrigger>
                  <SelectValue placeholder="All Strategies" />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="all">All Strategies</SelectItem>
                  {strategies.map((strategy) => (
                    <SelectItem key={strategy} value={strategy}>
                      {strategy}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
            <div className="flex gap-2 pt-5">
              <Button onClick={handleApply} disabled={isLoading}>
                <Filter className="h-4 w-4 mr-2" />
                Apply
              </Button>
              <Button variant="secondary" onClick={exportToCSV} disabled={trades.length === 0}>
                <Download className="h-4 w-4 mr-2" />
                Export CSV
              </Button>
            </div>
          </div>
        </CardContent>
      </Card>

      {/* Summary Cards */}
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-5 gap-4">
        <Card>
          <CardHeader className="pb-2">
            <CardTitle className="text-sm font-medium text-muted-foreground flex items-center gap-2">
              <Activity className="h-4 w-4" />
              Total Trades
            </CardTitle>
          </CardHeader>
          <CardContent>
            <div className="text-3xl font-bold">{summary?.total_trades ?? 0}</div>
          </CardContent>
        </Card>

        <Card>
          <CardHeader className="pb-2">
            <CardTitle className="text-sm font-medium text-muted-foreground flex items-center gap-2">
              <TrendingUp className="h-4 w-4" />
              Total P&L
            </CardTitle>
          </CardHeader>
          <CardContent>
            <div className={`text-3xl font-bold ${getPnlColorClass(summary?.total_pnl ?? null)}`}>
              {summary?.total_pnl !== undefined
                ? `${summary.total_pnl >= 0 ? '+' : ''}${summary.total_pnl.toFixed(2)}`
                : '0.00'}
            </div>
          </CardContent>
        </Card>

        <Card>
          <CardHeader className="pb-2">
            <CardTitle className="text-sm font-medium text-muted-foreground flex items-center gap-2">
              <Target className="h-4 w-4" />
              Win Rate
            </CardTitle>
          </CardHeader>
          <CardContent>
            <div className="text-3xl font-bold">{summary?.win_rate ?? 0}%</div>
          </CardContent>
        </Card>

        <Card>
          <CardHeader className="pb-2">
            <CardTitle className="text-sm font-medium text-muted-foreground flex items-center gap-2">
              <TrendingUp className="h-4 w-4" />
              Winning
            </CardTitle>
          </CardHeader>
          <CardContent>
            <div className="text-3xl font-bold text-green-600">
              {summary?.winning_trades ?? 0}
            </div>
          </CardContent>
        </Card>

        <Card>
          <CardHeader className="pb-2">
            <CardTitle className="text-sm font-medium text-muted-foreground flex items-center gap-2">
              <TrendingDown className="h-4 w-4" />
              Losing
            </CardTitle>
          </CardHeader>
          <CardContent>
            <div className="text-3xl font-bold text-red-600">
              {summary?.losing_trades ?? 0}
            </div>
          </CardContent>
        </Card>
      </div>

      {/* Error State */}
      {error && (
        <Card className="border-destructive">
          <CardContent className="py-4">
            <p className="text-destructive text-sm">{error}</p>
          </CardContent>
        </Card>
      )}

      {/* Trade Table */}
      <Card>
        <CardContent className="p-0">
          <div className="overflow-x-auto">
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Date</TableHead>
                  <TableHead>Strategy</TableHead>
                  <TableHead>Direction</TableHead>
                  <TableHead>Entry Time</TableHead>
                  <TableHead>Entry Spot</TableHead>
                  <TableHead>Option Symbol</TableHead>
                  <TableHead>Entry Price</TableHead>
                  <TableHead>Exit Time</TableHead>
                  <TableHead>Exit Spot</TableHead>
                  <TableHead>Exit Price</TableHead>
                  <TableHead>P&L</TableHead>
                  <TableHead>Exit Reason</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {trades.length === 0 ? (
                  <TableRow>
                    <TableCell colSpan={12} className="text-center py-8 text-muted-foreground">
                      No trades found for the selected filters
                    </TableCell>
                  </TableRow>
                ) : (
                  trades.map((trade) => (
                    <TableRow key={trade.trade_id} className="hover:bg-muted/50">
                      <TableCell className="text-sm whitespace-nowrap">
                        {trade.trade_date ?? '—'}
                      </TableCell>
                      <TableCell className="text-sm font-medium">
                        {trade.strategy_name}
                      </TableCell>
                      <TableCell className="text-sm">{trade.direction ?? '—'}</TableCell>
                      <TableCell className="text-sm whitespace-nowrap">
                        {formatTime(trade.entry_time)}
                      </TableCell>
                      <TableCell className="text-sm font-mono">
                        {trade.entry_spot_price?.toFixed(2) ?? '—'}
                      </TableCell>
                      <TableCell className="text-sm">{trade.entry_option_symbol ?? '—'}</TableCell>
                      <TableCell className="text-sm font-mono">
                        {trade.entry_option_price?.toFixed(2) ?? '—'}
                      </TableCell>
                      <TableCell className="text-sm whitespace-nowrap">
                        {formatTime(trade.exit_time)}
                      </TableCell>
                      <TableCell className="text-sm font-mono">
                        {trade.exit_spot_price?.toFixed(2) ?? '—'}
                      </TableCell>
                      <TableCell className="text-sm font-mono">
                        {trade.exit_option_price?.toFixed(2) ?? '—'}
                      </TableCell>
                      <TableCell
                        className={`text-sm font-mono font-medium ${getPnlColorClass(trade.pnl)}`}
                      >
                        {trade.pnl !== null ? trade.pnl.toFixed(2) : '—'}
                      </TableCell>
                      <TableCell className="text-sm">{trade.exit_reason ?? '—'}</TableCell>
                    </TableRow>
                  ))
                )}
              </TableBody>
            </Table>
          </div>
        </CardContent>
      </Card>
    </div>
  )
}
