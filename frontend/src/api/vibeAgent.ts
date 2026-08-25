import { request, type ApiResponse } from './request'
export { streamVibeEvents, parseSseFrame } from './vibeAgentStream'
export type { StreamVibeEventOptions, StreamVibeEvent } from './vibeAgentStream'

export interface VibeSession {
  session_id: string
  title: string
  status: string
  archived: boolean
  created_at: string
  updated_at: string
}

export interface VibeTask {
  task_id: string
  session_id: string
  status: string
  prompt: string
  progress: number
  error_message?: string
  created_at: string
}

export interface VibeMessage {
  message_id: string
  role: string
  content: string
  task_id?: string
  created_at: string
}

export interface VibeEvent {
  event_id?: string
  sequence?: number
  event_type?: string
  task_id?: string
  payload?: Record<string, any>
  created_at?: string
}


export const vibeAgentApi = {
  health(): Promise<ApiResponse<any>> {
    return request.get('/api/vibe-agent/health')
  },
  capabilities(): Promise<ApiResponse<any>> {
    return request.get('/api/vibe-agent/capabilities')
  },
  listSessions(): Promise<ApiResponse<VibeSession[]>> {
    return request.get('/api/vibe-agent/sessions')
  },
  createSession(payload: { title?: string; metadata?: Record<string, any> }): Promise<ApiResponse<VibeSession>> {
    return request.post('/api/vibe-agent/sessions', payload)
  },
  listMessages(sessionId: string): Promise<ApiResponse<VibeMessage[]>> {
    return request.get(`/api/vibe-agent/sessions/${sessionId}/messages`)
  },
  sendMessage(sessionId: string, payload: { content: string; idempotency_key?: string; metadata?: Record<string, any> }): Promise<ApiResponse<VibeTask>> {
    return request.post(`/api/vibe-agent/sessions/${sessionId}/messages`, payload)
  },
  listTasks(params?: { status?: string; page?: number; page_size?: number }): Promise<ApiResponse<{ tasks: VibeTask[]; total: number }>> {
    return request.get('/api/vibe-agent/tasks', { params })
  },
  cancelTask(taskId: string): Promise<ApiResponse<VibeTask>> {
    return request.post(`/api/vibe-agent/tasks/${taskId}/cancel`, {})
  },
  replayEvents(sessionId: string, after = 0): Promise<ApiResponse<VibeEvent[]>> {
    return request.get(`/api/vibe-agent/sessions/${sessionId}/events/replay`, { params: { after } })
  }
}
