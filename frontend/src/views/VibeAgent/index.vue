<template>
  <div class="vibe-workbench">
    <aside class="session-rail">
      <div class="rail-head">
        <div>
          <h2>研究会话</h2>
          <p class="rail-meta">
            <span :class="['status-pill', health.available ? 'ok' : 'warn']">{{ healthText }}</span>
            <span v-if="capabilities.error" class="rail-note">{{ capabilities.error }}</span>
          </p>
        </div>
        <el-button :icon="Plus" circle type="primary" @click="createSession" />
      </div>

      <div class="capability-strip">
        <span>{{ capabilities.tool_count }} tools</span>
        <span>{{ capabilities.skill_count }} skills</span>
        <span>{{ capabilities.swarm_count }} Swarm</span>
      </div>

      <el-scrollbar class="session-scroll">
        <button
          v-for="session in sessions"
          :key="session.session_id"
          :class="['session-row', session.session_id === activeSessionId ? 'active' : '']"
          @click="selectSession(session.session_id)"
        >
          <div class="session-row-top">
            <span class="session-title">{{ session.title }}</span>
            <span class="session-time">{{ formatTime(session.updated_at) }}</span>
          </div>
          <div class="session-row-bottom">
            <span>{{ session.status }}</span>
            <span>{{ session.session_id }}</span>
          </div>
        </button>
      </el-scrollbar>
    </aside>

    <main class="workbench">
      <header class="workbench-head">
        <div class="head-copy">
          <h1>自然语言研究</h1>
          <p>{{ activeSession?.title || '从输入框进入 Vibe 风格的金融研究 Agent' }}</p>
        </div>
        <div class="head-actions">
          <el-button :icon="Refresh" @click="reconnectStream" :disabled="!activeSessionId">重连</el-button>
          <el-button :icon="List" @click="router.push('/tasks?tab=running')">任务中心</el-button>
          <el-button
            v-if="activeTask && canCancel(activeTask.status)"
            type="danger"
            :icon="Close"
            @click="cancelTask"
          >
            取消
          </el-button>
          <el-button
            v-if="activeTask && activeTask.status === 'failed'"
            type="warning"
            :icon="Refresh"
            @click="retryTask"
          >
            重试
          </el-button>
        </div>
      </header>

      <section class="status-band">
        <div>
          <span class="band-label">连接</span>
          <strong>{{ streamStateLabel }}</strong>
        </div>
        <div>
          <span class="band-label">任务</span>
          <strong>{{ activeTask?.status || 'idle' }}</strong>
        </div>
        <div>
          <span class="band-label">游标</span>
          <strong>{{ lastSequence || 0 }}</strong>
        </div>
        <div v-if="activeTask?.error_message" class="band-error">
          {{ activeTask.error_message }}
        </div>
      </section>

      <section class="workbench-grid">
        <section class="transcript-pane">
          <el-scrollbar ref="chatScroll" class="transcript-scroll">
            <div v-if="messages.length === 0 && events.length === 0" class="empty-state">
              <h2>输入研究问题</h2>
              <p>例如：分析英伟达最近一个季度财报、估值和关键风险，并给出证据链。</p>
            </div>

            <div v-for="message in messages" :key="message.message_id" :class="['message-row', message.role]">
              <div class="message-bubble">
                <div class="message-role">{{ message.role === 'user' ? '你' : 'Agent' }}</div>
                <div class="message-content">{{ message.content }}</div>
              </div>
            </div>

          </el-scrollbar>

          <form class="composer" @submit.prevent="sendMessage">
            <el-input
              v-model="prompt"
              type="textarea"
              :autosize="{ minRows: 2, maxRows: 6 }"
              resize="none"
              placeholder="输入你的金融研究问题..."
              :disabled="sending || !activeSessionId"
            />
            <el-button
              type="primary"
              :icon="Promotion"
              native-type="submit"
              :loading="sending"
              :disabled="!prompt.trim() || !activeSessionId"
            >
              发送
            </el-button>
          </form>
        </section>

        <aside class="trace-pane">
          <div class="trace-head">
            <h3>运行轨迹</h3>
            <p>工具调用、证据、ReAct、Swarm 和失败原因会按顺序保留。</p>
          </div>

          <div class="trace-sections">
            <section class="trace-section">
              <div class="trace-section-head">
                <strong>运行轨迹</strong>
                <span>{{ workbenchSteps.length }}</span>
              </div>
              <div v-if="workbenchSteps.length === 0" class="trace-empty">暂无内容</div>
              <div v-else class="trace-items">
                <article
                  v-for="step in workbenchSteps"
                  :key="step.key"
                  :class="['trace-item', `step-${step.status}`]"
                >
                  <div class="trace-item-head">
                    <span class="trace-step-title"><i aria-hidden="true"></i>{{ step.title }}</span>
                    <span>{{ step.statusText }}</span>
                  </div>
                  <div class="trace-item-meta">
                    <span class="trace-action">{{ step.action }}</span>
                    <span v-if="stepElapsedText(step)">{{ stepElapsedText(step) }}</span>
                    <span v-if="step.sequence">#{{ step.sequence }}</span>
                  </div>
                </article>
              </div>
            </section>
          </div>
        </aside>
      </section>
    </main>
  </div>
</template>

<script setup lang="ts">
import { computed, nextTick, onMounted, onUnmounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import { Close, List, Plus, Promotion, Refresh } from '@element-plus/icons-vue'
import { vibeAgentApi,
  type VibeEvent,
  type VibeMessage,
  type VibeSession,
  type VibeTask
} from '@/api/vibeAgent'
import { streamVibeEvents } from '@/api/vibeAgentStream'
import { formatDateTime } from '@/utils/datetime'
import {
  buildWorkbenchSteps,
  stepElapsedText
} from './workbench'

const router = useRouter()
const route = useRoute()

const sessions = ref<VibeSession[]>([])
const activeSessionId = ref('')
const messages = ref<VibeMessage[]>([])
const events = ref<VibeEvent[]>([])
const prompt = ref('')
const sending = ref(false)
const activeTask = ref<VibeTask | null>(null)
const health = ref({ available: false, status: 'unknown', diagnostics: {} as Record<string, any> })
const capabilities = ref({ tool_count: 0, skill_count: 0, swarm_count: 0, error: '' })
const streamState = ref<'idle' | 'connected' | 'disconnected' | 'reconnecting'>('idle')
const streamError = ref('')
const chatScroll = ref()
let controller: AbortController | null = null
let reconnectTimer: number | null = null

const activeSession = computed(() => sessions.value.find(item => item.session_id === activeSessionId.value))
const healthText = computed(() => health.value.available ? 'Agent 就绪' : 'Agent 不可用')
const streamStateLabel = computed(() => {
  if (streamState.value === 'connected') return '已连接'
  if (streamState.value === 'reconnecting') return '重连中'
  if (streamState.value === 'disconnected') return streamError.value || '连接已断开'
  return '未连接'
})
const lastSequence = computed(() => Math.max(0, ...events.value.map(event => Number(event.sequence || 0))))
const workbenchSteps = computed(() => buildWorkbenchSteps(events.value))

const loadHealth = async () => {
  try {
    const res = await vibeAgentApi.health()
    health.value = (res as any).data || { available: false, status: 'unknown' }
    const diagnostics = health.value.diagnostics || {}
    capabilities.value = {
      tool_count: Number(diagnostics.tool_count || 0),
      skill_count: Number(diagnostics.skill_count || 0),
      swarm_count: Array.isArray(diagnostics.swarm_presets) ? diagnostics.swarm_presets.length : 0,
      error: diagnostics.error || diagnostics.tools_error || ''
    }
  } catch {
    health.value = { available: false, status: 'unavailable', diagnostics: {} }
    capabilities.value.error = '能力诊断不可用'
  }
}

const loadSessions = async () => {
  const res = await vibeAgentApi.listSessions()
  sessions.value = ((res as any).data || []) as VibeSession[]
  const routeSessionId = typeof route.query.session_id === 'string' ? route.query.session_id : ''
  if (!activeSessionId.value && routeSessionId) {
    await selectSession(routeSessionId)
    return
  }
  if (!activeSessionId.value && sessions.value.length > 0) {
    await selectSession(sessions.value[0].session_id)
  }
}

const createSession = async () => {
  const res = await vibeAgentApi.createSession({ title: '新的研究会话' })
  const session = (res as any).data as VibeSession
  sessions.value.unshift(session)
  await selectSession(session.session_id)
}

const loadSessionState = async (sessionId: string) => {
  const [messagesRes, eventsRes] = await Promise.all([
    vibeAgentApi.listMessages(sessionId),
    vibeAgentApi.replayEvents(sessionId, 0)
  ])
  messages.value = ((messagesRes as any).data || []) as VibeMessage[]
  events.value = ((eventsRes as any).data || []) as VibeEvent[]
  activeTask.value = null
  await nextTick(scrollToBottom)
}

const selectSession = async (sessionId: string) => {
  if (!sessionId || sessionId === activeSessionId.value) return
  activeSessionId.value = sessionId
  await router.replace({ path: '/research-agent', query: { ...route.query, session_id: sessionId } })
  await loadSessionState(sessionId)
  reconnectStream()
}

const reconnectStream = () => {
  if (!activeSessionId.value) return
  controller?.abort()
  controller = new AbortController()
  streamState.value = 'reconnecting'
  streamError.value = ''
  const after = lastSequence.value

  streamVibeEvents(
    activeSessionId.value,
    after,
    {
      onEvent: handleEvent,
      onConnected: () => {
        streamState.value = 'connected'
      },
      onError: (error) => {
        streamState.value = 'disconnected'
        streamError.value = error.message
        scheduleReconnect()
      },
      onClosed: () => {
        if (streamState.value === 'connected') streamState.value = 'disconnected'
        scheduleReconnect()
      }
    },
    controller.signal
  ).catch((error) => {
    if (error.name !== 'AbortError') {
      streamState.value = 'disconnected'
      streamError.value = error.message || '事件流已断开'
      ElMessage.warning(streamError.value)
      scheduleReconnect()
    }
  })
}

const scheduleReconnect = () => {
  if (reconnectTimer) window.clearTimeout(reconnectTimer)
  reconnectTimer = window.setTimeout(() => {
    if (activeTask.value && ['queued', 'processing', 'pending', 'running'].includes(activeTask.value.status)) {
      reconnectStream()
    }
  }, 2500)
}

const handleEvent = (event: VibeEvent) => {
  if (event.sequence && events.value.some(item => item.sequence === event.sequence)) return
  events.value.push(event)
  if (event.event_type === 'message_created' && event.payload?.message?.role === 'assistant') {
    const message = event.payload.message as VibeMessage
    if (message.message_id && !messages.value.some(item => item.message_id === message.message_id)) {
      messages.value.push(message)
    }
  }
  if (event.event_type === 'task_status' && event.payload?.status) {
    activeTask.value = { ...(activeTask.value || {} as VibeTask), status: event.payload.status }
    if (event.payload.status === 'failed') {
      streamState.value = 'disconnected'
      streamError.value = event.payload.error || '任务失败'
    }
  }
  if (event.event_type === 'error' && event.payload?.error) {
    streamError.value = event.payload.error
    scheduleReconnect()
  }
  nextTick(scrollToBottom)
}

const sendMessage = async () => {
  if (!prompt.value.trim() || !activeSessionId.value) return
  sending.value = true
  try {
    const content = prompt.value.trim()
    prompt.value = ''
    messages.value.push({
      message_id: `local_${Date.now()}`,
      role: 'user',
      content,
      created_at: new Date().toISOString()
    })
    const res = await vibeAgentApi.sendMessage(activeSessionId.value, {
      content,
      idempotency_key: `web_${Date.now()}_${Math.random().toString(36).slice(2)}`
    })
    activeTask.value = (res as any).data as VibeTask
    streamState.value = 'reconnecting'
    await loadSessions()
    await nextTick(scrollToBottom)
    reconnectStream()
  } catch (error: any) {
    ElMessage.error(error?.message || '发送失败')
  } finally {
    sending.value = false
  }
}

const cancelTask = async () => {
  if (!activeTask.value) return
  await vibeAgentApi.cancelTask(activeTask.value.task_id)
  activeTask.value.status = 'cancelled'
  streamState.value = 'disconnected'
  ElMessage.success('已发送取消请求')
}

const retryTask = async () => {
  if (!activeTask.value) return
  prompt.value = activeTask.value.prompt
  await sendMessage()
}

const canCancel = (status: string) => ['queued', 'processing', 'pending', 'running'].includes(status)
const formatTime = (value: string) => (value ? formatDateTime(value) : '-')
const scrollToBottom = () => {
  const wrap = chatScroll.value?.wrapRef
  if (wrap) wrap.scrollTop = wrap.scrollHeight
}

const openSessionFromRoute = async () => {
  const sessionId = typeof route.query.session_id === 'string' ? route.query.session_id : ''
  if (sessionId) {
    activeSessionId.value = sessionId
    await loadSessionState(sessionId)
    reconnectStream()
  }
}

watch(
  () => route.query.session_id,
  async (value, oldValue) => {
    if (typeof value === 'string' && value && value !== oldValue) {
      await selectSession(value)
    }
  }
)

onMounted(async () => {
  await loadHealth()
  await loadSessions()
  await openSessionFromRoute()
  if (!activeSessionId.value && sessions.value.length === 0) {
    await createSession()
  }
  if (activeSessionId.value && streamState.value === 'idle') {
    reconnectStream()
  }
})

onUnmounted(() => {
  controller?.abort()
  if (reconnectTimer) window.clearTimeout(reconnectTimer)
})
</script>

<style scoped lang="scss">
.vibe-workbench {
  display: grid;
  grid-template-columns: 282px minmax(0, 1fr);
  height: calc(100vh - 96px);
  min-height: 720px;
  background: var(--el-bg-color-page);
}

.session-rail {
  border-right: 1px solid var(--el-border-color-light);
  padding: 16px;
  overflow: hidden;
  background: var(--el-bg-color);
}

.rail-head,
.workbench-head,
.status-band,
.trace-section-head,
.trace-item-head,
.session-row-top,
.session-row-bottom {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 10px;
}

.rail-head h2,
.workbench-head h1,
.trace-head h3,
.trace-item pre,
.session-row span,
.session-title,
.message-content,
.band-error {
  overflow-wrap: anywhere;
}

.rail-head h2 {
  margin: 0;
  font-size: 16px;
}

.rail-meta {
  margin: 6px 0 0;
  display: flex;
  flex-direction: column;
  gap: 4px;
  font-size: 12px;
}

.status-pill {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  width: fit-content;
  padding: 2px 8px;
  border-radius: 999px;
  font-size: 12px;
  background: var(--el-fill-color-light);
}

.status-pill.ok {
  color: var(--el-color-success);
}

.status-pill.warn {
  color: var(--el-color-warning);
}

.rail-note {
  color: var(--el-text-color-secondary);
}

.capability-strip {
  margin-top: 14px;
  display: flex;
  gap: 8px;
  flex-wrap: wrap;
  color: var(--el-text-color-secondary);
  font-size: 12px;
}

.capability-strip span {
  padding: 4px 8px;
  border-radius: 999px;
  background: var(--el-fill-color-lighter);
}

.session-scroll {
  height: calc(100% - 96px);
  margin-top: 14px;
}

.session-row {
  width: 100%;
  margin-bottom: 8px;
  padding: 12px;
  border: 1px solid var(--el-border-color-lighter);
  border-radius: 8px;
  background: transparent;
  color: var(--el-text-color-primary);
  text-align: left;
  cursor: pointer;
}

.session-row.active,
.session-row:hover {
  border-color: var(--el-color-primary-light-3);
  background: var(--el-color-primary-light-9);
}

.session-title {
  font-weight: 600;
}

.session-time {
  color: var(--el-text-color-secondary);
  font-size: 12px;
}

.session-row-bottom {
  margin-top: 6px;
  color: var(--el-text-color-secondary);
  font-size: 12px;
}

.workbench {
  min-width: 0;
  min-height: 0;
  display: flex;
  flex-direction: column;
  padding: 18px 20px;
  overflow: hidden;
}

.workbench-head {
  padding-bottom: 12px;
  border-bottom: 1px solid var(--el-border-color-light);
}

.workbench-head h1 {
  margin: 0;
  font-size: 22px;
}

.workbench-head p {
  margin: 6px 0 0;
  color: var(--el-text-color-regular);
}

.head-actions {
  display: flex;
  gap: 8px;
  flex-wrap: wrap;
  justify-content: flex-end;
}

.status-band {
  margin-top: 14px;
  gap: 12px;
  flex-wrap: wrap;
  padding: 12px 14px;
  border: 1px solid var(--el-border-color-lighter);
  border-radius: 8px;
  background: var(--el-fill-color-extra-light);
}

.band-label {
  display: block;
  margin-bottom: 4px;
  color: var(--el-text-color-secondary);
  font-size: 12px;
}

.band-error {
  flex: 1 1 100%;
  color: var(--el-color-danger);
  font-size: 13px;
}

.workbench-grid {
  flex: 1;
  min-height: 0;
  display: grid;
  grid-template-columns: minmax(0, 1fr) 380px;
  grid-template-rows: minmax(0, 1fr);
  gap: 16px;
  padding-top: 16px;
  overflow: hidden;
}

.transcript-pane,
.trace-pane {
  min-height: 0;
  min-width: 0;
  border: 1px solid var(--el-border-color-light);
  border-radius: 8px;
  background: var(--el-bg-color);
}

.transcript-pane {
  display: flex;
  flex-direction: column;
}

.transcript-scroll {
  flex: 1;
  min-height: 0;
  padding: 16px;
}

.empty-state {
  max-width: 520px;
  margin: 14vh auto 0;
  text-align: center;
  color: var(--el-text-color-regular);
}

.empty-state h2 {
  margin: 0 0 10px;
  color: var(--el-text-color-primary);
}

.message-row {
  display: flex;
  margin-bottom: 12px;
}

.message-row.user {
  justify-content: flex-end;
}

.message-bubble {
  max-width: min(760px, 82%);
  padding: 10px 12px;
  border-radius: 8px;
  background: var(--el-fill-color-light);
}

.message-row.user .message-bubble {
  background: var(--el-color-primary);
  color: #fff;
}

.message-role {
  margin-bottom: 6px;
  font-size: 12px;
  opacity: 0.7;
}

.message-content {
  white-space: pre-wrap;
  line-height: 1.65;
}

.composer {
  display: grid;
  grid-template-columns: minmax(0, 1fr) auto;
  gap: 10px;
  padding: 12px;
  border-top: 1px solid var(--el-border-color-light);
  background: var(--el-bg-color);
}

.trace-pane {
  display: flex;
  flex-direction: column;
  padding: 12px;
  overflow: hidden;
}

.trace-head h3 {
  margin: 0;
  font-size: 15px;
}

.trace-head p {
  margin: 6px 0 0;
  color: var(--el-text-color-secondary);
  font-size: 12px;
}

.trace-sections {
  flex: 1;
  min-height: 0;
  max-height: 100%;
  margin-top: 12px;
  overflow-y: auto;
  padding-right: 4px;
}

.trace-section {
  margin-bottom: 14px;
  padding-top: 4px;
}

.trace-section-head {
  margin-bottom: 10px;
  color: var(--el-text-color-regular);
  font-size: 13px;
}

.trace-section-head span {
  color: var(--el-text-color-secondary);
  font-size: 12px;
}

.trace-empty {
  padding: 12px;
  border: 1px dashed var(--el-border-color-lighter);
  border-radius: 8px;
  color: var(--el-text-color-secondary);
  font-size: 12px;
}

.trace-item {
  margin-bottom: 6px;
  padding: 8px 10px;
  border: 1px solid var(--el-border-color-lighter);
  border-radius: 8px;
  background: var(--el-bg-color);
}

.trace-item.step-error,
.trace-item.error {
  border-color: var(--el-color-danger-light-7);
  background: var(--el-color-danger-light-9);
}

.trace-item.step-ok {
  border-color: var(--el-color-success-light-7);
}

.trace-item.step-running {
  border-color: var(--el-color-primary-light-5);
}

.trace-item.evidence {
  border-color: var(--el-color-success-light-7);
  background: var(--el-color-success-light-9);
}

.trace-item-head {
  margin-bottom: 4px;
  font-size: 13px;
  font-weight: 600;
}

.trace-step-title {
  display: inline-flex;
  align-items: center;
  min-width: 0;
  gap: 7px;
}

.trace-step-title i {
  width: 7px;
  height: 7px;
  flex: 0 0 7px;
  border-radius: 50%;
  background: var(--el-color-info);
}

.step-ok .trace-step-title i {
  background: var(--el-color-success);
}

.step-error .trace-step-title i {
  background: var(--el-color-danger);
}

.step-running .trace-step-title i {
  background: var(--el-color-primary);
}

.trace-item-meta {
  display: flex;
  gap: 8px;
  flex-wrap: wrap;
  color: var(--el-text-color-secondary);
  font-size: 12px;
}

.trace-action {
  min-width: 0;
  flex: 1 1 100%;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.compact-section {
  margin-top: 18px;
}

@media (max-width: 1200px) {
  .workbench-grid {
    grid-template-columns: 1fr;
  }
}

@media (max-width: 960px) {
  .vibe-workbench {
    grid-template-columns: 1fr;
    height: auto;
  }

  .session-rail {
    border-right: 0;
    border-bottom: 1px solid var(--el-border-color-light);
  }

  .session-scroll {
    height: 220px;
  }
}
</style>
