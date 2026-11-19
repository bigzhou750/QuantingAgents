import { ApiClient } from './request'

export interface AddObservationPayload {
  stock_code: string
  stock_name?: string
  market?: string
  source_type?: string
  source_strategy_id?: string
  source_task_id?: string
  match_reasons?: string[]
  risk_warnings?: string[]
  user_notes?: string
  data_as_of?: string
}

export const observationApi = {
  list(params?: Record<string, unknown>) {
    return ApiClient.get('/api/investment/observations', params)
  },
  get(observationId: string) {
    return ApiClient.get(`/api/investment/observations/${observationId}`)
  },
  add(data: AddObservationPayload) {
    return ApiClient.post('/api/investment/observations', data)
  },
  update(observationId: string, data: Record<string, unknown>) {
    return ApiClient.put(`/api/investment/observations/${observationId}`, data)
  },
  remove(observationId: string) {
    return ApiClient.post(`/api/investment/observations/${observationId}/remove`)
  },
  addReview(observationId: string, content: string) {
    return ApiClient.post(`/api/investment/observations/${observationId}/review`, { content })
  },
  getReviewSummary() {
    return ApiClient.get('/api/investment/observations/review-summary')
  },
}
