import { ApiClient } from './request'

export interface CurrencyAmount {
  CNY: number
  HKD: number
  USD: number
}

export interface PaperAccountSummary {
  cash: CurrencyAmount | number  // 支持新旧格式
  realized_pnl: CurrencyAmount | number  // 支持新旧格式
  positions_value: CurrencyAmount
  equity: CurrencyAmount | number  // 支持新旧格式
  updated_at?: string
}

export interface PaperPositionItem {
  position_id?: string
  code: string
  name?: string
  market?: string
  currency?: string
  quantity: number
  available_qty?: number
  avg_cost: number
  last_price?: number | null
  market_value?: number
  unrealized_pnl?: number | null
}

export interface PaperOrderItem {
  user_id?: string
  code: string
  side: 'buy' | 'sell'
  quantity: number
  price: number
  amount: number
  status: 'filled' | 'rejected' | string
  created_at: string
  filled_at?: string
  source_type?: string
  source_observation_id?: string
  source_strategy_id?: string
  source_task_id?: string
  source_candidate?: Record<string, unknown>
}

export interface GetAccountResponse {
  account: PaperAccountSummary
  positions: PaperPositionItem[]
}

export interface PlaceOrderPayload {
  code: string
  side: 'buy' | 'sell'
  quantity: number
  analysis_id?: string
  source_type?: string
  source_observation_id?: string
  source_strategy_id?: string
  source_task_id?: string
  source_candidate?: Record<string, unknown>
}

export const paperApi = {
  async getAccount() {
    return ApiClient.get<GetAccountResponse>('/api/paper/account')
  },
  async placeOrder(data: PlaceOrderPayload) {
    return ApiClient.post<{ order: PaperOrderItem }>('/api/paper/order', data, { showLoading: true })
  },
  async getPositions() {
    return ApiClient.get<{ items: PaperPositionItem[] }>('/api/paper/positions')
  },
  async listPositionReviewNotes(positionId: string) {
    return ApiClient.get<{ items: Array<{ note_id: string; content: string; created_at: string }> }>(
      `/api/paper/positions/${positionId}/review-notes`
    )
  },
  async addPositionReview(positionId: string, content: string) {
    return ApiClient.post<{ note_id: string; content: string; created_at: string }>(
      `/api/paper/positions/${positionId}/review`,
      { content }
    )
  },
  async getOrders(limit = 50) {
    return ApiClient.get<{ items: PaperOrderItem[] }>(`/api/paper/orders`, { limit })
  },
  async resetAccount() {
    // 后端要求 confirm=true
    return ApiClient.post<{ message: string; cash: number }>(`/api/paper/reset?confirm=true`)
  }
}
