export const proposalStatusLabels: Record<string, string> = {
  draft: '草稿',
  pending_verify: '待验证',
  verifying: '验证中',
  verified: '已验证',
  approved: '已批准',
  rejected: '已拒绝',
  promoted: '已发布',
  rollback: '已回滚',
  stopped: '已停止',
}

export const proposalStatusTagTypes: Record<string, string> = {
  draft: 'info',
  pending_verify: 'warning',
  verifying: 'warning',
  verified: 'success',
  approved: 'success',
  rejected: 'danger',
  promoted: 'success',
  rollback: 'warning',
  stopped: 'danger',
}

export const triggerTypeLabels: Record<string, string> = {
  run_completed: '运行完成',
  regression: '趋势回退',
  bad_case_threshold: 'Bad Case 阈值',
  scheduled: '定时触发',
}

export const riskLevelLabels: Record<string, string> = {
  low: '低风险',
  medium: '中风险',
  high: '高风险',
  critical: '严重风险',
}

export const riskLevelTagTypes: Record<string, string> = {
  low: 'success',
  medium: 'warning',
  high: 'danger',
  critical: 'danger',
}

export const artifactTypeLabels: Record<string, string> = {
  skill: 'Skill',
  prompt: 'Prompt',
  policy: 'Policy',
  rubric: 'Rubric',
  case: 'Case',
}

export const actionLabels: Record<string, string> = {
  approve: '批准',
  reject: '拒绝',
  comment: '评论',
}

export const verificationStatusLabels: Record<string, string> = {
  pending: '等待运行',
  running: '运行中',
  completed: '已完成',
  failed: '失败',
  cancelled: '已取消',
  cleanup_failed: '清理失败',
}

export function statusLabel(status?: string | null): string {
  return status ? proposalStatusLabels[status] || status : '未知'
}

export function statusTagType(status?: string | null): string {
  return status ? proposalStatusTagTypes[status] || 'info' : 'info'
}

export function triggerTypeLabel(triggerType?: string | null): string {
  return triggerType ? triggerTypeLabels[triggerType] || triggerType : '未知'
}

export function riskLevelLabel(riskLevel?: string | null): string {
  return riskLevel ? riskLevelLabels[riskLevel] || riskLevel : '未评估'
}

export function riskLevelTagType(riskLevel?: string | null): string {
  return riskLevel ? riskLevelTagTypes[riskLevel] || 'info' : 'info'
}

export function artifactTypeLabel(artifactType?: string | null): string {
  return artifactType ? artifactTypeLabels[artifactType] || artifactType : '未知'
}

export function actionLabel(action?: string | null): string {
  return action ? actionLabels[action] || action : '未知动作'
}

export function verificationStatusLabel(status?: string | null): string {
  return status ? verificationStatusLabels[status] || status : '未生成'
}

export interface DecisionSummary {
  statusLabel: string
  statusTagType: any
  triggerLabel: string
  riskLabel: string
  riskTagType: any
  artifactTypeLabel: string
  baselineLabel: string
  candidateLabel: string
  releaseReady: boolean
  releaseStateLabel: string
  releaseStateHint: string
  stopReasonLabel: string
}

export function buildDecisionSummary(
  proposal: Record<string, any>,
  verification?: Record<string, any> | null,
): DecisionSummary {
  const baseline = proposal.baseline_artifact_version || proposal.baseline_version || ''
  const candidate = proposal.candidate_version || ''
  const releaseReady = getActionStates(proposal, verification).canPromote
  return {
    statusLabel: statusLabel(proposal.status),
    statusTagType: statusTagType(proposal.status),
    triggerLabel: triggerTypeLabel(proposal.trigger_type),
    riskLabel: riskLevelLabel(proposal.risk_level),
    riskTagType: riskLevelTagType(proposal.risk_level),
    artifactTypeLabel: artifactTypeLabel(proposal.target_artifact_type),
    baselineLabel: baseline || '尚未固化',
    candidateLabel: candidate || '尚未生成',
    releaseReady,
    releaseStateLabel: releaseReady ? '满足发布条件' : '尚未就绪',
    releaseStateHint: releaseReady
      ? '验证、审批、基线和 smoke test 条件均已满足。'
      : releaseBlockReason(proposal) || '验证完成并通过审批后可发布。',
    stopReasonLabel: proposal.stop_reason || '—',
  }
}

export interface DiffSummary {
  description: string
  sections: string[]
  parameters: Array<{ key: string; value: string }>
  rawAvailable: boolean
}

export function buildDiffSummary(diff?: Record<string, any> | null): DiffSummary {
  const raw = diff || {}
  const parameters = Object.entries(raw.parameters || {}).map(([key, value]) => ({
    key,
    value: typeof value === 'string' ? value : JSON.stringify(value),
  }))
  return {
    description: raw.change_description || raw.changeDescription || '',
    sections: Array.isArray(raw.sections_affected) ? raw.sections_affected : [],
    parameters,
    rawAvailable: Boolean(diff && Object.keys(diff).length),
  }
}

export interface MetricSummary {
  label: string
  baseline: string
  candidate: string
  conclusion: string
  status: 'pass' | 'fail' | 'neutral'
}

export interface MetricGroup {
  key: string
  title: string
  rows: MetricSummary[]
}

export function summarizeComparison(comparison?: Record<string, any> | null): MetricGroup[] {
  const raw = comparison || {}
  const groups: MetricGroup[] = []
  const runComparison = raw.comparison?.runs || raw.runs || []
  const baselineRun = runComparison[0] || {}
  const candidateRun = runComparison[1] || {}

  const overviewRows = rowsFromObjects(baselineRun, candidateRun, [
    ['total_trials', '总试验数'],
    ['completed_count', '完成数'],
    ['failed_count', '失败数'],
    ['cancelled_count', '取消数'],
    ['success_rate', '成功率'],
    ['failure_rate', '失败率'],
  ])
  if (overviewRows.length) groups.push({ key: 'overview', title: '运行概览', rows: overviewRows })

  const latencyRows = rowsFromObjects(baselineRun.latency, candidateRun.latency, [], 'ms')
  if (latencyRows.length) groups.push({ key: 'latency', title: '性能与延迟', rows: latencyRows })

  const costRows = rowsFromObjects(baselineRun.cost, candidateRun.cost, [], 'USD')
  const tokenRows = rowsFromObjects(baselineRun.tokens, candidateRun.tokens, [], 'tokens')
  if (costRows.length || tokenRows.length) {
    groups.push({ key: 'cost', title: '成本与 Token', rows: [...costRows, ...tokenRows] })
  }

  const passAtK = raw.pass_at_k || {}
  const passRows = rowsFromObjects(passAtK.baseline, passAtK.candidate, [
    ['pass_at_k', 'Pass@K'],
    ['pass_pow_k', 'Pass^K'],
    ['k', 'K 值'],
    ['cases', 'Case 数'],
  ])
  if (passRows.length) groups.push({ key: 'pass-at-k', title: 'Pass@K / Pass^K', rows: passRows })

  const scoreGroups = scoreAggregationGroups(raw.score_aggregation)
  if (scoreGroups.length) groups.push(...scoreGroups)

  const checks = raw.gate?.checks
  if (Array.isArray(checks) && checks.length) {
    groups.push({
      key: 'gate',
      title: '发布门禁',
      rows: checks.map((check: Record<string, any>) => ({
        label: check.name || '未命名检查',
        baseline: '—',
        candidate: check.passed ? '通过' : '未通过',
        conclusion: check.passed ? '通过' : '未通过',
        status: check.passed ? 'pass' : 'fail',
      })),
    })
  }

  if (raw.regression_detected !== undefined) {
    groups.push({
      key: 'regression',
      title: '回归检测',
      rows: [{
        label: '成功率回归',
        baseline: '—',
        candidate: '—',
        conclusion: raw.regression_detected
          ? `检出，偏差 ${formatMetricValue(raw.regression_delta)}`
          : '未检出',
        status: raw.regression_detected ? 'fail' : 'pass',
      }],
    })
  }

  if (raw.error) {
    groups.push({
      key: 'error',
      title: '对比异常',
      rows: [{ label: '错误', baseline: '—', candidate: '—', conclusion: raw.error, status: 'fail' }],
    })
  }

  return groups.length
    ? groups
    : [{ key: 'empty', title: '指标对比', rows: [{ label: '对比结果', baseline: '—', candidate: '—', conclusion: '尚未生成', status: 'neutral' }] }]
}

function rowsFromObjects(
  baseline?: Record<string, any> | null,
  candidate?: Record<string, any> | null,
  labels: Array<[string, string]> = [],
  suffix = '',
): MetricSummary[] {
  if (!baseline && !candidate) return []
  const baselineObject = baseline || {}
  const candidateObject = candidate || {}
  const labelMap = new Map(labels)
  const keys = labels.length
    ? labels.map(([key]) => key)
    : [...new Set([...Object.keys(baselineObject), ...Object.keys(candidateObject)])]
  return keys.flatMap(key => {
    const baselineValue = baselineObject[key]
    const candidateValue = candidateObject[key]
    if (baselineValue && typeof baselineValue === 'object' || candidateValue && typeof candidateValue === 'object') {
      return rowsFromObjects(baselineValue, candidateValue, [], suffix).map(row => ({
        ...row,
        label: `${labelMap.get(key) || key} · ${row.label}`,
      }))
    }
    const baselineText = formatMetricValue(baselineValue, suffix)
    const candidateText = formatMetricValue(candidateValue, suffix)
    return [{
      label: labelMap.get(key) || key,
      baseline: baselineText,
      candidate: candidateText,
      conclusion: compareNumbers(baselineValue, candidateValue),
      status: compareStatus(baselineValue, candidateValue),
    }]
  })
}

function scoreAggregationGroups(scores: unknown): MetricGroup[] {
  if (!scores || typeof scores !== 'object') return []
  const aggregation = scores as Record<string, any>
  const baselineScores = extractDimensionScores(aggregation.baseline || {})
  const candidateScores = extractDimensionScores(aggregation.candidate || {})
  const dimensions = [...new Set([...Object.keys(baselineScores), ...Object.keys(candidateScores)])]
  return dimensions.map(dimension => {
    const baseline = baselineScores[dimension] || {}
    const candidate = candidateScores[dimension] || {}
    const rows = rowsFromObjects(baseline, candidate, [], '').filter(row => !['status', 'reason'].includes(row.label)).map(row => ({
      ...row,
      label: row.label,
    }))
    const baselineStatus = baseline.status || 'available'
    const candidateStatus = candidate.status || (Object.keys(candidate).length ? 'available' : 'not_recorded')
    if (baselineStatus !== 'available' || candidateStatus !== 'available') {
      rows.push({
        label: '评分状态',
        baseline: scoreStatusLabel(baselineStatus),
        candidate: scoreStatusLabel(candidateStatus),
        conclusion: candidateStatus === 'available' ? '候选已配置' : '候选未配置或未执行',
        status: 'neutral',
      })
      const baselineReason = baseline.reason || ''
      const candidateReason = candidate.reason || ''
      if (baselineReason || candidateReason) {
        rows.push({
          label: '原因',
          baseline: baselineReason || '—',
          candidate: candidateReason || '—',
          conclusion: '请先完成该评分器配置或执行',
          status: 'neutral',
        })
      }
    }
    return {
      key: `score-${dimension}`,
      title: dimension,
      rows,
    }
  })
}

function scoreStatusLabel(status: string): string {
  return {
    available: '已评分',
    not_configured: '未配置',
    skipped: '已跳过',
    error: '评分错误',
    not_recorded: '未生成',
  }[status] || status
}

function extractDimensionScores(payload: Record<string, any>): Record<string, any> {
  if (payload.scores && typeof payload.scores === 'object') return payload.scores
  return payload
}

function formatMetricValue(value: unknown, suffix = ''): string {
  if (value === undefined || value === null || value === '') return '—'
  if (typeof value === 'number') {
    const formatted = Number.isInteger(value) ? String(value) : value.toFixed(4)
    return suffix ? `${formatted} ${suffix}` : formatted
  }
  if (typeof value === 'object') {
    const objectValue = value as Record<string, unknown>
    const primary = objectValue.pass_at_k ?? objectValue.avg_score ?? objectValue.score ?? objectValue.value
    if (primary !== undefined && typeof primary !== 'object') return formatMetricValue(primary, suffix)
    const compact = Object.entries(objectValue)
      .filter(([, item]) => item === null || typeof item !== 'object')
      .slice(0, 3)
      .map(([key, item]) => `${key}: ${formatMetricValue(item)}`)
      .join('，')
    return compact || '已记录'
  }
  return String(value)
}

function compareNumbers(baseline: unknown, candidate: unknown): string {
  const baselineNumber = Number(baseline)
  const candidateNumber = Number(candidate)
  if (!Number.isFinite(baselineNumber) || !Number.isFinite(candidateNumber)) return '无法比较'
  const delta = candidateNumber - baselineNumber
  return `${delta >= 0 ? '提升' : '下降'} ${Math.abs(delta).toFixed(4)}`
}

function compareStatus(baseline: unknown, candidate: unknown): MetricSummary['status'] {
  const baselineNumber = Number(baseline)
  const candidateNumber = Number(candidate)
  if (!Number.isFinite(baselineNumber) || !Number.isFinite(candidateNumber)) return 'neutral'
  return candidateNumber >= baselineNumber ? 'pass' : 'fail'
}

export interface VerificationState {
  state: 'none' | 'pending' | 'running' | 'completed' | 'failed'
  title: string
  description: string
}

export function getVerificationState(
  verification?: Record<string, any> | null,
  proposal?: Record<string, any> | null,
): VerificationState {
  if (!verification) {
    const status = proposal?.status
    if (status === 'verified' || status === 'approved' || status === 'promoted') {
      return {
        state: 'none',
        title: '验证结果暂不可用',
        description: '当前状态已越过验证阶段，但未找到可用验证记录，请刷新或检查后端数据。',
      }
    }
    return {
      state: 'none',
      title: '尚未执行验证',
      description: '此提案还未启动候选验证，启动后这里会展示基线与候选的对比摘要。',
    }
  }
  const status = verification.status
  if (status === 'completed') {
    const gate = verification.gate_result || verification.comparison_result?.gate
    return {
      state: 'completed',
      title: gate?.passed ? '验证通过' : '验证完成但门禁未通过',
      description: gate?.passed
        ? '基线与候选验证已完成，门禁检查全部通过。'
        : (gate?.checks || []).filter((item: Record<string, any>) => !item.passed)
            .map((item: Record<string, any>) => item.name)
            .join('、') || '门禁结果未通过，需重新验证或停止提案。',
    }
  }
  if (status === 'running') {
    return { state: 'running', title: '验证运行中', description: '候选验证正在执行，完成后会自动刷新结果。' }
  }
  if (status === 'pending') {
    return { state: 'pending', title: '验证已排队', description: '验证任务已创建，等待运行环境处理。' }
  }
  return {
    state: 'failed',
    title: '验证失败',
    description: verification.comparison_result?.error || '候选验证未成功完成，请检查运行记录后重试。',
  }
}

export function getAuditState(
  records: Array<Record<string, any>>,
  proposal?: Record<string, any> | null,
): { state: 'empty' | 'pending' | 'available'; title: string; description: string } {
  if (records.length) {
    return { state: 'available', title: '已有审批记录', description: '以下记录来自人工审批或系统审批动作。' }
  }
  const status = proposal?.status
  if (status === 'approved' || status === 'promoted' || status === 'rejected') {
    return {
      state: 'empty',
      title: '审批记录缺失',
      description: '当前状态应存在审批记录，但未查询到，请刷新或检查审批审计数据。',
    }
  }
  if (status === 'verified') {
    return {
      state: 'pending',
      title: '等待审批',
      description: '验证已完成，正在等待管理员批准或拒绝。',
    }
  }
  return {
    state: 'empty',
    title: '尚未进入审批阶段',
    description: '提案需先通过验证，之后才会生成批准、拒绝或评论记录。',
  }
}

export interface ActionStates {
  canVerify: boolean
  canApprove: boolean
  canReject: boolean
  canPromote: boolean
  canStop: boolean
  verifyDisabledReason: string
  approveDisabledReason: string
  promoteDisabledReason: string
  stopDisabledReason: string
}

export function getActionStates(
  proposal?: Record<string, any> | null,
  verification?: Record<string, any> | null,
): ActionStates {
  if (!proposal) {
    return {
      canVerify: false,
      canApprove: false,
      canReject: false,
      canPromote: false,
      canStop: false,
      verifyDisabledReason: '提案尚未加载',
      approveDisabledReason: '提案尚未加载',
      promoteDisabledReason: '提案尚未加载',
      stopDisabledReason: '提案尚未加载',
    }
  }

  const forbidden = Boolean(proposal.forbidden_target)
  const status = proposal.status
  const gate = verification?.gate_result || verification?.comparison_result?.gate
  const verificationOk = verification?.status === 'completed'
  const gatePassed = gate?.passed === true
  const cleaned = verification?.cleanup_status === 'cleaned'

  const canVerify = ['draft', 'pending_verify'].includes(status) && !forbidden
  const canApprove = status === 'verified' && !forbidden && verificationOk && gatePassed
  const canReject = status === 'verified' && !forbidden
  const canPromote =
    status === 'approved' && verificationOk && cleaned && gatePassed && !forbidden
  const canStop = !['promoted', 'stopped', 'rejected', 'rollback'].includes(status)

  let verifyDisabledReason = ''
  if (forbidden) verifyDisabledReason = '目标在禁止修改列表中，不能启动验证。'
  else if (!['draft', 'pending_verify'].includes(status)) verifyDisabledReason = '仅草稿或待验证提案可启动验证。'

  let approveDisabledReason = ''
  if (status !== 'verified') approveDisabledReason = '仅验证通过后的提案可批准。'
  else if (gatePassed === false) approveDisabledReason = '验证门禁未通过，不能批准。'
  else if (!verificationOk) approveDisabledReason = '未找到已完成验证记录。'
  else if (forbidden) approveDisabledReason = '目标在禁止修改列表中，不能批准。'

  let promoteDisabledReason = ''
  if (status !== 'approved') promoteDisabledReason = '提案需先被批准。'
  else if (!verificationOk) promoteDisabledReason = '未找到已完成验证记录。'
  else if (!gatePassed) promoteDisabledReason = '验证门禁未通过，不能发布。'
  else if (!cleaned) promoteDisabledReason = '候选验证沙箱尚未清理完成。'
  else if (proposal.content_diff_status === 'legacy_incomplete') promoteDisabledReason = '历史 diff 不完整，请重新生成候选内容。'
  else if (forbidden) promoteDisabledReason = '目标在禁止修改列表中，不能发布。'

  let stopDisabledReason = ''
  if (['promoted', 'stopped', 'rejected', 'rollback'].includes(status)) {
    stopDisabledReason = '当前终态提案不能执行停止操作。'
  }

  return {
    canVerify,
    canApprove,
    canReject,
    canPromote,
    canStop,
    verifyDisabledReason,
    approveDisabledReason,
    promoteDisabledReason,
    stopDisabledReason,
  }
}

export function isReleaseReady(
  proposal?: Record<string, any> | null,
  verification?: Record<string, any> | null,
): boolean {
  const actions = getActionStates(proposal, verification)
  return actions.canPromote
}

export function releaseBlockReason(proposal?: Record<string, any> | null): string {
  if (!proposal) return '提案尚未加载。'
  if (proposal.forbidden_target) return '目标在禁止修改列表中。'
  if (proposal.status === 'verified') return '等待管理员审批。'
  if (proposal.status === 'pending_verify' || proposal.status === 'verifying') return '候选验证尚未完成。'
  if (proposal.status === 'approved') return '发布门禁或验证记录检查未完成。'
  return '提案当前不处于可发布阶段。'
}
