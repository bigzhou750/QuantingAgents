export const marketplaceTagLabels: Record<string, string> = {
  value: '价值',
  growth: '成长',
  dividend: '红利',
  momentum: '趋势',
  balanced: '均衡',
  conservative: '稳健',
}

export const marketplaceCriteriaLabels: Record<string, string> = {
  pe_max: '市盈率上限',
  roe_min: 'ROE下限',
  dividend_yield_min: '股息率下限',
  rsi_min: 'RSI下限',
  rsi_max: 'RSI上限',
  ma_trend: '均线趋势',
  market_cap_min: '市值下限',
}

export interface MarketplaceDataStatusInput {
  data_preparation_status?: string | null
  simulation_data_sufficient?: boolean
  simulation_cumulative_return?: number | null
  simulation_max_drawdown?: number | null
}

export function marketplaceTagLabel(tag: string): string {
  return marketplaceTagLabels[tag] || tag
}

export function marketplaceCriteriaLabel(key: string): string {
  return marketplaceCriteriaLabels[key] || key
}

export function marketplaceDataStatus(template?: MarketplaceDataStatusInput | null): string {
  if (!template) return '数据准备中'
  if (template.simulation_data_sufficient === false || template.data_preparation_status === 'insufficient') {
    return '数据不足'
  }
  if (template.data_preparation_status === 'ready' && template.simulation_data_sufficient) {
    return '数据已准备'
  }
  return '数据准备中'
}

export function marketplaceMetricText(template?: MarketplaceDataStatusInput | null): string {
  if (!template) return '数据准备中'
  if (marketplaceDataStatus(template) === '数据已准备' && template.simulation_cumulative_return != null) {
    return `累计收益 ${(template.simulation_cumulative_return * 100).toFixed(1)}%`
  }
  return marketplaceDataStatus(template)
}
