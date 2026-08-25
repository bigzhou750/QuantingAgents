import type { VibeEvent } from '@/api/vibeAgent'

export interface WorkbenchStep {
  key: string
  title: string
  action: string
  status: 'running' | 'ok' | 'error'
  statusText: string
  elapsedMs?: number
  sequence?: number
  count?: number
  event: VibeEvent
}

export interface WorkbenchActivity {
  taskId: string
  steps: WorkbenchStep[]
  state: 'running' | 'done' | 'failed' | 'cancelled'
  startedAt?: number
  endedAt?: number
}

const INTERNAL_EVENTS = new Set([
  'token',
  'session_created',
  'message_created',
  'task_queued',
  'worker_status',
  'task_status',
  'error',
  'evidence',
  'react_summary',
  'swarm_status'
])

const TOOL_LABELS: Record<string, string> = {
  screen_market: '筛选市场',
  get_market_data: '获取市场数据',
  search_symbol: '搜索标的',
  technical_indicators: '技术指标',
  news_search: '搜索新闻',
  fundamentals: '获取基本面',
  pattern: '识别形态',
  swarm: '协同分析'
}

export function eventLabel(event: VibeEvent): string {
  const type = event.event_type || ''
  if (type === 'tool_call') {
    return TOOL_LABELS[String(event.payload?.name || event.payload?.tool || '')] || '执行工具'
  }
  return type || '事件'
}

export function eventStatusText(event: VibeEvent): string {
  const payload = event.payload || {}
  if (payload.error || payload.status === 'error' || payload.status === 'failed') return '失败'
  if (payload.phase === 'tool_result' || payload.status === 'ok' || payload.status === 'completed') return '完成'
  return '执行中'
}

function toolCallKey(event: VibeEvent): string {
  const payload = event.payload || {}
  return String(payload.tool_call_id || payload.call_id || payload.id || '')
}

function toolName(event: VibeEvent): string {
  const payload = event.payload || {}
  return String(payload.name || payload.tool || '')
}

function elapsedMs(event: VibeEvent): number | undefined {
  const value = event.payload?.elapsed_ms
  return typeof value === 'number' && Number.isFinite(value) ? Math.max(0, value) : undefined
}

function stringifyValue(value: unknown): string {
  if (typeof value === 'string') return value
  try {
    return JSON.stringify(value)
  } catch {
    return String(value)
  }
}

function compact(value: string, max = 72): string {
  const text = value.replace(/\s+/g, ' ').trim()
  return text.length > max ? `${text.slice(0, max - 1)}…` : text
}

function argumentSummary(event: VibeEvent): string {
  const payload = event.payload || {}
  const args = (payload.arguments || payload.args || {}) as Record<string, unknown>
  const name = toolName(event)
  if (name === 'search_symbol') {
    return String(args.query || args.q || args.keyword || '').trim()
  }
  if (name === 'get_market_data') {
    const codes = args.codes || args.symbols || args.symbol
    return codes ? compact(stringifyValue(codes), 86) : ''
  }
  if (name === 'screen_market') {
    const market = args.market || args.region
    return market ? String(market) : ''
  }
  const preferred = ['query', 'symbol', 'symbols', 'codes', 'factor', 'action', 'source', 'market']
  for (const key of preferred) {
    if (args[key] !== undefined && args[key] !== null && args[key] !== '') {
      return compact(stringifyValue(args[key]))
    }
  }
  return compact(String(payload.action || payload.preview || ''))
}

function toolAction(event: VibeEvent): string {
  const payload = event.payload || {}
  const preview = payload.preview
  if (payload.phase === 'tool_result' && preview && payload.error) return compact(String(payload.error))
  return argumentSummary(event) || (preview ? compact(String(preview)) : '')
}

export function stepElapsedText(step: WorkbenchStep): string {
  if (step.elapsedMs === undefined) return ''
  if (step.elapsedMs < 100) return '<0.1s'
  if (step.elapsedMs < 1000) return `${(step.elapsedMs / 1000).toFixed(1)}s`
  const seconds = step.elapsedMs / 1000
  return seconds < 60 ? `${seconds.toFixed(1)}s` : `${Math.floor(seconds / 60)}m ${Math.round(seconds % 60)}s`
}

export function formatActivityElapsed(startedAt?: number, endedAt?: number): string {
  if (!startedAt || !endedAt) return ''
  const seconds = Math.max(0, Math.floor((endedAt - startedAt) / 1000))
  if (seconds < 60) return `${seconds}s`
  return `${Math.floor(seconds / 60)}m ${seconds % 60}s`
}

export function summarizeEventPayload(event: VibeEvent): string {
  const payload = event.payload || {}
  const compactPayload: Record<string, unknown> = {}
  for (const key of ['tool', 'name', 'phase', 'status', 'tool_call_id', 'call_id', 'preview', 'error']) {
    if (payload[key] !== undefined && payload[key] !== null && payload[key] !== '') compactPayload[key] = payload[key]
  }
  return JSON.stringify(Object.keys(compactPayload).length ? compactPayload : payload, null, 2)
}

function mergeResult(steps: WorkbenchStep[], indexes: Map<string, number>, event: VibeEvent): boolean {
  const key = toolCallKey(event)
  const index = key ? indexes.get(key) : undefined
  if (index === undefined) return false
  const previous = steps[index]
  const failed = Boolean(event.payload?.error) || event.payload?.status === 'error'
  steps[index] = {
    ...previous,
    action: toolAction(event) || previous.action,
    status: failed ? 'error' : 'ok',
    statusText: failed ? '失败' : '完成',
    elapsedMs: elapsedMs(event) ?? previous.elapsedMs,
    event
  }
  return true
}

function coalesceSteps(steps: WorkbenchStep[]): WorkbenchStep[] {
  const result: WorkbenchStep[] = []
  for (const step of steps) {
    const previous = result[result.length - 1]
    if (previous && previous.status === 'ok' && step.status === 'ok' && previous.title === step.title) {
      const actions = [previous.action, step.action].filter(Boolean)
      previous.count = (previous.count || 1) + 1
      previous.action = actions.slice(0, 3).join(', ') + (actions.length > 3 ? ` +${actions.length - 3}` : '')
      previous.elapsedMs = (previous.elapsedMs || 0) + (step.elapsedMs || 0)
      previous.event = step.event
      continue
    }
    result.push({ ...step, count: step.count || 1 })
  }
  return result
}

export function buildWorkbenchSteps(events: VibeEvent[]): WorkbenchStep[] {
  const steps: WorkbenchStep[] = []
  const indexes = new Map<string, number>()

  for (const event of events) {
    if (event.event_type !== 'tool_call') continue
    const payload = event.payload || {}
    const isResult = payload.phase === 'tool_result' || payload.result !== undefined || payload.error
    if (isResult) {
      if (mergeResult(steps, indexes, event)) continue
    }
    const failed = Boolean(payload.error) || payload.status === 'error'
    const step: WorkbenchStep = {
      key: toolCallKey(event) || `tool-${event.sequence || steps.length}`,
      title: eventLabel(event),
      action: toolAction(event),
      status: isResult ? (failed ? 'error' : 'ok') : 'running',
      statusText: isResult ? (failed ? '失败' : '完成') : '执行中',
      elapsedMs: elapsedMs(event),
      sequence: event.sequence,
      event
    }
    steps.push(step)
    const key = toolCallKey(event)
    if (key) indexes.set(key, steps.length - 1)
  }
  return coalesceSteps(steps)
}

export function buildWorkbenchActivity(taskId: string, events: VibeEvent[], taskStatus?: string): WorkbenchActivity {
  const relevant = events.filter(event => event.task_id === taskId)
  const toolEvents = relevant.filter(event => event.event_type === 'tool_call')
  const timestamps = relevant
    .map(event => event.created_at ? Date.parse(event.created_at) : 0)
    .filter(value => value > 0)
  const statusEvent = [...relevant].reverse().find(event => event.event_type === 'task_status')
  const status = String(taskStatus || statusEvent?.payload?.status || '')
  const state = status === 'failed'
    ? 'failed'
    : status === 'cancelled'
      ? 'cancelled'
      : status === 'completed'
        ? 'done'
        : 'running'
  return {
    taskId,
    steps: buildWorkbenchSteps(toolEvents),
    state,
    startedAt: timestamps.length ? Math.min(...timestamps) : undefined,
    endedAt: state === 'running' ? undefined : timestamps.length ? Math.max(...timestamps) : undefined
  }
}

export function isInternalEvent(event: VibeEvent): boolean {
  return INTERNAL_EVENTS.has(event.event_type || '')
}
