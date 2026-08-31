import { describe, expect, it } from 'vitest'
import { readFileSync } from 'node:fs'
import { fileURLToPath } from 'node:url'
import { dirname, resolve } from 'node:path'

const __dirname = dirname(fileURLToPath(import.meta.url))

const workbenchSource = readFileSync(
  resolve(__dirname, '../../views/NewsWatch/Workbench.vue'),
  'utf-8'
)

const impactSource = readFileSync(
  resolve(__dirname, '../../views/NewsWatch/ImpactAnalysis.vue'),
  'utf-8'
)

const alertSource = readFileSync(
  resolve(__dirname, '../../views/NewsWatch/AlertConfig.vue'),
  'utf-8'
)

const sidebarSource = readFileSync(
  resolve(__dirname, '../../components/Layout/SidebarMenu.vue'),
  'utf-8'
)

const apiSource = readFileSync(
  resolve(__dirname, '../../api/newsWatch.ts'),
  'utf-8'
)

describe('NewsWatch Workbench', () => {
  it('shows empty state with guidance when no items collected', () => {
    expect(workbenchSource).toContain('还没有收集任何关注对象')
    expect(workbenchSource).toContain('股票详情页')
    expect(workbenchSource).toContain('自选股列表')
    expect(workbenchSource).toContain('新闻列表')
  })

  it('calls the news-watch collect API for removal', () => {
    expect(apiSource).toContain('/api/news-watch/collected')
    expect(workbenchSource).toContain('newsWatchApi.listCollected')
    expect(workbenchSource).toContain('newsWatchApi.removeCollected')
  })

  it('shows a related news stream with market-news fallback', () => {
    expect(workbenchSource).toContain('相关新闻流')
    expect(workbenchSource).toContain('暂无关注对象，展示近期市场新闻')
    expect(workbenchSource).toContain('newsWatchApi.getLatestNews')
    expect(workbenchSource).toContain('newsWatchApi.queryStockNews')
  })

  it('uses research-oriented copy, not trading language', () => {
    expect(workbenchSource).not.toMatch(/买入|卖出|推荐/)
    expect(workbenchSource).toContain('不构成任何投资建议')
  })
})

describe('NewsWatch ImpactAnalysis', () => {
  it('calls the impact-analysis API endpoint', () => {
    expect(apiSource).toContain('/api/news-watch/impact-analysis')
    expect(impactSource).toContain('newsWatchApi.analyzeImpact')
  })

  it('displays three-level impact severity tags', () => {
    expect(impactSource).toContain('translateImpactLevel')
    expect(impactSource).toContain("low: '低'")
    expect(impactSource).toContain("medium: '中'")
    expect(impactSource).toContain("high: '高'")
  })

  it('includes boundary explanation card', () => {
    expect(impactSource).toContain('结论边界说明')
    expect(impactSource).toContain('不构成任何买入或卖出建议')
  })

  it('handles no-holdings state gracefully', () => {
    expect(impactSource).toContain('暂无持仓数据')
    expect(impactSource).toContain('去设置持仓')
  })
})

describe('NewsWatch AlertConfig', () => {
  it('provides three threshold options', () => {
    expect(alertSource).toContain('value="low"')
    expect(alertSource).toContain('value="medium"')
    expect(alertSource).toContain('value="high"')
  })

  it('clearly marks alerts as simulated', () => {
    expect(alertSource).toContain('模拟')
    expect(alertSource).toContain('未实际发送任何外部消息')
    expect(alertSource).toContain('simulated')
  })

  it('calls the simulate and config APIs', () => {
    expect(apiSource).toContain('/api/news-watch/alerts/simulate')
    expect(apiSource).toContain('/api/news-watch/alerts/config')
    expect(alertSource).toContain('newsWatchApi.simulateAlerts')
    expect(alertSource).toContain('newsWatchApi.getAlertConfig')
  })

  it('uses the shared authenticated API client', () => {
    expect(apiSource).toContain("import { ApiClient } from './request'")
    expect(workbenchSource).not.toContain("import axios from 'axios'")
    expect(impactSource).not.toContain("import axios from 'axios'")
    expect(alertSource).not.toContain("import axios from 'axios'")
  })
})

describe('Sidebar navigation for NewsWatch', () => {
  it('includes all three news-watch sub-menu entries', () => {
    expect(sidebarSource).toContain('index="/news-watch/workbench"')
    expect(sidebarSource).toContain('index="/news-watch/impact"')
    expect(sidebarSource).toContain('index="/news-watch/alerts"')
  })

  it('imports Bell icon for the news-watch menu', () => {
    expect(sidebarSource).toContain('Bell')
  })
})
