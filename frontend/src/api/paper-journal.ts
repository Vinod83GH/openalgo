import type { PaperTrade, TradeSummary } from '@/types/paper-journal'
import { webClient } from './client'

interface ApiResponse<T> {
  status: string
  data: T
  message?: string
}

export const paperJournalApi = {
  getStrategies: async (): Promise<string[]> => {
    const response = await webClient.get<ApiResponse<string[]>>(
      '/api/v1/paperjournal/strategies'
    )
    return response.data.data || []
  },

  getTrades: async (params: {
    start_date: string
    end_date: string
    strategy_name?: string
  }): Promise<PaperTrade[]> => {
    const queryParams = new URLSearchParams()
    queryParams.append('start_date', params.start_date)
    queryParams.append('end_date', params.end_date)
    if (params.strategy_name && params.strategy_name !== 'all') {
      queryParams.append('strategy_name', params.strategy_name)
    }
    const response = await webClient.get<ApiResponse<PaperTrade[]>>(
      `/api/v1/paperjournal/trades?${queryParams}`
    )
    return response.data.data || []
  },

  getSummary: async (params: {
    start_date: string
    end_date: string
    strategy_name?: string
  }): Promise<TradeSummary> => {
    const queryParams = new URLSearchParams()
    queryParams.append('start_date', params.start_date)
    queryParams.append('end_date', params.end_date)
    if (params.strategy_name && params.strategy_name !== 'all') {
      queryParams.append('strategy_name', params.strategy_name)
    }
    const response = await webClient.get<ApiResponse<TradeSummary>>(
      `/api/v1/paperjournal/summary?${queryParams}`
    )
    return response.data.data
  },
}
