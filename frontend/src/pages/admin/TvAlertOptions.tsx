import { ArrowLeft, Save, Tv } from 'lucide-react'
import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { webClient } from '@/api/client'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
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

interface TvAlertConfig {
  strategy: string
  quantity: number
  product: string
  exchange: string
  enabled: boolean
}

export default function TvAlertOptions() {
  const [isLoading, setIsLoading] = useState(true)
  const [isSaving, setIsSaving] = useState(false)

  const [strategy, setStrategy] = useState('TV-Alert-Options')
  const [quantity, setQuantity] = useState(1)
  const [product, setProduct] = useState('MIS')
  const [exchange, setExchange] = useState('NFO')
  const [enabled, setEnabled] = useState(true)

  const fetchSettings = async () => {
    try {
      const response = await webClient.get<{ status: string; data: TvAlertConfig }>(
        '/admin/api/tv-alert-settings'
      )
      const data = response.data.data
      setStrategy(data.strategy)
      setQuantity(data.quantity)
      setProduct(data.product)
      setExchange(data.exchange)
      setEnabled(data.enabled)
    } catch {
      showToast.error('Failed to load TV Alert settings', 'admin')
    } finally {
      setIsLoading(false)
    }
  }

  useEffect(() => {
    fetchSettings()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  const handleSave = async () => {
    if (!strategy.trim()) {
      showToast.error('Strategy name is required')
      return
    }
    if (quantity < 1) {
      showToast.error('Quantity must be at least 1')
      return
    }

    setIsSaving(true)
    try {
      const response = await webClient.post<{ status: string; message?: string }>(
        '/admin/api/tv-alert-settings',
        { strategy, quantity, product, exchange, enabled }
      )
      if (response.data.status === 'success') {
        showToast.success(response.data.message || 'TV Alert settings saved', 'admin')
      } else {
        showToast.error(response.data.message || 'Failed to save settings', 'admin')
      }
    } catch (error: unknown) {
      const err = error as { response?: { data?: { message?: string } } }
      showToast.error(err.response?.data?.message || 'Failed to save settings', 'admin')
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
          <Link to="/admin" className="text-muted-foreground hover:text-foreground">
            <ArrowLeft className="h-4 w-4" />
          </Link>
          <h1 className="text-2xl font-bold flex items-center gap-2">
            <Tv className="h-6 w-6" />
            TV Alert Options
          </h1>
        </div>
        <p className="text-muted-foreground">
          Configure TradingView alert options trading parameters
        </p>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        {/* Trading Configuration Card */}
        <Card>
          <CardHeader>
            <CardTitle>Trading Configuration</CardTitle>
            <CardDescription>
              Set the default parameters for TV alert option orders
            </CardDescription>
          </CardHeader>
          <CardContent className="space-y-4">
            <div className="space-y-2">
              <Label htmlFor="strategy-name">Strategy Name</Label>
              <Input
                id="strategy-name"
                type="text"
                placeholder="e.g. TV-Alert-Options"
                value={strategy}
                onChange={(e) => setStrategy(e.target.value)}
                aria-label="Strategy name"
              />
            </div>
            <div className="space-y-2">
              <Label htmlFor="quantity">Quantity (Lots)</Label>
              <Input
                id="quantity"
                type="number"
                min={1}
                placeholder="e.g. 1"
                value={quantity}
                onChange={(e) => setQuantity(parseInt(e.target.value) || 1)}
                aria-label="Quantity"
              />
            </div>
            <div className="space-y-2">
              <Label htmlFor="product">Product Type</Label>
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
                </SelectContent>
              </Select>
            </div>
          </CardContent>
        </Card>

        {/* Feature Toggle Card */}
        <Card>
          <CardHeader>
            <CardTitle>Feature Toggle</CardTitle>
            <CardDescription>
              Enable or disable the TV alert options trading feature
            </CardDescription>
          </CardHeader>
          <CardContent className="space-y-4">
            <div className="flex items-center justify-between">
              <Label htmlFor="tv-alert-enabled" className="text-sm text-muted-foreground">
                TV Alert Options Enabled
              </Label>
              <Switch
                id="tv-alert-enabled"
                checked={enabled}
                onCheckedChange={setEnabled}
                aria-label="Toggle TV alert options enabled"
              />
            </div>
            <p className="text-sm text-muted-foreground">
              When disabled, incoming TradingView webhook alerts will be rejected with a 403 response.
            </p>
          </CardContent>
        </Card>
      </div>

      {/* Save Button */}
      <div className="flex justify-end">
        <Button onClick={handleSave} disabled={isSaving}>
          <Save className="h-4 w-4 mr-2" />
          {isSaving ? 'Saving...' : 'Save Settings'}
        </Button>
      </div>
    </div>
  )
}
