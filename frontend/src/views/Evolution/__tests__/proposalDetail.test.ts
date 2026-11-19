import { describe, expect, it } from 'vitest'
import {
  actionLabel,
  buildDecisionSummary,
  buildDiffSummary,
  getActionStates,
  getAuditState,
  getVerificationState,
  riskLevelLabel,
  statusLabel,
  summarizeComparison,
  triggerTypeLabel,
  verificationStatusLabel,
} from '../proposalDetail'

describe('proposal detail labels', () => {
  it('maps every proposal enum to readable Chinese text', () => {
    expect(statusLabel('pending_verify')).toBe('待验证')
    expect(statusLabel('promoted')).toBe('已发布')
    expect(statusLabel('stopped')).toBe('已停止')
    expect(triggerTypeLabel('bad_case_threshold')).toBe('Bad Case 阈值')
    expect(triggerTypeLabel('regression')).toBe('趋势回退')
    expect(riskLevelLabel('critical')).toBe('严重风险')
    expect(verificationStatusLabel('completed')).toBe('已完成')
    expect(verificationStatusLabel('')).toBe('未生成')
    expect(actionLabel('reject')).toBe('拒绝')
  })
})

describe('proposal decision summary', () => {
  it('shows frozen baseline and candidate as readable values', () => {
    const summary = buildDecisionSummary({
      status: 'approved',
      trigger_type: 'regression',
      risk_level: 'high',
      target_artifact_type: 'skill',
      baseline_artifact_version: '1.2.0',
      candidate_version: '1.2.1',
      target_artifact_id: 'art_skill_general',
    })
    expect(summary.statusLabel).toBe('已批准')
    expect(summary.triggerLabel).toBe('趋势回退')
    expect(summary.riskLabel).toBe('高风险')
    expect(summary.baselineLabel).toBe('1.2.0')
    expect(summary.candidateLabel).toBe('1.2.1')
    expect(summary.artifactTypeLabel).toBe('Skill')
  })
})

describe('diff and comparison summaries', () => {
  it('extracts change description and keeps raw JSON available', () => {
    const summary = buildDiffSummary({
      change_description: '优化工具路由',
      sections_affected: ['tool_selection', 'output_format'],
      parameters: { retry_limit: 3 },
    })
    expect(summary.description).toBe('优化工具路由')
    expect(summary.sections).toEqual(['tool_selection', 'output_format'])
    expect(summary.parameters[0]).toEqual({ key: 'retry_limit', value: '3' })
    expect(summary.rawAvailable).toBe(true)
  })

  it('flattens verification gate and baseline/candidate score rows', () => {
    const metrics = summarizeComparison({
      pass_at_k: {
        baseline: { pass_at_k: 0.8, pass_pow_k: 0.75, k: 3 },
        candidate: { pass_at_k: 0.9, pass_pow_k: 0.85, k: 3 },
      },
      score_aggregation: {
        baseline: { scores: { safety: { avg_score: 0.9 }, evidence_quality: { avg_score: 0.7 } } },
        candidate: { scores: { safety: { avg_score: 0.95 }, evidence_quality: { avg_score: 0.8 } } },
      },
      gate: {
        passed: true,
        checks: [{ name: 'success_rate', passed: true }],
      },
    })
    const rows = metrics.flatMap(group => group.rows)
    const labels = rows.map(item => item.label)
    expect(labels).toContain('Pass@K')
    expect(labels).toContain('avg_score')
    expect(labels).toContain('success_rate')
    expect(metrics.find(group => group.title === 'safety')?.rows.find(item => item.label === 'avg_score')?.candidate).toBe('0.9500')
    expect(rows.find(item => item.label === 'Pass@K')?.baseline).toBe('0.8000')
    expect(rows.find(item => item.label === 'Pass@K')?.candidate).toBe('0.9000')
    expect(rows.find(item => item.label === 'Pass^K')?.baseline).toBe('0.7500')
    expect(rows.find(item => item.label === 'Pass^K')?.candidate).toBe('0.8500')
  })
})

describe('empty states and action states', () => {
  it('explains missing verification and approval records by stage', () => {
    expect(getVerificationState(null, { status: 'pending_verify' }).title).toBe('尚未执行验证')
    expect(getVerificationState(null, { status: 'approved' }).title).toBe('验证结果暂不可用')
    expect(getAuditState([], { status: 'pending_verify' }).title).toBe('尚未进入审批阶段')
    expect(getAuditState([], { status: 'verified' }).title).toBe('等待审批')
    expect(getAuditState([], { status: 'approved' }).title).toBe('审批记录缺失')
  })

  it('blocks verification for forbidden targets and promotion for failed gates', () => {
    const forbidden = getActionStates({ status: 'pending_verify', forbidden_target: true }, null)
    expect(forbidden.canVerify).toBe(false)
    expect(forbidden.verifyDisabledReason).toContain('禁止修改')

    const gateFailed = getActionStates(
      { status: 'approved', forbidden_target: false },
      {
        status: 'completed',
        cleanup_status: 'cleaned',
        gate_result: { passed: false },
      },
    )
    expect(gateFailed.canPromote).toBe(false)
    expect(gateFailed.promoteDisabledReason).toContain('门禁')
  })

  it('enables promote only for approved completed cleaned gate-passed proposals', () => {
    const states = getActionStates(
      { status: 'approved', forbidden_target: false },
      {
        status: 'completed',
        cleanup_status: 'cleaned',
        gate_result: { passed: true },
      },
    )
    expect(states.canPromote).toBe(true)
    expect(states.canApprove).toBe(false)
  })
})
