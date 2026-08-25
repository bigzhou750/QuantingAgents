import { describe, expect, it, vi } from 'vitest'
import { streamVibeEvents } from '@/api/vibeAgentStream'
import {
  eventLabel,
  eventStatusText,
  buildWorkbenchSteps,
  groupWorkbenchEvents,
  summarizeEventPayload
} from '../workbench'

describe('VibeAgent workbench helpers', () => {
  it('groups trace events into the expected workbench panels', () => {
    const groups = groupWorkbenchEvents([
      { sequence: 1, event_type: 'token', payload: { text: 'hello' } },
      { sequence: 2, event_type: 'tool_call', payload: { name: 'screen_market' } },
      { sequence: 3, event_type: 'evidence', payload: { title: 'evidence' } },
      { sequence: 4, event_type: 'swarm_status', payload: { agent: 'researcher' } },
      { sequence: 5, event_type: 'task_status', payload: { status: 'failed', error: 'boom' } }
    ])

    expect(groups.map(group => group.label)).toEqual([
      '运行轨迹',
      '工具调用',
      '证据与 ReAct',
      'Swarm'
    ])
    expect(groups[0].events.map(event => event.event_type)).toEqual(['token', 'task_status'])
    expect(groups[1].events[0].payload?.name).toBe('screen_market')
    expect(groups[2].events[0].event_type).toBe('evidence')
    expect(groups[3].events[0].payload?.agent).toBe('researcher')
  })

  it('renders compact labels and status text for failures and tool calls', () => {
    expect(eventLabel({ event_type: 'tool_call' })).toBe('工具轨迹')
    expect(eventLabel({ event_type: 'react_summary' })).toBe('ReAct 摘要')
    expect(eventStatusText({ event_type: 'tool_call', payload: {} })).toBe('调用中')
    expect(eventStatusText({ event_type: 'task_status', payload: { status: 'failed', error: 'boom' } })).toBe('失败')
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
    expect(steps[0].title).toBe('screen_market')
    expect(steps[0].status).toBe('ok')
    expect(steps[0].action).toBe('获取完成')
    expect(steps[0].elapsedMs).toBe(842)
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
