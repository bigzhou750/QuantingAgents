export interface StreamVibeEvent {
  event_id?: string
  sequence?: number
  event_type?: string
  task_id?: string
  payload?: Record<string, any>
  created_at?: string
}

export interface StreamVibeEventOptions {
  onEvent: (event: StreamVibeEvent) => void
  onConnected?: () => void
  onHeartbeat?: () => void
  onError?: (error: Error) => void
  onClosed?: () => void
}

export class VibeAgentUnauthorizedError extends Error {
  status = 401

  constructor() {
    super('登录已过期，请重新登录')
    this.name = 'VibeAgentUnauthorizedError'
  }
}

export async function streamVibeEvents(
  sessionId: string,
  after: number,
  handlers: StreamVibeEventOptions,
  signal?: AbortSignal
) {
  const token = localStorage.getItem('auth-token')
  const response = await fetch(`/api/vibe-agent/sessions/${sessionId}/events?after=${after}`, {
    headers: token ? { Authorization: `Bearer ${token}` } : {},
    signal
  })

  if (response.status === 401) {
    localStorage.removeItem('auth-token')
    localStorage.removeItem('refresh-token')
    localStorage.removeItem('user-info')
    if (window.location.pathname !== '/login') {
      window.location.assign('/login')
    }
    throw new VibeAgentUnauthorizedError()
  }

  if (!response.ok || !response.body) {
    throw new Error(`事件流连接失败: ${response.status}`)
  }

  const reader = response.body.getReader()
  const decoder = new TextDecoder()
  let buffer = ''

  try {
    while (true) {
      const { value, done } = await reader.read()
      if (done) break
      buffer += decoder.decode(value, { stream: true })

      let boundary = buffer.indexOf('\n\n')
      while (boundary >= 0) {
        const raw = buffer.slice(0, boundary)
        buffer = buffer.slice(boundary + 2)
        const parsed = parseSseFrame(raw)
        if (parsed.event === 'connected') handlers.onConnected?.()
        if (parsed.event === 'heartbeat') handlers.onHeartbeat?.()
        if (parsed.event === 'event' && parsed.data) handlers.onEvent(parsed.data)
        boundary = buffer.indexOf('\n\n')
      }
    }
  } finally {
    try {
      await reader.cancel()
    } catch {
      // The request may already be aborted or the stream may be closed.
    }
  }

  if (!signal?.aborted) handlers.onClosed?.()
}

export function parseSseFrame(raw: string): { event: string; data?: any } {
  const lines = raw.split('\n')
  const event = lines.find(line => line.startsWith('event:'))?.slice(6).trim() || 'message'
  const dataText = lines
    .filter(line => line.startsWith('data:'))
    .map(line => line.slice(5).trim())
    .join('\n')
  if (!dataText) return { event }
  try {
    return { event, data: JSON.parse(dataText) }
  } catch {
    return { event, data: dataText }
  }
}
