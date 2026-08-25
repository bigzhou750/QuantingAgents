import type { VibeEvent } from '@/api/vibeAgent'

export interface WorkbenchEventGroup {
  label: string
  events: VibeEvent[]
}

export interface WorkbenchStep {
  key: string
  title: string
  action: string
  status: 'running' | 'ok' | 'error' | 'done'
  statusText: string
  elapsedMs?: number
  sequence?: number
  event: VibeEvent
}

export function eventLabel(event: VibeEvent): string {
  const labels: Record<string, string> = {
    session_created: '会话创建',
    message_created: '用户消息',
    task_queued: '任务入队',
    worker_status: 'Worker 状态',
    token: '流式输出',
    tool_call: '工具轨迹',
    evidence: '证据',
    react_summary: 'ReAct 摘要',
    swarm_status: 'Swarm 状态',
    task_status: '任务状态',
    error: '错误'
  }
  return labels[event.event_type || ''] || event.event_type || '事件'
}

export function eventKind(event: VibeEvent): string {
  const type = event.event_type || ''
  if (type === 'tool_call') return 'tool'
  if (type === 'evidence' || type === 'react_summary') return 'evidence'
  if (type === 'swarm_status') return 'swarm'
  if (type === 'token') return 'token'
  if (type === 'task_status' || type === 'error') return 'status'
  return 'general'
}

export function groupWorkbenchEvents(events: VibeEvent[]): WorkbenchEventGroup[] {
  const buckets: Record<string, VibeEvent[]> = {
    trajectory: [],
    tool: [],
    evidence: [],
    swarm: [],
    status: []
  }

  for (const event of events) {
    const kind = eventKind(event)
    if (kind === 'tool') buckets.tool.push(event)
    else if (kind === 'evidence') buckets.evidence.push(event)
    else if (kind === 'swarm') buckets.swarm.push(event)
    else if (kind === 'status') buckets.status.push(event)
    else buckets.trajectory.push(event)
  }

  return [
    { label: '运行轨迹', events: [...buckets.trajectory, ...buckets.status] },
    { label: '工具调用', events: buckets.tool },
    { label: '证据与 ReAct', events: buckets.evidence },
    { label: 'Swarm', events: buckets.swarm }
  ]
}

export function summarizeEventPayload(event: VibeEvent): string {
  const payload = event.payload || {}
  const compact: Record<string, any> = {}
  for (const key of ['tool', 'name', 'phase', 'status', 'tool_call_id', 'call_id', 'message', 'preview', 'error', 'agent', 'role']) {
    const value = payload[key]
    if (value !== undefined && value !== null && value !== '') compact[key] = value
  }
  if (Object.keys(compact).length > 0) return JSON.stringify(compact, null, 2)
  return JSON.stringify(payload, null, 2)
}

export function eventStatusText(event: VibeEvent): string {
  const payload = event.payload || {}
  if (payload.error) return '失败'
  if (payload.status) return String(payload.status)
  if (event.event_type === 'token') return '生成中'
  if (event.event_type === 'tool_call') return '调用中'
  return '已记录'
}

function toolCallKey(event: VibeEvent): string {
  const payload = event.payload || {}
  return String(payload.tool_call_id || payload.call_id || payload.id || '')
}

function toolName(event: VibeEvent): string {
  const payload = event.payload || {}
  return String(payload.name || payload.tool || '工具调用')
}

function elapsedMs(event: VibeEvent): number | undefined {
  const value = event.payload?.elapsed_ms
  return typeof value === 'number' && Number.isFinite(value) ? value : undefined
}

export function stepElapsedText(step: WorkbenchStep): string {
  if (step.elapsedMs === undefined) return ''
  return step.elapsedMs < 1000
    ? `${Math.round(step.elapsedMs)} ms`
    : `${(step.elapsedMs / 1000).toFixed(1)} s`
}

export function buildWorkbenchSteps(events: VibeEvent[]): WorkbenchStep[] {
  const steps: WorkbenchStep[] = []
  const toolIndexes = new Map<string, number>()

  for (const event of events) {
    const type = event.event_type || ''
    const payload = event.payload || {}
    if (type === 'token' || ['session_created', 'message_created', 'task_queued'].includes(type)) continue

    if (type === 'tool_call') {
      const key = toolCallKey(event)
      const isResult = payload.phase === 'tool_result' || payload.result !== undefined || payload.error
      if (isResult && key && toolIndexes.has(key)) {
        const index = toolIndexes.get(key)!
        const previous = steps[index]
        steps[index] = {
          ...previous,
          action: String(payload.preview || payload.error || previous.action),
          status: payload.error ? 'error' : 'ok',
          statusText: payload.error ? '失败' : '完成',
          elapsedMs: elapsedMs(event) ?? previous.elapsedMs,
          event
        }
        continue
      }
      const step: WorkbenchStep = {
        key: key || `tool-${event.sequence || steps.length}`,
        title: toolName(event),
        action: String(payload.action || payload.preview || '执行工具'),
        status: 'running',
        statusText: '运行中',
        elapsedMs: elapsedMs(event),
        sequence: event.sequence,
        event
      }
      steps.push(step)
      if (key) toolIndexes.set(key, steps.length - 1)
      continue
    }

    if (type === 'task_status' || type === 'error' || type === 'worker_status') {
      const failed = Boolean(payload.error) || payload.status === 'failed'
      steps.push({
        key: `status-${event.sequence || steps.length}`,
        title: eventLabel(event),
        action: String(payload.error || payload.message || payload.status || '状态更新'),
        status: failed ? 'error' : payload.status === 'processing' ? 'running' : 'done',
        statusText: failed ? '失败' : eventStatusText(event),
        elapsedMs: elapsedMs(event),
        sequence: event.sequence,
        event
      })
      continue
    }

    if (['evidence', 'react_summary', 'swarm_status'].includes(type)) {
      steps.push({
        key: `${type}-${event.sequence || steps.length}`,
        title: eventLabel(event),
        action: String(payload.title || payload.summary || payload.message || payload.agent || '已记录'),
        status: 'done',
        statusText: '已记录',
        elapsedMs: elapsedMs(event),
        sequence: event.sequence,
        event
      })
    }
  }
  return steps
}
