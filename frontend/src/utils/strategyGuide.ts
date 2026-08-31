// 个人投资助手：策略选择向导的纯逻辑
// 输出策略类型匹配建议、适用场景和证据层级，不输出股票推荐

export interface StrategyGuideRecommendation {
  name: string
  description: string
  audience: string
  marketCondition: string
  evidenceLevel: string
  invalidation: string
  screeningCriteria: {
    pe_max?: number
    roe_min?: number
    rsi_min?: number
    rsi_max?: number
    ma_trend?: string
  }
}

export const strategyGuideMap: Record<string, StrategyGuideRecommendation> = {
  conservative_value: {
    name: '低估值稳健策略',
    description: '偏好低估值、财务稳健的标的，减少短期波动带来的心理压力。',
    audience: '风险承受能力较低、希望长期持有的新手',
    marketCondition: '震荡或下行市场中相对抗跌，趋势市中弹性可能不足',
    evidenceLevel: '基于历史财务指标和估值回归假设，证据强度：中',
    invalidation: '若行业景气度持续恶化或分红能力下降，策略假设可能失效',
    screeningCriteria: { pe_max: 25, roe_min: 8 },
  },
  conservative_dividend: {
    name: '红利稳健策略',
    description: '优先选择分红稳定、现金流健康的标的。',
    audience: '希望获得稳定现金流、风险偏好较低的新手',
    marketCondition: '适合大多数市场环境，趋势市中涨幅可能落后',
    evidenceLevel: '基于历史分红记录和财务稳健性，证据强度：中',
    invalidation: '若公司分红政策改变或盈利能力下滑，策略假设可能失效',
    screeningCriteria: { pe_max: 30, roe_min: 8 },
  },
  balanced_value: {
    name: '均衡价值策略',
    description: '在控制风险的同时保留一定成长空间，兼顾估值与质地。',
    audience: '希望在稳健和成长之间取得平衡的用户',
    marketCondition: '适合大多数市场阶段，需要定期复核估值变化',
    evidenceLevel: '基于估值和盈利质量的综合规则匹配，证据强度：中',
    invalidation: '若市场持续单边下跌或标的基本面恶化，策略假设可能失效',
    screeningCriteria: { pe_max: 30, roe_min: 8 },
  },
  balanced_growth: {
    name: '均衡成长策略',
    description: '关注业绩增长且估值合理的标的，兼顾成长性和安全边际。',
    audience: '希望适度参与成长机会但仍看重风险控制的用户',
    marketCondition: '适合温和上升或结构性行情，剧烈波动市中需谨慎',
    evidenceLevel: '基于历史成长指标和趋势规则，证据强度：中',
    invalidation: '若业绩增速大幅放缓或估值过高，策略假设可能失效',
    screeningCriteria: { pe_max: 45, roe_min: 10 },
  },
  aggressive_growth: {
    name: '成长趋势策略',
    description: '关注业绩持续增长且价格处于上升趋势的标的，追求更高弹性。',
    audience: '能承受较大波动、希望参与成长机会的用户',
    marketCondition: '适合结构性成长行情，下行市中波动可能明显放大',
    evidenceLevel: '基于历史成长和动量规则，证据强度：中偏低，需结合体检验证',
    invalidation: '若趋势反转或成长逻辑被证伪，策略假设可能快速失效',
    screeningCriteria: { pe_max: 60, roe_min: 12, rsi_min: 40, rsi_max: 70, ma_trend: 'up' },
  },
  aggressive_momentum: {
    name: '趋势跟踪策略',
    description: '跟随价格趋势捕捉阶段性机会，换手可能更频繁。',
    audience: '能承受较大波动、接受较高操作频率的用户',
    marketCondition: '适合有明确趋势的市场，震荡市中信号可能失真',
    evidenceLevel: '基于历史价格趋势规则，证据强度：低，需持续跟踪验证',
    invalidation: '若趋势快速反转或波动率骤升，策略假设可能迅速失效',
    screeningCriteria: { rsi_min: 40, rsi_max: 70, ma_trend: 'up' },
  },
}

export const DEFAULT_GUIDE_KEY = 'balanced_value'

/**
 * 根据风险偏好和选股逻辑，获取策略类型匹配建议。
 * 未匹配到组合时回退到均衡价值策略，而不是抛出错误或留空。
 */
export function getStrategyGuideRecommendation(
  risk: string,
  style: string
): StrategyGuideRecommendation {
  const key = `${risk}_${style}`
  return strategyGuideMap[key] || strategyGuideMap[DEFAULT_GUIDE_KEY]
}
