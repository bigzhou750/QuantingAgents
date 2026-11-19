import { describe, expect, it } from 'vitest'
import { readFileSync } from 'node:fs'
import { fileURLToPath } from 'node:url'
import { dirname, resolve } from 'node:path'

const __dirname = dirname(fileURLToPath(import.meta.url))
const marketplaceSource = readFileSync(resolve(__dirname, '../Marketplace.vue'), 'utf-8')
const detailSource = readFileSync(resolve(__dirname, '../MarketplaceDetail.vue'), 'utf-8')
const strategiesSource = readFileSync(resolve(__dirname, '../Strategies.vue'), 'utf-8')

describe('strategy marketplace pages', () => {
  it('strategy cards expose beginner-facing copy and data preparation state', () => {
    expect(marketplaceSource).toContain('策略广场')
    expect(marketplaceSource).toContain('marketplaceDataStatus')
    expect(marketplaceSource).toContain('MarketplaceDetail')
  })

  it('detail page explains rules, boundaries, and the join action', () => {
    expect(detailSource).toContain('这个策略在找什么')
    expect(detailSource).toContain('为什么这些条件有意义')
    expect(detailSource).toContain('什么情况下容易表现不好')
    expect(detailSource).toContain('加入我的策略')
  })

  it('my strategies distinguishes marketplace-sourced and self-built strategies', () => {
    expect(strategiesSource).toContain('策略广场')
    expect(strategiesSource).toContain('自建')
  })
})
