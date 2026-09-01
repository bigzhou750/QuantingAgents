import { describe, expect, it } from 'vitest'
import {
  marketplaceCriteriaLabel,
  marketplaceDataStatus,
  marketplaceMetricText,
  marketplaceTagLabel,
} from '../marketplace'

describe('marketplace helpers', () => {
  it('translates marketplace tags and criteria into beginner-facing labels', () => {
    expect(marketplaceTagLabel('dividend')).toBe('红利')
    expect(marketplaceCriteriaLabel('pe_max')).toBe('市盈率上限')
  })

  it('shows data preparation state instead of blank metrics', () => {
    expect(marketplaceDataStatus({ data_preparation_status: 'ready', simulation_data_sufficient: true, simulation_cumulative_return: 0.12 })).toBe('数据已准备')
    expect(marketplaceDataStatus({})).toBe('数据准备中')
  })

  it('formats a metric only when simulation data is ready', () => {
    expect(marketplaceMetricText({ data_preparation_status: 'ready', simulation_data_sufficient: true, simulation_cumulative_return: 0.12 })).toBe('累计收益 12.0%')
    expect(marketplaceMetricText({})).toBe('数据准备中')
  })
})
