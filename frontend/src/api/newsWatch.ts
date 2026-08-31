import { ApiClient } from './request'
import type { LatestNewsResponse, NewsQueryResponse } from './news'
import type { NewsResponse } from './stocks'

export type NewsWatchItemType = 'stock' | 'news'
export type NewsWatchImpactLevel = 'low' | 'medium' | 'high'

export interface CollectNewsWatchItemReq {
  item_type: NewsWatchItemType
  symbol?: string
  news_id?: string
  source_page: string
  title?: string
}

export interface NewsWatchCollectedItem {
  _id: string
  item_type: NewsWatchItemType
  symbol?: string
  news_id?: string
  source_page: string
  title?: string
  collected_at: string
}

export interface NewsWatchImpact {
  stock_code: string
  stock_name: string
  impact_level: NewsWatchImpactLevel
  news_count: number
  evidence_note: string
  latest_news_time?: string
  sample_headlines: string[]
}

export interface NewsWatchImpactAnalysisResult {
  has_holdings: boolean
  holdings_count: number
  data_sufficient: boolean
  boundary_note: string
  impacts: NewsWatchImpact[]
}

export interface NewsWatchAlertRecord {
  _id: string
  stock_code: string
  stock_name: string
  impact_level: NewsWatchImpactLevel
  channel: string
  status: string
  trigger_reason: string
  created_at: string
}

export interface NewsWatchSimulateResult {
  generated_count: number
  alerts: NewsWatchAlertRecord[]
  note: string
  analysis_summary?: {
    holdings_count: number
    data_sufficient: boolean
  }
}

export const newsWatchApi = {
  collect: (payload: CollectNewsWatchItemReq) =>
    ApiClient.post<NewsWatchCollectedItem>('/api/news-watch/collect', payload),

  listCollected: (params: { limit?: number; skip?: number; item_type?: NewsWatchItemType } = {}) =>
    ApiClient.get<{ items: NewsWatchCollectedItem[]; total: number }>('/api/news-watch/collected', params),

  removeCollected: (itemId: string) =>
    ApiClient.delete('/api/news-watch/collected/' + itemId),

  analyzeImpact: (params: { hours_back?: number } = {}) =>
    ApiClient.post<NewsWatchImpactAnalysisResult>('/api/news-watch/impact-analysis', null, { params }),

  getAlertConfig: () =>
    ApiClient.get<{ threshold: NewsWatchImpactLevel }>('/api/news-watch/alerts/config'),

  updateAlertConfig: (threshold: NewsWatchImpactLevel) =>
    ApiClient.put<{ threshold: NewsWatchImpactLevel }>('/api/news-watch/alerts/config', { threshold }),

  simulateAlerts: (params: { hours_back?: number } = {}) =>
    ApiClient.post<NewsWatchSimulateResult>('/api/news-watch/alerts/simulate', null, { params }),

  listAlerts: (params: { limit?: number; skip?: number } = {}) =>
    ApiClient.get<{ records: NewsWatchAlertRecord[]; total: number }>('/api/news-watch/alerts', params),

  getLatestNews: (params: { symbol?: string; limit?: number; hours_back?: number } = {}) =>
    ApiClient.get<LatestNewsResponse>('/api/news-data/latest', params),

  queryStockNews: (symbol: string, params: { limit?: number; hours_back?: number } = {}) =>
    ApiClient.get<NewsQueryResponse>('/api/news-data/query/' + symbol, params),

  getStockNews: (symbol: string, params: { days?: number; limit?: number; include_announcements?: boolean } = {}) =>
    ApiClient.get<NewsResponse>('/api/stocks/' + symbol + '/news', params),
}
