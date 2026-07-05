import type { PaperTrade, TradeSummary } from '@/types/paper-journal'
import { apiClient } from './client'

interface ApiResponse<T> {
  status: string
  data: T
  message?: string
}

export const paperJournalApi = {
  getStrategies: async (apiKey: string): Promise<string[]> => {
    const response = await apiClient.get<ApiResponse<string[]>>(
      `/paperjournal/strategies?apikey=${encodeURIComponent(apiKey)}`
    )
    return response.data.data || []
  },

  getTrades: async (
    apiKey: string,
    params: {
      start_date: string
      end_date: string
      strategy_name?: string
    }
  ): Promise<PaperTrade[]> => {
    const queryParams = new URLSearchParams()
    queryParams.append('apikey', apiKey)
    queryParams.append('start_date', params.start_date)
    queryParams.append('end_date', params.end_date)
    if (params.strategy_name && params.strategy_name !== 'all') {
      queryParams.append('strategy_name', params.strategy_name)
    }
    const response = await apiClient.get<ApiResponse<PaperTrade[]>>(
      `/paperjournal/trades?${queryParams}`
    )
    return response.data.data || []
  },

  getSummary: async (
    apiKey: string,
    params: {
      start_date: string
      end_date: string
      strategy_name?: string
    }
  ): Promise<TradeSummary> => {
    const queryParams = new URLSearchParams()
    queryParams.append('apikey', apiKey)
    queryParams.append('start_date', params.start_date)
    queryParams.append('end_date', params.end_date)
    if (params.strategy_name && params.strategy_name !== 'all') {
      queryParams.append('strategy_name', params.strategy_name)
    }
    const response = await apiClient.get<ApiResponse<TradeSummary>>(
      `/paperjournal/summary?${queryParams}`
    )
    return response.data.data
  },
}
