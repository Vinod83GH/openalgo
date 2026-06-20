import { ArrowLeft, Save, Tv } from 'lucide-react'
import { useEffect, useState } from 'react'
import { Link, useNavigate, useParams } from 'react-router-dom'
import { webClient } from '@/api/client'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Checkbox } from '@/components/ui/checkbox'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'
import { Switch } from '@/components/ui/switch'
import { showToast } from '@/utils/toast'

const DAYS = ['Mon', 'Tue', 'Wed', 'Thu', 'Fri'] as const

const STRIKE_SELECTIONS = [
  'ITM5', 'ITM4', 'ITM3', 'ITM2', 'ITM1',
  'ATM',
  'OTM1', 'OTM2', 'OTM3', 'OTM4', 'OTM5',
]

export default function TvStrategyEdit() {
  const { strategyName } = useParams<{ strategyName: string }>()
  const navigate = useNavigate()
  const isNew = strategyName === 'new'

  const [isLoading, setIsLoading] = useState(!isNew)
  const [isSaving, setIsSaving] = useState(false)

  const [name, setName] = useState('')
  const [activeDays, setActiveDays] = useState<string[]>([...DAYS])
  const [lotSize, setLotSize] = useState(1)
  const [strikeSelection, setStrikeSelection] = useState('ITM2')
  const [enabled, setEnabled] = useState(true)
  const [product, setProduct] = useState('MIS')
  const [exchange, setExchange] = useState('NFO')

  useEffect(() => {
    if (!isNew && strategyName) {
      fetchStrategy(strategyName)
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [strategyName])

  const fetchStrategy = async (stratName: string) => {
    try {
      const response = await webClient.get<{ status: string; data: {
        name: string
        active_days: string[]
        lot_size: number
        strike_selection: string
        enabled: boolean
        product: string
        exchange: string
      } }>(`/admin/api/tv-strategies/${stratName}`)
      const data = response.data.data
      setName(data.name)
      setActiveDays(data.active_days)
      setLotSize(data.lot_size)
      setStrikeSelection(data.strike_selection)
      setEnabled(data.enabled)
      setProduct(data.product)
      setExchange(data.exchange)
    } catch {
      showToast.error('Failed to load strategy', 'admin')
    } finally {
      setIsLoading(false)
    }
  }

  const handleDayToggle = (day: string, checked: boolean) => {
    if (checked) {
      setActiveDays((prev) => [...prev, day])
    } else {
      setActiveDays((prev) => prev.filter((d) => d !== day))
    }
  }

  const handleSave = async () => {
    // Client-side validation
    if (isNew && !name.trim()) {
      showToast.error('Strategy name is required')
      return
    }
    if (lotSize < 1) {
      showToast.error('Lot size must be at least 1')
      return
    }

    setIsSaving(true)
    try {
      const payload = {
        ...(isNew ? { name: name.trim() } : {}),
        active_days: activeDays,
        lot_size: lotSize,
        strike_selection: strikeSelection,
        enabled,
        product,
        exchange,
      }

      if (isNew) {
        const response = await webClient.post<{ status: string; message?: string }>(
          '/admin/api/tv-strategies',
          payload
        )
        if (response.data.status === 'success') {
          showToast.success('Strategy created successfully', 'admin')
          navigate('/admin/tv-strategies')
        } else {
          showToast.error(response.data.message || 'Failed to create strategy', 'admin')
        }
      } else {
        const response = await webClient.put<{ status: string; message?: string }>(
          `/admin/api/tv-strategies/${strategyName}`,
          payload
        )
        if (response.data.status === 'success') {
          showToast.success('Strategy updated successfully', 'admin')
          navigate('/admin/tv-strategies')
        } else {
          showToast.error(response.data.message || 'Failed to update strategy', 'admin')
        }
      }
    } catch (error: unknown) {
      const err = error as { response?: { data?: { message?: string } } }
      showToast.error(err.response?.data?.message || 'Failed to save strategy', 'admin')
    } finally {
      setIsSaving(false)
    }
  }

  if (isLoading) {
    return (
      <div className="flex items-center justify-center py-16">
        <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-primary"></div>
      </div>
    )
  }

  return (
    <div className="py-6 space-y-6">
      {/* Header */}
      <div>
        <div className="flex items-center gap-2 mb-2">
          <Link to="/admin/tv-strategies" className="text-muted-foreground hover:text-foreground">
            <ArrowLeft className="h-4 w-4" />
          </Link>
          <h1 className="text-2xl font-bold flex items-center gap-2">
            <Tv className="h-6 w-6" />
            {isNew ? 'New Strategy' : `Edit: ${strategyName}`}
          </h1>
        </div>
        <p className="text-muted-foreground">
          {isNew
            ? 'Create a new TradingView alert strategy configuration'
            : 'Update strategy trading parameters'}
        </p>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        {/* Strategy Configuration Card */}
        <Card>
          <CardHeader>
            <CardTitle>Strategy Configuration</CardTitle>
            <CardDescription>
              Set the trading parameters for this strategy
            </CardDescription>
          </CardHeader>
          <CardContent className="space-y-4">
            <div className="space-y-2">
              <Label htmlFor="strategy-name">Name</Label>
              <Input
                id="strategy-name"
                type="text"
                placeholder="e.g. nifty-scalp"
                value={name}
                onChange={(e) => setName(e.target.value)}
                disabled={!isNew}
                aria-label="Strategy name"
              />
            </div>
            <div className="space-y-2">
              <Label htmlFor="lot-size">Lot Size</Label>
              <Input
                id="lot-size"
                type="number"
                min={1}
                placeholder="e.g. 1"
                value={lotSize}
                onChange={(e) => setLotSize(parseInt(e.target.value) || 1)}
                aria-label="Lot size"
              />
            </div>
            <div className="space-y-2">
              <Label htmlFor="strike-selection">Strike Selection</Label>
              <Select value={strikeSelection} onValueChange={setStrikeSelection}>
                <SelectTrigger id="strike-selection" aria-label="Strike selection">
                  <SelectValue placeholder="Select strike" />
                </SelectTrigger>
                <SelectContent>
                  {STRIKE_SELECTIONS.map((strike) => (
                    <SelectItem key={strike} value={strike}>
                      {strike}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
            <div className="space-y-2">
              <Label htmlFor="product">Product</Label>
              <Select value={product} onValueChange={setProduct}>
                <SelectTrigger id="product" aria-label="Product type">
                  <SelectValue placeholder="Select product" />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="MIS">MIS (Intraday)</SelectItem>
                  <SelectItem value="NRML">NRML (Positional)</SelectItem>
                </SelectContent>
              </Select>
            </div>
            <div className="space-y-2">
              <Label htmlFor="exchange">Exchange</Label>
              <Select value={exchange} onValueChange={setExchange}>
                <SelectTrigger id="exchange" aria-label="Exchange">
                  <SelectValue placeholder="Select exchange" />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="NFO">NFO (NSE F&O)</SelectItem>
                  <SelectItem value="BFO">BFO (BSE F&O)</SelectItem>
                  <SelectItem value="MCX">MCX (Commodity)</SelectItem>
                  <SelectItem value="CDS">CDS (Currency)</SelectItem>
                </SelectContent>
              </Select>
            </div>
          </CardContent>
        </Card>

        {/* Active Days & Toggle Card */}
        <Card>
          <CardHeader>
            <CardTitle>Schedule & Status</CardTitle>
            <CardDescription>
              Configure which days the strategy is active and its enabled state
            </CardDescription>
          </CardHeader>
          <CardContent className="space-y-6">
            <div className="space-y-3">
              <Label>Active Days</Label>
              <div className="flex flex-wrap gap-4">
                {DAYS.map((day) => (
                  <div key={day} className="flex items-center space-x-2">
                    <Checkbox
                      id={`day-${day}`}
                      checked={activeDays.includes(day)}
                      onCheckedChange={(checked) => handleDayToggle(day, checked === true)}
                      aria-label={day}
                    />
                    <Label htmlFor={`day-${day}`} className="text-sm font-normal cursor-pointer">
                      {day}
                    </Label>
                  </div>
                ))}
              </div>
            </div>
            <div className="flex items-center justify-between">
              <Label htmlFor="strategy-enabled" className="text-sm text-muted-foreground">
                Strategy Enabled
              </Label>
              <Switch
                id="strategy-enabled"
                checked={enabled}
                onCheckedChange={setEnabled}
                aria-label="Toggle strategy enabled"
              />
            </div>
            <p className="text-sm text-muted-foreground">
              When disabled, incoming TradingView webhook alerts for this strategy will be ignored.
            </p>
          </CardContent>
        </Card>
      </div>

      {/* Save Button */}
      <div className="flex justify-end">
        <Button onClick={handleSave} disabled={isSaving}>
          <Save className="h-4 w-4 mr-2" />
          {isSaving ? 'Saving...' : isNew ? 'Create Strategy' : 'Save Changes'}
        </Button>
      </div>
    </div>
  )
}
