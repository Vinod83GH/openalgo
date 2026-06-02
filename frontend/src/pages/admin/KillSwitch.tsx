import { AlertTriangle, ArrowLeft, RefreshCw, Shield, ShieldOff } from 'lucide-react'
import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { adminApi } from '@/api/admin'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Switch } from '@/components/ui/switch'
import type { KillSwitchStatus } from '@/types/admin'
import { showToast } from '@/utils/toast'

export default function KillSwitch() {
  const [status, setStatus] = useState<KillSwitchStatus | null>(null)
  const [isLoading, setIsLoading] = useState(true)
  const [isRefreshing, setIsRefreshing] = useState(false)

  const [profitThreshold, setProfitThreshold] = useState('')
  const [lossThreshold, setLossThreshold] = useState('')
  const [thresholdError, setThresholdError] = useState('')
  const [isSavingThresholds, setIsSavingThresholds] = useState(false)

  const [isActivating, setIsActivating] = useState(false)
  const [isTogglingEnabled, setIsTogglingEnabled] = useState(false)

  const fetchStatus = async () => {
    setIsRefreshing(true)
    try {
      const data = await adminApi.getKillSwitchStatus()
      setStatus(data)
      setProfitThreshold(String(data.profit_threshold))
      setLossThreshold(String(data.loss_threshold))
    } catch {
      showToast.error('Failed to load kill switch status', 'admin')
    } finally {
      setIsRefreshing(false)
      setIsLoading(false)
    }
  }

  useEffect(() => {
    fetchStatus()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  const validateThresholds = (): boolean => {
    const profit = parseFloat(profitThreshold)
    const loss = parseFloat(lossThreshold)
    if (isNaN(profit) || profit < 0 || isNaN(loss) || loss < 0) {
      setThresholdError('Thresholds must be non-negative numbers')
      return false
    }
    setThresholdError('')
    return true
  }

  const handleSaveThresholds = async () => {
    if (!validateThresholds() || !status) return
    setIsSavingThresholds(true)
    try {
      const response = await adminApi.updateKillSwitchConfig({
        enabled: status.enabled,
        profit_threshold: parseFloat(profitThreshold),
        loss_threshold: parseFloat(lossThreshold),
      })
      if (response.status === 'success') {
        showToast.success(response.message || 'Thresholds saved', 'admin')
        // Optimistically update local state
        setStatus((prev) => prev ? {
          ...prev,
          profit_threshold: parseFloat(profitThreshold),
          loss_threshold: parseFloat(lossThreshold),
        } : prev)
      } else {
        showToast.error(response.message || 'Failed to save thresholds', 'admin')
      }
    } catch (error: unknown) {
      const err = error as { response?: { data?: { message?: string } } }
      showToast.error(err.response?.data?.message || 'Failed to save thresholds', 'admin')
    } finally {
      setIsSavingThresholds(false)
    }
  }

  const handleToggleEnabled = async (enabled: boolean) => {
    if (!status) return
    // Optimistically update toggle immediately
    setStatus((prev) => (prev ? { ...prev, enabled } : prev))
    setIsTogglingEnabled(true)
    try {
      const response = await adminApi.updateKillSwitchConfig({
        enabled,
        profit_threshold: parseFloat(profitThreshold) || status.profit_threshold,
        loss_threshold: parseFloat(lossThreshold) || status.loss_threshold,
      })
      if (response.status === 'success') {
        showToast.success(enabled ? 'Kill switch enabled' : 'Kill switch disabled', 'admin')
      } else {
        // Revert on failure
        setStatus((prev) => (prev ? { ...prev, enabled: !enabled } : prev))
        showToast.error(response.message || 'Failed to update', 'admin')
      }
    } catch (error: unknown) {
      // Revert on failure
      setStatus((prev) => (prev ? { ...prev, enabled: !enabled } : prev))
      const err = error as { response?: { data?: { message?: string } } }
      showToast.error(err.response?.data?.message || 'Failed to update', 'admin')
    } finally {
      setIsTogglingEnabled(false)
    }
  }

  const handleActivate = async () => {
    setIsActivating(true)
    // Optimistically update status to ACTIVATED immediately
    setStatus((prev) => prev ? { ...prev, kill_switch_status: 'ACTIVATED' as const } : prev)
    try {
      const response = await adminApi.activateKillSwitch()
      if (response.status === 'success') {
        showToast.success('Kill switch activated successfully', 'admin')
      } else {
        // Revert on failure
        setStatus((prev) => prev ? { ...prev, kill_switch_status: 'DEACTIVATED' as const } : prev)
        showToast.error(response.message || 'Failed to activate kill switch', 'admin')
      }
    } catch (error: unknown) {
      // Revert on failure
      setStatus((prev) => prev ? { ...prev, kill_switch_status: 'DEACTIVATED' as const } : prev)
      const err = error as { response?: { data?: { message?: string } } }
      showToast.error(err.response?.data?.message || 'Failed to activate kill switch', 'admin')
    } finally {
      setIsActivating(false)
    }
  }

  if (isLoading) {
    return (
      <div className="flex items-center justify-center py-16">
        <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-primary"></div>
      </div>
    )
  }

  const isActivated = status?.kill_switch_status === 'ACTIVATED'

  return (
    <div className="py-6 space-y-6">
      {/* Header */}
      <div>
        <div className="flex items-center gap-2 mb-2">
          <Link to="/admin" className="text-muted-foreground hover:text-foreground">
            <ArrowLeft className="h-4 w-4" />
          </Link>
          <h1 className="text-2xl font-bold flex items-center gap-2">
            <ShieldOff className="h-6 w-6" />
            Kill Switch
          </h1>
        </div>
        <p className="text-muted-foreground">
          Configure P&L thresholds and manually activate broker kill switch
        </p>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        {/* Status Card */}
        <Card>
          <CardHeader>
            <div className="flex items-center justify-between">
              <CardTitle>Current Status</CardTitle>
              <Button
                variant="ghost"
                size="icon"
                onClick={() => fetchStatus()}
                disabled={isRefreshing}
                aria-label="Refresh status"
              >
                <RefreshCw className={`h-4 w-4 ${isRefreshing ? 'animate-spin' : ''}`} />
              </Button>
            </div>
            <CardDescription>Broker-reported kill switch state</CardDescription>
          </CardHeader>
          <CardContent className="space-y-4">
            <div className="flex items-center justify-between">
              <span className="text-sm text-muted-foreground">Status</span>
              <Badge
                variant={isActivated ? 'destructive' : 'default'}
                className={!isActivated ? 'bg-green-600 text-white hover:bg-green-700' : ''}
              >
                {isActivated ? (
                  <ShieldOff className="h-3 w-3 mr-1" />
                ) : (
                  <Shield className="h-3 w-3 mr-1" />
                )}
                {status?.kill_switch_status}
              </Badge>
            </div>
            <div className="flex items-center justify-between">
              <span className="text-sm text-muted-foreground">Broker</span>
              <span className="text-sm font-medium capitalize">{status?.broker_name}</span>
            </div>
            <div className="flex items-center justify-between">
              <span className="text-sm text-muted-foreground">Current P&L</span>
              <span
                className={`text-sm font-mono font-medium ${
                  (status?.current_pnl ?? 0) >= 0 ? 'text-green-600' : 'text-red-600'
                }`}
              >
                {(status?.current_pnl ?? 0) >= 0 ? '+' : ''}
                {status?.current_pnl?.toFixed(2)}
              </span>
            </div>
            <div className="flex items-center justify-between">
              <Label htmlFor="kill-switch-enabled" className="text-sm text-muted-foreground">
                Kill Switch Enabled
              </Label>
              <Switch
                id="kill-switch-enabled"
                checked={status?.enabled ?? false}
                onCheckedChange={handleToggleEnabled}
                disabled={isTogglingEnabled}
                aria-label="Toggle kill switch enabled"
              />
            </div>
          </CardContent>
        </Card>

        {/* Thresholds Card */}
        <Card>
          <CardHeader>
            <CardTitle>P&L Thresholds</CardTitle>
            <CardDescription>
              Set profit and loss limits. A value of 0 disables that side.
            </CardDescription>
          </CardHeader>
          <CardContent className="space-y-4">
            <div className="space-y-2">
              <Label htmlFor="profit-threshold">Profit Threshold</Label>
              <Input
                id="profit-threshold"
                type="number"
                min={0}
                step="any"
                placeholder="e.g. 5000"
                value={profitThreshold}
                onChange={(e) => {
                  setProfitThreshold(e.target.value)
                  setThresholdError('')
                }}
                aria-label="Profit threshold"
              />
            </div>
            <div className="space-y-2">
              <Label htmlFor="loss-threshold">Loss Threshold</Label>
              <Input
                id="loss-threshold"
                type="number"
                min={0}
                step="any"
                placeholder="e.g. 3000"
                value={lossThreshold}
                onChange={(e) => {
                  setLossThreshold(e.target.value)
                  setThresholdError('')
                }}
                aria-label="Loss threshold"
              />
            </div>
            {thresholdError && (
              <div className="flex items-center gap-2 text-sm text-destructive">
                <AlertTriangle className="h-4 w-4 flex-shrink-0" />
                {thresholdError}
              </div>
            )}
            <Button
              className="w-full"
              onClick={handleSaveThresholds}
              disabled={isSavingThresholds}
            >
              {isSavingThresholds ? 'Saving...' : 'Save Thresholds'}
            </Button>
          </CardContent>
        </Card>
      </div>

      {/* Manual Activation Card */}
      <Card className={isActivated ? 'border-destructive' : 'border-destructive/50'}>
        <CardHeader>
          <CardTitle className="flex items-center gap-2 text-destructive">
            <AlertTriangle className="h-5 w-5" />
            Manual Activation
          </CardTitle>
          <CardDescription>
            Immediately activate the broker kill switch. The broker will reset it automatically
            before the next market open.
          </CardDescription>
        </CardHeader>
        <CardContent>
          <Button
            variant="destructive"
            onClick={handleActivate}
            disabled={isActivating || isActivated}
            aria-label={isActivated ? 'Kill switch already activated' : 'Activate kill switch'}
          >
            <ShieldOff className="h-4 w-4 mr-2" />
            {isActivating
              ? 'Activating...'
              : isActivated
                ? 'Kill Switch ACTIVATED'
                : 'Activate Kill Switch'}
          </Button>
          {isActivated && (
            <p className="mt-3 text-sm text-muted-foreground">
              Kill switch is currently <span className="text-destructive font-semibold">ACTIVATED</span>.
              All new orders are blocked. The broker will reset automatically before the next market open.
            </p>
          )}
        </CardContent>
      </Card>
    </div>
  )
}
