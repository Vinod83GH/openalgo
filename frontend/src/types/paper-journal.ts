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
  per_strategy: Record<
    string,
    {
      total_trades: number
      total_pnl: number
      winning_trades: number
      losing_trades: number
      win_rate: number
    }
  >
}
