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

const EXCHANGE_OPTIONS = ['NFO', 'BFO', 'MCX', 'CDS']

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

      {/* Time Fields */}
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
    </div>
  )
}
