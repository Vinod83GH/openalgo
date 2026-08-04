import { Activity, ArrowLeft, Calendar, Loader2, RefreshCw, Save } from 'lucide-react'
import { useCallback, useEffect, useRef, useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import { pythonStrategyApi } from '@/api/python-strategy'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import type { PositionalState, PythonStrategy } from '@/types/python-strategy'
import { POSITIONAL_STATUS_COLORS, POSITIONAL_STATUS_LABELS } from '@/types/python-strategy'
import { showToast } from '@/utils/toast'
import { formatINR, formatIST, getDaysRemaining, isChronologicalOrder, isFutureDatetime, isValidDatetimeFormat, pluralizeDays } from './positional-utils'

export default function PositionalStrategyState() {
  const { strategyId } = useParams<{ strategyId: string }>()

  const [strategy, setStrategy] = useState<PythonStrategy | null>(null)
  const [state, setState] = useState<PositionalState | null>(null)
  const [isLoading, setIsLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [exitDialogOpen, setExitDialogOpen] = useState(false)
  const [isExiting, setIsExiting] = useState(false)
  const [isRefreshing, setIsRefreshing] = useState(false)
  const [isStale, setIsStale] = useState(false)
  const lastUpdatedRef = useRef<string | null>(null)
  const intervalRef = useRef<ReturnType<typeof setInterval> | null>(null)

  // Datetime config editing state
  const [entryStart, setEntryStart] = useState('')
  const [entryEnd, setEntryEnd] = useState('')
  const [exitDt, setExitDt] = useState('')
  const [savedEntryStart, setSavedEntryStart] = useState('')
  const [savedEntryEnd, setSavedEntryEnd] = useState('')
  const [savedExitDt, setSavedExitDt] = useState('')
  const [dtErrors, setDtErrors] = useState<{ entryStart?: string; entryEnd?: string; exitDt?: string; ordering?: string }>({})
  const [isSavingConfig, setIsSavingConfig] = useState(false)

  const fetchData = async () => {
    if (!strategyId) return

    try {
      setError(null)
      const strategyInfo = await pythonStrategyApi.getStrategy(strategyId)
      setStrategy(strategyInfo)

      if (strategyInfo.strategy_type !== 'positional') {
        setIsLoading(false)
        return
      }

      const positionalState = await pythonStrategyApi.getPositionalState(strategyId)
      setState(positionalState)
      lastUpdatedRef.current = positionalState.last_updated
    } catch (err: unknown) {
      const error = err as { response?: { data?: { message?: string } } }
      const message = error.response?.data?.message || 'Failed to load strategy state'
      setError(message)
      showToast.error(message, 'pythonStrategy')
    } finally {
      setIsLoading(false)
    }
  }

  useEffect(() => {
    fetchData()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [strategyId])

  const handleRetry = () => {
    setIsLoading(true)
    setState(null)
    setStrategy(null)
    fetchData()
  }

  const pollState = useCallback(async () => {
    if (!strategyId || !strategy || strategy.strategy_type !== 'positional') return
    try {
      setIsRefreshing(true)
      const positionalState = await pythonStrategyApi.getPositionalState(strategyId)
      // Skip re-render if last_updated hasn't changed
      if (positionalState.last_updated === lastUpdatedRef.current) {
        return
      }
      lastUpdatedRef.current = positionalState.last_updated
      setState(positionalState)
      setIsStale(false)
    } catch {
      setIsStale(true)
    } finally {
      setIsRefreshing(false)
    }
  }, [strategyId, strategy])

  useEffect(() => {
    if (!strategy || strategy.strategy_type !== 'positional') return

    const startPolling = () => {
      if (intervalRef.current) clearInterval(intervalRef.current)
      intervalRef.current = setInterval(pollState, 30000)
    }

    const stopPolling = () => {
      if (intervalRef.current) {
        clearInterval(intervalRef.current)
        intervalRef.current = null
      }
    }

    const handleVisibilityChange = () => {
      if (document.hidden) {
        stopPolling()
      } else {
        pollState() // Immediate poll on resume
        startPolling()
      }
    }

    startPolling()
    document.addEventListener('visibilitychange', handleVisibilityChange)

    return () => {
      stopPolling()
      document.removeEventListener('visibilitychange', handleVisibilityChange)
    }
  }, [strategy, pollState])

  const handleExit = async () => {
    if (!strategyId) return
    try {
      setIsExiting(true)
      const response = await pythonStrategyApi.exitPosition(strategyId)
      if (response.status === 'success') {
        showToast.success(response.message || 'Exit signal sent', 'pythonStrategy')
        setExitDialogOpen(false)
        // Refetch state to reflect changes
        const positionalState = await pythonStrategyApi.getPositionalState(strategyId)
        setState(positionalState)
      } else {
        showToast.error(response.message || 'Failed to exit position', 'pythonStrategy')
      }
    } catch (err: unknown) {
      const error = err as { response?: { data?: { message?: string } } }
      const message = error.response?.data?.message || 'Failed to exit position'
      showToast.error(message, 'pythonStrategy')
    } finally {
      setIsExiting(false)
    }
  }

  // Initialize datetime fields from state.entry_window
  useEffect(() => {
    if (state?.entry_window) {
      setEntryStart(state.entry_window.start)
      setEntryEnd(state.entry_window.end)
      setExitDt(state.entry_window.exit_dt)
      setSavedEntryStart(state.entry_window.start)
      setSavedEntryEnd(state.entry_window.end)
      setSavedExitDt(state.entry_window.exit_dt)
    }
  }, [state?.entry_window?.start, state?.entry_window?.end, state?.entry_window?.exit_dt])

  // Validate datetime fields
  const validateDatetime = (start: string, end: string, exit: string) => {
    const errors: typeof dtErrors = {}
    if (start && !isValidDatetimeFormat(start)) errors.entryStart = 'Invalid format. Use YYYY-MM-DD HH:MM'
    if (end && !isValidDatetimeFormat(end)) errors.entryEnd = 'Invalid format. Use YYYY-MM-DD HH:MM'
    if (exit && !isValidDatetimeFormat(exit)) errors.exitDt = 'Invalid format. Use YYYY-MM-DD HH:MM'

    // Chronological ordering (only if all formats are valid)
    if (!errors.entryStart && !errors.entryEnd && !errors.exitDt && start && end && exit) {
      const orderResult = isChronologicalOrder(start, end, exit)
      if (!orderResult.valid) {
        errors.ordering = orderResult.error
      }
    }

    // Future validation for exit_dt when position is open
    if (!errors.exitDt && exit && state?.position_status === 'position_open') {
      if (!isFutureDatetime(exit)) {
        errors.exitDt = 'Exit datetime must be in the future'
      }
    }

    setDtErrors(errors)
    return Object.keys(errors).length === 0
  }

  // Save datetime config handler
  const handleSaveConfig = async () => {
    if (!strategyId) return
    if (!validateDatetime(entryStart, entryEnd, exitDt)) return

    try {
      setIsSavingConfig(true)
      const config: Record<string, string> = {}
      if (entryStart !== savedEntryStart) config.entry_start_dt = entryStart
      if (entryEnd !== savedEntryEnd) config.entry_end_dt = entryEnd
      if (exitDt !== savedExitDt) config.exit_dt = exitDt

      if (Object.keys(config).length === 0) {
        showToast.info('No changes to save', 'pythonStrategy')
        return
      }

      const response = await pythonStrategyApi.updateDatetimeConfig(strategyId, config)
      if (response.status === 'success') {
        showToast.success('Datetime configuration updated', 'pythonStrategy')
        setSavedEntryStart(entryStart)
        setSavedEntryEnd(entryEnd)
        setSavedExitDt(exitDt)
      } else {
        showToast.error(response.message || 'Failed to save', 'pythonStrategy')
        // Revert to last saved
        setEntryStart(savedEntryStart)
        setEntryEnd(savedEntryEnd)
        setExitDt(savedExitDt)
      }
    } catch (err: unknown) {
      const error = err as { response?: { data?: { message?: string } } }
      const message = error.response?.data?.message || 'Failed to save datetime configuration'
      showToast.error(message, 'pythonStrategy')
      // Revert to last saved
      setEntryStart(savedEntryStart)
      setEntryEnd(savedEntryEnd)
      setExitDt(savedExitDt)
    } finally {
      setIsSavingConfig(false)
    }
  }

  // Loading state
  if (isLoading) {
    return (
      <div className="flex items-center justify-center py-16">
        <Loader2 className="h-8 w-8 animate-spin text-primary" />
      </div>
    )
  }

  // Error state
  if (error) {
    return (
      <div className="py-6 space-y-6">
        <div className="flex items-center gap-2 mb-2">
          <Link to="/python" className="text-muted-foreground hover:text-foreground">
            <ArrowLeft className="h-4 w-4" />
          </Link>
          <h1 className="text-2xl font-bold">Strategy State</h1>
        </div>
        <Card>
          <CardContent className="py-8">
            <div className="flex flex-col items-center gap-4 text-center">
              <p className="text-destructive">{error}</p>
              <Button variant="outline" onClick={handleRetry}>
                <RefreshCw className="h-4 w-4 mr-2" />
                Retry
              </Button>
            </div>
          </CardContent>
        </Card>
      </div>
    )
  }

  // Not a positional strategy
  if (strategy && strategy.strategy_type !== 'positional') {
    return (
      <div className="py-6 space-y-6">
        <div className="flex items-center gap-2 mb-2">
          <Link to="/python" className="text-muted-foreground hover:text-foreground">
            <ArrowLeft className="h-4 w-4" />
          </Link>
          <h1 className="text-2xl font-bold">{strategy.name}</h1>
        </div>
        <Card>
          <CardContent className="py-8">
            <div className="flex flex-col items-center gap-4 text-center">
              <p className="text-muted-foreground">
                State panel is only available for positional strategies
              </p>
              <Link to="/python">
                <Button variant="outline">
                  <ArrowLeft className="h-4 w-4 mr-2" />
                  Back to Strategies
                </Button>
              </Link>
            </div>
          </CardContent>
        </Card>
      </div>
    )
  }

  const positionalStatus = strategy?.positional_status

  const formatEntryWindowDate = (dateStr: string): string => {
    // dateStr is "YYYY-MM-DD HH:MM" — format as "DD MMM YYYY"
    const [datePart] = dateStr.split(' ')
    const [year, month, day] = datePart.split('-')
    const months = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec']
    const monthName = months[parseInt(month, 10) - 1] || month
    return `${day} ${monthName} ${year}`
  }

  return (
    <div className="py-6 space-y-6">
      {/* Header */}
      <div>
        <div className="flex items-center gap-2 mb-2">
          <Link to="/python" className="text-muted-foreground hover:text-foreground">
            <ArrowLeft className="h-4 w-4" />
          </Link>
          <h1 className="text-2xl font-bold">{strategy?.name ?? 'Strategy State'}</h1>
          {positionalStatus && (
            <Badge className={`${POSITIONAL_STATUS_COLORS[positionalStatus]} text-white`}>
              {POSITIONAL_STATUS_LABELS[positionalStatus]}
            </Badge>
          )}
          {isStale && (
            <Badge variant="outline" className="border-amber-500 text-amber-600">
              Data may be stale
            </Badge>
          )}
          <Button variant="ghost" size="sm" onClick={() => { pollState() }} disabled={isRefreshing}>
            <RefreshCw className={`h-4 w-4 ${isRefreshing ? 'animate-spin' : ''}`} />
          </Button>
        </div>
      </div>

      {/* is_live notice */}
      {state && !state.is_live && (
        <Card className="border-amber-200 bg-amber-50 dark:border-amber-800 dark:bg-amber-950">
          <CardContent className="py-3">
            <p className="text-sm text-amber-700 dark:text-amber-300">
              Showing persisted snapshot — strategy is not currently running
            </p>
          </CardContent>
        </Card>
      )}

      {/* Position State */}
      {state && state.position_status === 'no_position' && (
        <Card>
          <CardHeader>
            <CardTitle>No Position Open</CardTitle>
          </CardHeader>
          <CardContent className="space-y-2">
            <p className="text-muted-foreground">Strategy is waiting for entry conditions</p>
            {state.entry_window && (
              <div className="text-sm space-y-1">
                <p>
                  <span className="text-muted-foreground">Entry Window Start:</span>{' '}
                  <span className="font-medium">{state.entry_window.start}</span>
                </p>
                <p>
                  <span className="text-muted-foreground">Entry Window End:</span>{' '}
                  <span className="font-medium">{state.entry_window.end}</span>
                </p>
              </div>
            )}
          </CardContent>
        </Card>
      )}

      {/* Entry Window Progress Section */}
      {state && state.position_status === 'no_position' && state.entry_window && (
        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-2">
              <Calendar className="h-5 w-5" />
              Entry Window
            </CardTitle>
          </CardHeader>
          <CardContent className="space-y-3">
            {/* Days remaining or expired */}
            {(() => {
              const daysLeft = getDaysRemaining(state.entry_window!.end)
              if (daysLeft <= 0) {
                return (
                  <Badge className="bg-orange-500 text-white">Entry Expired</Badge>
                )
              }
              return (
                <p className="text-lg font-medium">
                  {pluralizeDays(daysLeft)} remaining
                </p>
              )
            })()}

            {/* Date range display */}
            <div className="grid grid-cols-2 gap-4 text-sm">
              <div>
                <p className="text-muted-foreground">Start</p>
                <p className="font-medium">{formatEntryWindowDate(state.entry_window!.start)}</p>
              </div>
              <div>
                <p className="text-muted-foreground">End</p>
                <p className="font-medium">{formatEntryWindowDate(state.entry_window!.end)}</p>
              </div>
            </div>
          </CardContent>
        </Card>
      )}

      {/* Datetime Configuration Card */}
      {state && state.entry_window && (
        <Card>
          <CardHeader>
            <CardTitle>Datetime Configuration</CardTitle>
          </CardHeader>
          <CardContent className="space-y-4">
            <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
              <div className="space-y-2">
                <Label htmlFor="entry-start">Entry Start</Label>
                <Input
                  id="entry-start"
                  value={entryStart}
                  onChange={(e) => { setEntryStart(e.target.value); validateDatetime(e.target.value, entryEnd, exitDt) }}
                  disabled={state.position_status !== 'no_position'}
                  placeholder="YYYY-MM-DD HH:MM"
                />
                {dtErrors.entryStart && <p className="text-xs text-destructive">{dtErrors.entryStart}</p>}
              </div>
              <div className="space-y-2">
                <Label htmlFor="entry-end">Entry End</Label>
                <Input
                  id="entry-end"
                  value={entryEnd}
                  onChange={(e) => { setEntryEnd(e.target.value); validateDatetime(entryStart, e.target.value, exitDt) }}
                  disabled={state.position_status !== 'no_position'}
                  placeholder="YYYY-MM-DD HH:MM"
                />
                {dtErrors.entryEnd && <p className="text-xs text-destructive">{dtErrors.entryEnd}</p>}
              </div>
              <div className="space-y-2">
                <Label htmlFor="exit-dt">Exit Datetime</Label>
                <Input
                  id="exit-dt"
                  value={exitDt}
                  onChange={(e) => { setExitDt(e.target.value); validateDatetime(entryStart, entryEnd, e.target.value) }}
                  disabled={state.position_status === 'position_closed'}
                  placeholder="YYYY-MM-DD HH:MM"
                />
                {dtErrors.exitDt && <p className="text-xs text-destructive">{dtErrors.exitDt}</p>}
              </div>
            </div>
            {dtErrors.ordering && <p className="text-sm text-destructive">{dtErrors.ordering}</p>}
            {state.position_status !== 'position_closed' && (
              <Button
                onClick={handleSaveConfig}
                disabled={isSavingConfig || Object.keys(dtErrors).length > 0}
              >
                {isSavingConfig ? <Loader2 className="h-4 w-4 mr-2 animate-spin" /> : <Save className="h-4 w-4 mr-2" />}
                Save
              </Button>
            )}
          </CardContent>
        </Card>
      )}

      {state && state.position_status === 'position_open' && (
        <Card>
          <CardHeader>
            <CardTitle>Position Open</CardTitle>
          </CardHeader>
          <CardContent className="space-y-4">
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
              <div>
                <p className="text-sm text-muted-foreground">Instrument</p>
                <p className="font-medium">{state.instrument_symbol ?? '-'}</p>
              </div>
              <div>
                <p className="text-sm text-muted-foreground">Entry Price</p>
                <p className="font-medium">
                  {state.entry_price != null ? formatINR(state.entry_price) : '-'}
                </p>
              </div>
              <div>
                <p className="text-sm text-muted-foreground">Quantity</p>
                <p className="font-medium">{state.quantity != null ? state.quantity : '-'}</p>
              </div>
              <div>
                <p className="text-sm text-muted-foreground">Entry Time</p>
                <p className="font-medium">
                  {state.entry_timestamp ? formatIST(state.entry_timestamp) : '-'}
                </p>
              </div>
              <div>
                <p className="text-sm text-muted-foreground">Unrealized P&L</p>
                <p
                  className={`font-medium ${
                    state.unrealized_pnl != null && state.unrealized_pnl > 0
                      ? 'text-green-600'
                      : state.unrealized_pnl != null && state.unrealized_pnl < 0
                        ? 'text-red-600'
                        : 'text-muted-foreground'
                  }`}
                >
                  {state.unrealized_pnl != null ? formatINR(state.unrealized_pnl) : '-'}
                </p>
              </div>
              {state.high_watermark != null && (
                <div>
                  <p className="text-sm text-muted-foreground">High Watermark</p>
                  <p className="font-medium">{formatINR(state.high_watermark)}</p>
                </div>
              )}
              <div>
                <p className="text-sm text-muted-foreground">Trailing Active</p>
                <div className="mt-1">
                  {state.trailing_active ? (
                    <Badge className="bg-green-500 text-white">
                      <Activity className="h-3 w-3" />
                      Active
                    </Badge>
                  ) : (
                    <Badge variant="secondary">Inactive</Badge>
                  )}
                </div>
              </div>
            </div>
            <div className="pt-4">
              <Button
                variant="destructive"
                onClick={() => setExitDialogOpen(true)}
                disabled={isExiting}
              >
                {isExiting ? <Loader2 className="h-4 w-4 mr-2 animate-spin" /> : null}
                Manual Exit
              </Button>
            </div>
            <div className="pt-2 border-t">
              <p className="text-xs text-muted-foreground">
                Last updated: {formatIST(state.last_updated)}
              </p>
            </div>
          </CardContent>
        </Card>
      )}

      {state && state.position_status === 'position_closed' && (
        <Card>
          <CardHeader>
            <div className="flex items-center gap-2">
              <CardTitle>Position Closed</CardTitle>
              <Badge className="bg-blue-500 text-white">Closed</Badge>
            </div>
          </CardHeader>
          <CardContent className="space-y-4">
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
              <div>
                <p className="text-sm text-muted-foreground">Instrument</p>
                <p className="font-medium">{state.instrument_symbol ?? '-'}</p>
              </div>
              <div>
                <p className="text-sm text-muted-foreground">Entry Price</p>
                <p className="font-medium">
                  {state.entry_price != null ? formatINR(state.entry_price) : '-'}
                </p>
              </div>
              <div>
                <p className="text-sm text-muted-foreground">Quantity</p>
                <p className="font-medium">{state.quantity != null ? state.quantity : '-'}</p>
              </div>
            </div>
            <div className="pt-2 border-t">
              <p className="text-xs text-muted-foreground">
                Last updated: {formatIST(state.last_updated)}
              </p>
            </div>
          </CardContent>
        </Card>
      )}

      {/* Exit Confirmation Dialog */}
      <Dialog open={exitDialogOpen} onOpenChange={setExitDialogOpen}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Confirm Manual Exit</DialogTitle>
            <DialogDescription>
              Are you sure you want to exit this position? This will place a market sell order for {state?.quantity ?? 0} units of {state?.instrument_symbol ?? 'unknown'}.
            </DialogDescription>
          </DialogHeader>
          <DialogFooter>
            <Button variant="outline" onClick={() => setExitDialogOpen(false)} disabled={isExiting}>
              Cancel
            </Button>
            <Button variant="destructive" onClick={handleExit} disabled={isExiting}>
              {isExiting && <Loader2 className="h-4 w-4 mr-2 animate-spin" />}
              Confirm Exit
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  )
}
