import { describe, expect, it, vi } from 'vitest'
import { streamVibeEvents } from '@/api/vibeAgentStream'
import {
  eventLabel,
  eventStatusText,
  buildWorkbenchActivity,
  buildWorkbenchSteps,
  formatActivityElapsed,
  summarizeEventPayload
} from '../workbench'

describe('VibeAgent workbench helpers', () => {
  it('only exposes tool calls and filters internal runtime events', () => {
    const steps = buildWorkbenchSteps([
      { sequence: 1, event_type: 'token', payload: { text: 'hello' } },
      { sequence: 2, event_type: 'worker_status', payload: { status: 'processing' } },
      { sequence: 3, event_type: 'tool_call', payload: { name: 'screen_market', arguments: { market: 'us' } } },
      { sequence: 4, event_type: 'evidence', payload: { title: 'evidence' } }
    ])

    expect(steps).toHaveLength(1)
    expect(steps[0].title).toBe('筛选市场')
    expect(steps[0].action).toBe('us')
  })

  it('renders compact labels and status text for failures and tool calls', () => {
    expect(eventLabel({ event_type: 'tool_call', payload: { name: 'search_symbol' } })).toBe('搜索标的')
    expect(eventStatusText({ event_type: 'tool_call', payload: {} })).toBe('执行中')
    expect(eventStatusText({ event_type: 'tool_call', payload: { phase: 'tool_result', status: 'ok' } })).toBe('完成')
  })

  it('merges tool call and tool result into one compact step', () => {
    const steps = buildWorkbenchSteps([
      {
        sequence: 1,
        event_type: 'tool_call',
        payload: { name: 'screen_market', tool_call_id: 'call-1', action: '获取行情' }
      },
      {
        sequence: 2,
        event_type: 'tool_call',
        payload: {
          phase: 'tool_result',
          name: 'screen_market',
          tool_call_id: 'call-1',
          preview: '获取完成',
          elapsed_ms: 842
        }
      },
      { sequence: 3, event_type: 'token', payload: { text: '不应展示' } }
    ])

    expect(steps).toHaveLength(1)
    expect(steps[0].title).toBe('筛选市场')
    expect(steps[0].status).toBe('ok')
    expect(steps[0].action).toBe('获取完成')
    expect(steps[0].elapsedMs).toBe(842)
  })

  it('coalesces consecutive calls and keeps one activity per task', () => {
    const activity = buildWorkbenchActivity('task-1', [
      { sequence: 1, task_id: 'task-1', created_at: '2026-08-25T00:00:00.000Z', event_type: 'tool_call', payload: { name: 'search_symbol', tool_call_id: 'a', arguments: { query: '伊利股份' } } },
      { sequence: 2, task_id: 'task-1', created_at: '2026-08-25T00:00:00.100Z', event_type: 'tool_call', payload: { phase: 'tool_result', name: 'search_symbol', tool_call_id: 'a', status: 'ok', elapsed_ms: 80 } },
      { sequence: 3, task_id: 'task-1', created_at: '2026-08-25T00:00:00.200Z', event_type: 'tool_call', payload: { name: 'search_symbol', tool_call_id: 'b', arguments: { query: '格力电器' } } },
      { sequence: 4, task_id: 'task-1', created_at: '2026-08-25T00:00:00.300Z', event_type: 'tool_call', payload: { phase: 'tool_result', name: 'search_symbol', tool_call_id: 'b', status: 'ok', elapsed_ms: 90 } },
      { sequence: 5, task_id: 'task-1', created_at: '2026-08-25T00:00:01.000Z', event_type: 'task_status', payload: { status: 'completed' } }
    ], 'completed')

    expect(activity.state).toBe('done')
    expect(activity.steps).toHaveLength(1)
    expect(activity.steps[0].count).toBe(2)
    expect(formatActivityElapsed(activity.startedAt, activity.endedAt)).toBe('1s')
  })

  it('summarizes payloads without dumping the whole trace blob', () => {
    const text = summarizeEventPayload({
      event_type: 'tool_call',
      payload: {
        name: 'screen_market',
        phase: 'tool_call',
        tool_call_id: 'call-1',
        preview: 'result preview',
        large: 'ignored'
      }
    })

    expect(text).toContain('screen_market')
    expect(text).toContain('call-1')
    expect(text).not.toContain('ignored')
  })

  it('replays SSE frames in order and keeps the server cursor payload intact', async () => {
    const chunks = [
      'event: connected\ndata: {"session_id":"sess-1"}\n\n',
      'event: event\ndata: {"sequence":1,"event_type":"tool_call","payload":{"name":"screen_market"}}\n\n',
      'event: event\ndata: {"sequence":2,"event_type":"token","payload":{"text":"完成"}}\n\n'
    ]
    const fetchMock = globalThis.fetch
    const storageMock = {
      getItem: vi.fn(() => null),
      setItem: vi.fn(),
      removeItem: vi.fn(),
      clear: vi.fn(),
      key: vi.fn(),
      length: 0
    } as unknown as Storage
    Object.defineProperty(globalThis, 'localStorage', { value: storageMock, configurable: true })
    globalThis.fetch = (async () => ({
      ok: true,
      body: {
        getReader: () => ({
          read: async () => chunks.length
            ? { value: new TextEncoder().encode(chunks.shift()!), done: false }
            : { value: undefined, done: true }
        })
      }
    })) as typeof fetch

    const received: any[] = []
    let connected = 0
    try {
      await streamVibeEvents('sess-1', 0, {
        onConnected: () => { connected += 1 },
        onEvent: event => received.push(event)
      })
    } finally {
      globalThis.fetch = fetchMock
    }

    expect(connected).toBe(1)
    expect(received.map(event => event.sequence)).toEqual([1, 2])
    expect(received[1].payload.text).toBe('完成')
  })
})
