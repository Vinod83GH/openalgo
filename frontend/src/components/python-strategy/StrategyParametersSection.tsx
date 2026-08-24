import { Settings2 } from 'lucide-react'

import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'
import type { StrategyEnvVars } from '@/utils/strategy-env-validation'

const STRIKE_OPTIONS = [
  'ITM5',
  'ITM4',
  'ITM3',
  'ITM2',
  'ITM1',
  'ATM',
  'OTM1',
  'OTM2',
  'OTM3',
  'OTM4',
  'OTM5',
]

const PRODUCT_OPTIONS = ['MIS', 'NRML']

const EXCHANGE_OPTIONS = ['NSE', 'NSE_INDEX', 'NFO', 'BFO', 'BSE', 'MCX', 'CDS']

const STRATEGY_TYPE_OPTIONS = ['intraday', 'positional']

const CANDLE_TIMEFRAME_OPTIONS = ['1', '2', '3', '5', '10', '15', '20', '30', '60']

interface StrategyParametersSectionProps {
  values: StrategyEnvVars
  onChange: (values: StrategyEnvVars) => void
  disabled?: boolean
  errors?: Record<string, string>
}

export default function StrategyParametersSection({
  values,
  onChange,
  disabled = false,
  errors = {},
}: StrategyParametersSectionProps) {
  const handleChange = (key: keyof StrategyEnvVars, value: string) => {
    onChange({ ...values, [key]: value })
  }

  return (
    <div className="space-y-4 border-t pt-6">
      <div className="flex items-center gap-2">
        <Settings2 className="h-5 w-5 text-muted-foreground" />
        <h3 className="font-medium">Strategy Parameters</h3>
      </div>
      <p className="text-sm text-muted-foreground">
        Configure trading parameters for this strategy. All fields are optional.
      </p>

      {/* Strategy Type and Candle Timeframe */}
      <div className="grid grid-cols-2 gap-4">
        {/* Strategy Type */}
        <div className="space-y-2">
          <Label htmlFor="strategy-type">Strategy Type</Label>
          <Select
            value={values.strategy_type || 'intraday'}
            onValueChange={(value) => handleChange('strategy_type', value)}
            disabled={disabled}
          >
            <SelectTrigger id="strategy-type">
              <SelectValue placeholder="Select type" />
            </SelectTrigger>
            <SelectContent>
              {STRATEGY_TYPE_OPTIONS.map((option) => (
                <SelectItem key={option} value={option}>
                  {option.charAt(0).toUpperCase() + option.slice(1)}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
          <p className="text-xs text-muted-foreground">
            Intraday = same-day close. Positional = multi-day with state persistence.
          </p>
        </div>

        {/* Candle Timeframe */}
        <div className="space-y-2">
          <Label htmlFor="candle-timeframe">Candle Timeframe (min)</Label>
          <Select
            value={values.CANDLE_TIMEFRAME_MIN || '15'}
            onValueChange={(value) => handleChange('CANDLE_TIMEFRAME_MIN', value)}
            disabled={disabled}
          >
            <SelectTrigger id="candle-timeframe">
              <SelectValue placeholder="Select timeframe" />
            </SelectTrigger>
            <SelectContent>
              {CANDLE_TIMEFRAME_OPTIONS.map((option) => (
                <SelectItem key={option} value={option}>
                  {option} min
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        </div>
      </div>

      {/* Symbol */}
      <div className="space-y-2">
        <Label htmlFor="strategy-symbol">Symbol</Label>
        <Input
          id="strategy-symbol"
          placeholder="e.g. NIFTY, BANKNIFTY"
          value={values.STRATEGY_SYMBOL}
          onChange={(e) => handleChange('STRATEGY_SYMBOL', e.target.value)}
          disabled={disabled}
          className={errors.STRATEGY_SYMBOL ? 'border-red-500' : ''}
        />
        {errors.STRATEGY_SYMBOL && (
          <p className="text-sm text-red-500">{errors.STRATEGY_SYMBOL}</p>
        )}
      </div>

      {/* Strike Selection */}
      <div className="space-y-2">
        <Label htmlFor="strategy-strike">Strike Selection</Label>
        <Select
          value={values.STRATEGY_STRIKE}
          onValueChange={(value) => handleChange('STRATEGY_STRIKE', value)}
          disabled={disabled}
        >
          <SelectTrigger
            id="strategy-strike"
            className={errors.STRATEGY_STRIKE ? 'border-red-500' : ''}
          >
            <SelectValue placeholder="Select strike" />
          </SelectTrigger>
          <SelectContent>
            {STRIKE_OPTIONS.map((option) => (
              <SelectItem key={option} value={option}>
                {option}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
        {errors.STRATEGY_STRIKE && (
          <p className="text-sm text-red-500">{errors.STRATEGY_STRIKE}</p>
        )}
      </div>

      {/* Expiry Date */}
      <div className="space-y-2">
        <Label htmlFor="strategy-expiry-date">Expiry Date (DD-MMM-YYYY)</Label>
        <Input
          id="strategy-expiry-date"
          placeholder="e.g. 29-SEP-2026"
          value={values.STOCK_MONTHLY_EXPIRY}
          onChange={(e) => handleChange('STOCK_MONTHLY_EXPIRY', e.target.value.toUpperCase())}
          disabled={disabled}
          className={errors.STOCK_MONTHLY_EXPIRY ? 'border-red-500' : ''}
        />
        <p className="text-xs text-muted-foreground">
          Monthly expiry date for stock options. Leave empty for index weekly expiry.
        </p>
        {errors.STOCK_MONTHLY_EXPIRY && (
          <p className="text-sm text-red-500">{errors.STOCK_MONTHLY_EXPIRY}</p>
        )}
      </div>

      {/* Lots */}
      <div className="space-y-2">
        <Label htmlFor="strategy-lots">Lots</Label>
        <Input
          id="strategy-lots"
          type="number"
          min={1}
          placeholder="1"
          value={values.STRATEGY_LOTS}
          onChange={(e) => handleChange('STRATEGY_LOTS', e.target.value)}
          disabled={disabled}
          className={errors.STRATEGY_LOTS ? 'border-red-500' : ''}
        />
        {errors.STRATEGY_LOTS && (
          <p className="text-sm text-red-500">{errors.STRATEGY_LOTS}</p>
        )}
      </div>

      {/* Time Fields (Intraday) */}
      <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
        {/* Entry Start Time */}
        <div className="space-y-2">
          <Label htmlFor="strategy-entry-start">Entry Start Time</Label>
          <Input
            id="strategy-entry-start"
            type="time"
            value={values.STRATEGY_ENTRY_START}
            onChange={(e) => handleChange('STRATEGY_ENTRY_START', e.target.value)}
            disabled={disabled}
            className={errors.STRATEGY_ENTRY_START ? 'border-red-500' : ''}
          />
          {errors.STRATEGY_ENTRY_START && (
            <p className="text-sm text-red-500">{errors.STRATEGY_ENTRY_START}</p>
          )}
        </div>

        {/* Entry End Time */}
        <div className="space-y-2">
          <Label htmlFor="strategy-entry-end">Entry End Time</Label>
          <Input
            id="strategy-entry-end"
            type="time"
            value={values.STRATEGY_ENTRY_END}
            onChange={(e) => handleChange('STRATEGY_ENTRY_END', e.target.value)}
            disabled={disabled}
            className={errors.STRATEGY_ENTRY_END ? 'border-red-500' : ''}
          />
          {errors.STRATEGY_ENTRY_END && (
            <p className="text-sm text-red-500">{errors.STRATEGY_ENTRY_END}</p>
          )}
        </div>

        {/* Exit Time */}
        <div className="space-y-2">
          <Label htmlFor="strategy-exit-time">Exit Time</Label>
          <Input
            id="strategy-exit-time"
            type="time"
            value={values.STRATEGY_EXIT_TIME}
            onChange={(e) => handleChange('STRATEGY_EXIT_TIME', e.target.value)}
            disabled={disabled}
            className={errors.STRATEGY_EXIT_TIME ? 'border-red-500' : ''}
          />
          {errors.STRATEGY_EXIT_TIME && (
            <p className="text-sm text-red-500">{errors.STRATEGY_EXIT_TIME}</p>
          )}
        </div>
      </div>

      {/* Date+Time Fields (Positional) */}
      <div className="space-y-3 border-t pt-4 mt-4">
        <h4 className="text-sm font-medium text-muted-foreground">Positional Strategy Dates (optional)</h4>
        <p className="text-xs text-muted-foreground">
          For multi-day positional strategies. Format: YYYY-MM-DD HH:MM (IST)
        </p>
        <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
          {/* Entry Start DateTime */}
          <div className="space-y-2">
            <Label htmlFor="strategy-entry-start-dt">Entry Start Date</Label>
            <Input
              id="strategy-entry-start-dt"
              type="text"
              placeholder="2026-08-05 09:20"
              value={values.STRATEGY_ENTRY_START_DATE_TIME}
              onChange={(e) => handleChange('STRATEGY_ENTRY_START_DATE_TIME', e.target.value)}
              disabled={disabled}
              className={errors.STRATEGY_ENTRY_START_DATE_TIME ? 'border-red-500' : ''}
            />
            {errors.STRATEGY_ENTRY_START_DATE_TIME && (
              <p className="text-sm text-red-500">{errors.STRATEGY_ENTRY_START_DATE_TIME}</p>
            )}
          </div>

          {/* Entry End DateTime */}
          <div className="space-y-2">
            <Label htmlFor="strategy-entry-end-dt">Entry End Date</Label>
            <Input
              id="strategy-entry-end-dt"
              type="text"
              placeholder="2026-08-08 15:00"
              value={values.STRATEGY_ENTRY_END_DATE_TIME}
              onChange={(e) => handleChange('STRATEGY_ENTRY_END_DATE_TIME', e.target.value)}
              disabled={disabled}
              className={errors.STRATEGY_ENTRY_END_DATE_TIME ? 'border-red-500' : ''}
            />
            {errors.STRATEGY_ENTRY_END_DATE_TIME && (
              <p className="text-sm text-red-500">{errors.STRATEGY_ENTRY_END_DATE_TIME}</p>
            )}
          </div>

          {/* Exit DateTime */}
          <div className="space-y-2">
            <Label htmlFor="strategy-exit-dt">Exit Date</Label>
            <Input
              id="strategy-exit-dt"
              type="text"
              placeholder="2026-08-15 15:20"
              value={values.STRATEGY_EXIT_DATE_TIME}
              onChange={(e) => handleChange('STRATEGY_EXIT_DATE_TIME', e.target.value)}
              disabled={disabled}
              className={errors.STRATEGY_EXIT_DATE_TIME ? 'border-red-500' : ''}
            />
            {errors.STRATEGY_EXIT_DATE_TIME && (
              <p className="text-sm text-red-500">{errors.STRATEGY_EXIT_DATE_TIME}</p>
            )}
          </div>
        </div>
      </div>

      {/* Product and Exchange */}
      <div className="grid grid-cols-2 gap-4">
        {/* Product */}
        <div className="space-y-2">
          <Label htmlFor="strategy-product">Product</Label>
          <Select
            value={values.STRATEGY_PRODUCT}
            onValueChange={(value) => handleChange('STRATEGY_PRODUCT', value)}
            disabled={disabled}
          >
            <SelectTrigger
              id="strategy-product"
              className={errors.STRATEGY_PRODUCT ? 'border-red-500' : ''}
            >
              <SelectValue placeholder="Select product" />
            </SelectTrigger>
            <SelectContent>
              {PRODUCT_OPTIONS.map((option) => (
                <SelectItem key={option} value={option}>
                  {option}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
          {errors.STRATEGY_PRODUCT && (
            <p className="text-sm text-red-500">{errors.STRATEGY_PRODUCT}</p>
          )}
        </div>

        {/* Exchange */}
        <div className="space-y-2">
          <Label htmlFor="strategy-exchange">Exchange</Label>
          <Select
            value={values.STRATEGY_EXCHANGE}
            onValueChange={(value) => handleChange('STRATEGY_EXCHANGE', value)}
            disabled={disabled}
          >
            <SelectTrigger
              id="strategy-exchange"
              className={errors.STRATEGY_EXCHANGE ? 'border-red-500' : ''}
            >
              <SelectValue placeholder="Select exchange" />
            </SelectTrigger>
            <SelectContent>
              {EXCHANGE_OPTIONS.map((option) => (
                <SelectItem key={option} value={option}>
                  {option}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
          {errors.STRATEGY_EXCHANGE && (
            <p className="text-sm text-red-500">{errors.STRATEGY_EXCHANGE}</p>
          )}
        </div>
      </div>

      {/* Target Profit % */}
      <div className="space-y-2">
        <Label htmlFor="strategy-target-pct">Target Profit %</Label>
        <Input
          id="strategy-target-pct"
          type="number"
          min={0}
          step={1}
          placeholder="0 (disabled)"
          value={values.STRATEGY_TARGET_PCT}
          onChange={(e) => handleChange('STRATEGY_TARGET_PCT', e.target.value)}
          disabled={disabled}
          className={errors.STRATEGY_TARGET_PCT ? 'border-red-500' : ''}
        />
        <p className="text-xs text-muted-foreground">
          Exit when option profit reaches this %. Set to 0 to disable.
        </p>
        {errors.STRATEGY_TARGET_PCT && (
          <p className="text-sm text-red-500">{errors.STRATEGY_TARGET_PCT}</p>
        )}
      </div>

      {/* Trail Gap and Max Flip Entries */}
      <div className="grid grid-cols-2 gap-4">
        {/* Trail Gap */}
        <div className="space-y-2">
          <Label htmlFor="strategy-trail-gap">Trail Gap (₹)</Label>
          <Input
            id="strategy-trail-gap"
            type="number"
            min={0}
            step={0.5}
            placeholder="0 (disabled)"
            value={values.TRAIL_GAP}
            onChange={(e) => handleChange('TRAIL_GAP', e.target.value)}
            disabled={disabled}
            className={errors.TRAIL_GAP ? 'border-red-500' : ''}
          />
          <p className="text-xs text-muted-foreground">
            Trailing SL gap in ₹ from high watermark. 0 = no trailing.
          </p>
          {errors.TRAIL_GAP && (
            <p className="text-sm text-red-500">{errors.TRAIL_GAP}</p>
          )}
        </div>

        {/* Max Flip Entries */}
        <div className="space-y-2">
          <Label htmlFor="strategy-max-flip">Max Flip Entries</Label>
          <Input
            id="strategy-max-flip"
            type="number"
            min={0}
            step={1}
            placeholder="0 (no flips)"
            value={values.MAX_FLIP_ENTRIES}
            onChange={(e) => handleChange('MAX_FLIP_ENTRIES', e.target.value)}
            disabled={disabled}
            className={errors.MAX_FLIP_ENTRIES ? 'border-red-500' : ''}
          />
          <p className="text-xs text-muted-foreground">
            Max direction flips after SL hit. 0 = no re-entry on SL.
          </p>
          {errors.MAX_FLIP_ENTRIES && (
            <p className="text-sm text-red-500">{errors.MAX_FLIP_ENTRIES}</p>
          )}
        </div>
      </div>

      {/* Order Type */}
      <div className="space-y-2">
        <Label htmlFor="strategy-order-type">Order Type</Label>
        <Select
          value={values.STRATEGY_ORDER_TYPE}
          onValueChange={(value) => handleChange('STRATEGY_ORDER_TYPE', value)}
          disabled={disabled}
        >
          <SelectTrigger id="strategy-order-type">
            <SelectValue placeholder="Select order type" />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="MARKET">MARKET</SelectItem>
            <SelectItem value="LIMIT">LIMIT</SelectItem>
          </SelectContent>
        </Select>
        <p className="text-xs text-muted-foreground">
          MARKET for index options, LIMIT for stock options (Zerodha blocks MARKET for stocks).
        </p>
      </div>
    </div>
  )
}
