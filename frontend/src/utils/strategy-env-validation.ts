/**
 * Strategy environment variable validation and mapping utilities.
 *
 * Provides validation for strategy parameter fields (lots, time formats)
 * and mapping between form state and environment variable dictionaries.
 */

export interface StrategyEnvVars {
  STRATEGY_SYMBOL: string
  STRATEGY_STRIKE: string
  STRATEGY_LOTS: string
  STRATEGY_ENTRY_START: string
  STRATEGY_ENTRY_END: string
  STRATEGY_EXIT_TIME: string
  STRATEGY_PRODUCT: string
  STRATEGY_EXCHANGE: string
  STRATEGY_TARGET_PCT: string
}

/**
 * Constant mapping from form field names to environment variable names.
 */
export const STRATEGY_FIELD_MAP: Record<string, string> = {
  symbol: 'STRATEGY_SYMBOL',
  strike: 'STRATEGY_STRIKE',
  lots: 'STRATEGY_LOTS',
  entryStart: 'STRATEGY_ENTRY_START',
  entryEnd: 'STRATEGY_ENTRY_END',
  exitTime: 'STRATEGY_EXIT_TIME',
  product: 'STRATEGY_PRODUCT',
  exchange: 'STRATEGY_EXCHANGE',
  targetPct: 'STRATEGY_TARGET_PCT',
}

/**
 * Validate the lots field value.
 * Returns an error message string if invalid, or null if valid.
 * Empty values are considered valid (field is optional).
 */
export function validateLots(value: string): string | null {
  if (!value) return null // optional field
  const num = parseInt(value, 10)
  if (isNaN(num) || num < 1 || !Number.isInteger(Number(value))) {
    return 'Lots must be a positive integer (minimum 1)'
  }
  return null
}

/**
 * Validate a time field value in HH:MM format.
 * Returns an error message string if invalid, or null if valid.
 * Empty values are considered valid (field is optional).
 */
export function validateTimeFormat(value: string): string | null {
  if (!value) return null // optional field
  const timeRegex = /^([01]\d|2[0-3]):([0-5]\d)$/
  if (!timeRegex.test(value)) {
    return 'Time must be in HH:MM format (00:00 - 23:59)'
  }
  return null
}

/**
 * Convert form state (StrategyEnvVars) to an env_vars dictionary for the API.
 * Filters out entries with empty or whitespace-only values.
 */
export function formStateToEnvVars(state: StrategyEnvVars): Record<string, string> {
  const result: Record<string, string> = {}
  for (const [, envKey] of Object.entries(STRATEGY_FIELD_MAP)) {
    const value = state[envKey as keyof StrategyEnvVars]
    if (value && value.trim()) {
      result[envKey] = value.trim()
    }
  }
  return result
}

/**
 * Convert an env_vars dictionary from the API to form state (StrategyEnvVars).
 * Missing keys default to empty string.
 */
export function envVarsToFormState(envVars: Record<string, string>): StrategyEnvVars {
  return {
    STRATEGY_SYMBOL: envVars['STRATEGY_SYMBOL'] || '',
    STRATEGY_STRIKE: envVars['STRATEGY_STRIKE'] || '',
    STRATEGY_LOTS: envVars['STRATEGY_LOTS'] || '',
    STRATEGY_ENTRY_START: envVars['STRATEGY_ENTRY_START'] || '',
    STRATEGY_ENTRY_END: envVars['STRATEGY_ENTRY_END'] || '',
    STRATEGY_EXIT_TIME: envVars['STRATEGY_EXIT_TIME'] || '',
    STRATEGY_PRODUCT: envVars['STRATEGY_PRODUCT'] || '',
    STRATEGY_EXCHANGE: envVars['STRATEGY_EXCHANGE'] || '',
    STRATEGY_TARGET_PCT: envVars['STRATEGY_TARGET_PCT'] || '',
  }
}
