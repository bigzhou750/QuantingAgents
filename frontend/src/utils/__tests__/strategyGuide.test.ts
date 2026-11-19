import { describe, expect, it } from 'vitest'
import { getStrategyGuideRecommendation, strategyGuideMap, DEFAULT_GUIDE_KEY } from '../strategyGuide'

describe('strategyGuide', () => {
  it('returns the matching recommendation for a known risk/style combination', () => {
    const rec = getStrategyGuideRecommendation('conservative', 'value')
    expect(rec.name).toBe('低估值稳健策略')
    expect(rec.evidenceLevel).toContain('证据强度')
    expect(rec.invalidation).toBeTruthy()
  })

  it('falls back to the balanced/value recommendation when no combination matches', () => {
    const rec = getStrategyGuideRecommendation('unknown', 'unknown')
    expect(rec).toEqual(strategyGuideMap[DEFAULT_GUIDE_KEY])
  })

  it('never outputs a stock recommendation, only strategy-type guidance fields', () => {
    Object.values(strategyGuideMap).forEach((rec) => {
      expect(rec).not.toHaveProperty('stock_code')
      expect(rec).not.toHaveProperty('candidates')
      expect(rec.description).not.toMatch(/买入|卖出/)
    })
  })

  it('covers all risk x style combinations referenced by the wizard', () => {
    const risks = ['conservative', 'balanced', 'aggressive']
    const styles = ['value', 'growth', 'dividend', 'momentum']

    risks.forEach((risk) => {
      styles.forEach((style) => {
        const rec = getStrategyGuideRecommendation(risk, style)
        expect(rec.audience).toBeTruthy()
        expect(rec.marketCondition).toBeTruthy()
      })
    })
  })
})
