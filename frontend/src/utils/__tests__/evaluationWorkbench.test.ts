import { describe, expect, it } from 'vitest'
import { readFileSync } from 'node:fs'
import { fileURLToPath } from 'node:url'
import { dirname, resolve } from 'node:path'

const __dirname = dirname(fileURLToPath(import.meta.url))
const readView = (name: string) => readFileSync(resolve(__dirname, `../../views/Evaluation/${name}`), 'utf-8')

describe('Evaluation production workbench', () => {
  it('supports case editing, batch operations and JSON/CSV/Excel import', () => {
    const source = readView('DatasetDetail.vue')
    expect(source).toContain('cases/upload')
    expect(source).toContain('.csv,.xlsx')
    expect(source).toContain('batch-update')
    expect(source).toContain('publish-version')
  })

  it('persists scorer, judge, review and data-window configuration', () => {
    const source = readView('RunCreate.vue')
    expect(source).toContain('scorer_names')
    expect(source).toContain('judge_model')
    expect(source).toContain('rubric_version')
    expect(source).toContain('low_confidence_threshold')
    expect(source).toContain('data_window')
  })

  it('provides report export, trace grouping and claim evidence views', () => {
    expect(readView('RunReport.vue')).toContain('exportCsv')
    expect(readView('RunReport.vue')).toContain('Claim-Evidence')
    expect(readView('RunDetail.vue')).toContain('groupedTraceEvents')
    expect(readView('HumanReview.vue')).toContain('claimEvidenceList')
  })

  it('exposes trend stability, regression and governance controls', () => {
    const source = readView('Trends.vue')
    expect(source).toContain('pass_at_k')
    expect(source).toContain('pass_pow_k')
    expect(source).toContain('regression-tasks')
    expect(source).toContain('governance/config')
    expect(source).toContain('release-gate/config')
  })
})
