// Python Strategy Types

// Positional strategy status type
export type PositionalStatus =
  | 'suspended'
  | 'running'
  | 'error'
  | 'state_save_failed'
  | 'requires_manual_review'
  | 'entry_expired'
  | 'completed'
  | 'suspended_stale'

export interface PythonStrategy {
  id: string
  name: string
  file_name: string
  status: 'stopped' | 'running' | 'error' | 'scheduled' | 'paused' | 'manually_stopped'
  status_message?: string
  process_id: number | null
  last_started: string | null
  last_stopped: string | null
  error_message: string | null
  is_scheduled: boolean
  manually_stopped?: boolean
  schedule_start_time: string | null
  schedule_stop_time: string | null
  schedule_days: string[]
  env_vars?: Record<string, string>
  created_at: string
  updated_at: string
  strategy_type?: 'intraday' | 'positional'
  positional_status?: PositionalStatus
}

export interface PythonStrategyContent {
  id: string
  name: string
  file_name: string
  content: string
  line_count: number
  size_kb: number
  last_modified: string
}

export interface LogFile {
  name: string
  path: string
  size_kb: number
  last_modified: string
}

export interface LogContent {
  content: string
  lines: number
  size_kb: number
  last_updated: string
}

export interface EnvironmentVariables {
  regular: Record<string, string>
  secure: Record<string, string>
}

export interface ScheduleConfig {
  start_time: string
  stop_time: string
  days: string[]
  env_vars?: Record<string, string>
}

export interface MasterContractStatus {
  ready: boolean
  message: string
  last_updated: string | null
}

export const SCHEDULE_DAYS = [
  { value: 'mon', label: 'Monday' },
  { value: 'tue', label: 'Tuesday' },
  { value: 'wed', label: 'Wednesday' },
  { value: 'thu', label: 'Thursday' },
  { value: 'fri', label: 'Friday' },
  { value: 'sat', label: 'Saturday' },
  { value: 'sun', label: 'Sunday' },
] as const

export const STATUS_COLORS: Record<string, string> = {
  running: 'bg-green-500',
  stopped: 'bg-gray-500',
  error: 'bg-red-500',
  scheduled: 'bg-blue-500',
  paused: 'bg-yellow-500',
  manually_stopped: 'bg-orange-500',
}

export const STATUS_LABELS: Record<string, string> = {
  running: 'Running',
  stopped: 'Stopped',
  error: 'Error',
  scheduled: 'Scheduled',
  paused: 'Paused',
  manually_stopped: 'Manual Stop',
}

// State API response type
export interface PositionalState {
  position_status: 'no_position' | 'position_open' | 'position_closed'
  entry_price: number | null
  entry_timestamp: string | null  // ISO 8601
  instrument_symbol: string | null
  quantity: number | null
  unrealized_pnl: number | null
  high_watermark: number | null
  trailing_active: boolean
  last_updated: string  // ISO 8601
  is_live: boolean
  entry_window: {
    start: string  // YYYY-MM-DD HH:MM
    end: string    // YYYY-MM-DD HH:MM
    exit_dt: string  // YYYY-MM-DD HH:MM
  } | null
}

// Datetime config update request
export interface DatetimeConfigUpdate {
  entry_start_dt?: string  // YYYY-MM-DD HH:MM
  entry_end_dt?: string    // YYYY-MM-DD HH:MM
  exit_dt?: string         // YYYY-MM-DD HH:MM
}

// Positional status colour mapping
export const POSITIONAL_STATUS_COLORS: Record<PositionalStatus, string> = {
  suspended: 'bg-amber-500',
  running: 'bg-green-500',
  error: 'bg-red-500',
  state_save_failed: 'bg-red-500',
  requires_manual_review: 'bg-red-500',
  entry_expired: 'bg-orange-500',
  completed: 'bg-blue-500',
  suspended_stale: 'bg-amber-500',
}

// Positional status label mapping
export const POSITIONAL_STATUS_LABELS: Record<PositionalStatus, string> = {
  suspended: 'Suspended',
  running: 'Running',
  error: 'Error',
  state_save_failed: 'State Save Failed',
  requires_manual_review: 'Needs Review',
  entry_expired: 'Entry Expired',
  completed: 'Completed',
  suspended_stale: 'Suspended (Stale)',
}

// Positional status tooltip mapping (only for statuses that need extra explanation)
export const POSITIONAL_STATUS_TOOLTIPS: Partial<Record<PositionalStatus, string>> = {
  suspended_stale: 'Last state save may be incomplete. Verify position manually.',
  requires_manual_review: 'Manual intervention required. Check logs for details.',
}
