import { describe, expect, it } from 'vitest'
import { readFileSync } from 'node:fs'
import { fileURLToPath } from 'node:url'
import { dirname, resolve } from 'node:path'

const __dirname = dirname(fileURLToPath(import.meta.url))

const profileSource = readFileSync(
  resolve(__dirname, '../../views/PersonalInvestment/Profile.vue'),
  'utf-8'
)

const strategiesSource = readFileSync(
  resolve(__dirname, '../../views/PersonalInvestment/Strategies.vue'),
  'utf-8'
)

describe('Profile.vue onboarding templates', () => {
  it('defines conservative, balanced and aggressive profile templates', () => {
    expect(profileSource).toContain("key: 'conservative'")
    expect(profileSource).toContain("key: 'balanced'")
    expect(profileSource).toContain("key: 'aggressive'")
  })

  it('shows onboarding state driven by isFirstTime', () => {
    expect(profileSource).toContain('isFirstTime')
    expect(profileSource).toContain('applyTemplate')
  })

  it('never presents templates as guaranteed recommendations', () => {
    expect(profileSource).toMatch(/不代表推荐结论/)
  })
})

describe('Strategies.vue default templates and task wizard', () => {
  it('defines at least one default strategy template', () => {
    expect(strategiesSource).toContain('strategyTemplates')
    expect(strategiesSource).toContain('createFromTemplate')
  })

  it('exposes a strategy guidance dialog entry', () => {
    expect(strategiesSource).toContain('showGuideDialog')
    expect(strategiesSource).toContain('策略怎么选')
  })

  it('routes strategy execution through a confirmation wizard instead of firing tasks directly', () => {
    expect(strategiesSource).toContain('openTaskWizard')
    expect(strategiesSource).toContain('confirmTaskWizard')
    expect(strategiesSource).toContain('showTaskWizard')
  })

  it('shows evidence level and invalidation conditions in the guidance result', () => {
    expect(strategiesSource).toContain('证据层级')
    expect(strategiesSource).toContain('失效条件')
  })
})
