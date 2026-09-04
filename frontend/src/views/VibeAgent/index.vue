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
        <div
          v-for="session in sessions"
          :key="session.session_id"
          :class="['session-row', session.session_id === activeSessionId ? 'active' : '']"
          role="button"
          tabindex="0"
          @click="selectSession(session.session_id)"
          @keydown.enter="selectSession(session.session_id)"
          @keydown.space.prevent="selectSession(session.session_id)"
        >
          <div class="session-row-top">
            <span class="session-title">{{ session.title }}</span>
            <div class="session-row-actions">
              <span class="session-time">{{ formatTime(session.updated_at) }}</span>
              <el-button
                class="session-delete"
                :icon="Delete"
                circle
                text
                size="small"
                title="删除会话"
                aria-label="删除会话"
                :disabled="Boolean(tasksBySession[session.session_id])"
                @click.stop="deleteSession(session)"
              />
            </div>
          </div>
          <div v-if="session.first_prompt" class="session-preview">{{ session.first_prompt }}</div>
        </div>
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

      <section class="transcript-pane">
          <el-scrollbar ref="chatScroll" class="transcript-scroll">
            <div v-if="messages.length === 0 && events.length === 0" class="empty-state">
              <h2>输入研究问题</h2>
              <p>例如：分析英伟达最近一个季度财报、估值和关键风险，并给出证据链。</p>
            </div>

            <div v-for="message in messages" :key="message.message_id" :class="['message-row', message.role]">
              <div
                v-if="message.role === 'assistant' && message.task_id && activityFor(message.task_id).steps.length > 0"
                class="activity-line"
                :class="{ 'activity-running': activityFor(message.task_id).state === 'running' }"
              >
                <button
                  type="button"
                  class="activity-summary"
                  :aria-expanded="isActivityOpen(activityFor(message.task_id))"
                  @click="toggleActivity(activityFor(message.task_id).taskId)"
                >
                  <span class="activity-status-icon" :class="`status-${activityFor(message.task_id).state}`">
                    {{ activityFor(message.task_id).state === 'running' ? '·' : activityFor(message.task_id).state === 'failed' ? '!' : '✓' }}
                  </span>
                  <span class="activity-summary-text">
                    {{ activitySummary(activityFor(message.task_id)) }}
                  </span>
                  <span class="activity-chevron">{{ isActivityOpen(activityFor(message.task_id)) ? '⌄' : '›' }}</span>
                </button>
                <div v-if="isActivityOpen(activityFor(message.task_id))" class="activity-steps">
                  <div v-for="step in activityFor(message.task_id).steps" :key="step.key" class="activity-step">
                    <span class="step-dot" :class="`step-${step.status}`"></span>
                    <span class="step-title">{{ step.title }}<template v-if="step.count && step.count > 1"> ×{{ step.count }}</template></span>
                    <span v-if="step.action" class="step-action">{{ step.action }}</span>
                    <span v-if="stepElapsedText(step)" class="step-elapsed">{{ stepElapsedText(step) }}</span>
                  </div>
                </div>
              </div>
              <div class="message-bubble">
                <div class="message-role">{{ message.role === 'user' ? '你' : 'Agent' }}</div>
                <div class="message-content markdown-body" v-html="renderMarkdown(message.content)"></div>
              </div>
            </div>

            <div
              v-if="activeTask && !messages.some(message => message.role === 'assistant' && message.task_id === activeTask?.task_id)"
              class="activity-line activity-current"
              :class="{ 'activity-running': activityFor(activeTask.task_id).state === 'running' }"
            >
              <button
                type="button"
                class="activity-summary"
                :aria-expanded="isActivityOpen(activityFor(activeTask.task_id))"
                @click="toggleActivity(activeTask.task_id)"
              >
                <span class="activity-status-icon" :class="`status-${activityFor(activeTask.task_id).state}`">
                  {{ activityFor(activeTask.task_id).state === 'running' ? '·' : activityFor(activeTask.task_id).state === 'failed' ? '!' : '✓' }}
                </span>
                <span class="activity-summary-text">{{ activitySummary(activityFor(activeTask.task_id)) }}</span>
                <span class="activity-chevron">{{ isActivityOpen(activityFor(activeTask.task_id)) ? '⌄' : '›' }}</span>
              </button>
              <div v-if="isActivityOpen(activityFor(activeTask.task_id))" class="activity-steps">
                <div v-for="step in activityFor(activeTask.task_id).steps" :key="step.key" class="activity-step">
                  <span class="step-dot" :class="`step-${step.status}`"></span>
                  <span class="step-title">{{ step.title }}<template v-if="step.count && step.count > 1"> ×{{ step.count }}</template></span>
                  <span v-if="step.action" class="step-action">{{ step.action }}</span>
                  <span v-if="stepElapsedText(step)" class="step-elapsed">{{ stepElapsedText(step) }}</span>
                </div>
              </div>
              <div v-if="streamTextFor(activeTask.task_id)" class="streaming-response">
                <div class="markdown-body" v-html="renderMarkdown(streamTextFor(activeTask.task_id))"></div>
              </div>
            </div>
          </el-scrollbar>

          <form class="composer" @submit.prevent="sendMessage">
            <!-- 上下文注入选项 & 模型选择 -->
            <div class="context-options">
              <template v-if="investmentContextEnabled">
                <el-checkbox v-model="useProfileContext">
                  <el-icon><UserFilled /></el-icon>
                  带入投资画像
                </el-checkbox>
                <el-select
                  v-model="selectedStrategyId"
                  placeholder="选择策略（可选）"
                  clearable
                  size="small"
                  style="width: 180px; margin-left: 12px;"
                >
                  <el-option
                    v-for="strategy in availableStrategies"
                    :key="strategy.strategy_id"
                    :label="strategy.name"
                    :value="strategy.strategy_id"
                  />
                </el-select>
              </template>
              <el-select
                v-model="selectedModel"
                placeholder="默认模型"
                clearable
                size="small"
                style="width: 200px; margin-left: auto;"
              >
                <el-option-group
                  v-for="group in availableModels"
                  :key="group.provider"
                  :label="group.provider_name"
                >
                  <el-option
                    v-for="model in group.models"
                    :key="model.name"
                    :label="model.display_name || model.name"
                    :value="model.name"
                  />
                </el-option-group>
              </el-select>
            </div>

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
              :disabled="!prompt.trim() || !activeSessionId || hasRunningTask"
            >
              发送
            </el-button>
            <div v-if="hasRunningTask" class="composer-lock">
              当前有研究任务执行中，请等待完成或先取消任务
            </div>
          </form>
        </section>
    </main>
  </div>
</template>

<script setup lang="ts">
import { computed, nextTick, onMounted, onUnmounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'
import { Close, Delete, List, Plus, Promotion, Refresh, UserFilled } from '@element-plus/icons-vue'
import { marked } from 'marked'
import { vibeAgentApi,
  type VibeEvent,
  type VibeMessage,
  type VibeSession,
  type VibeTask
} from '@/api/vibeAgent'
import { configApi } from '@/api/config'
import { streamVibeEvents, VibeAgentUnauthorizedError } from '@/api/vibeAgentStream'
import { configApi } from '@/api/config'
import { formatDateTime } from '@/utils/datetime'
import {
  buildWorkbenchActivity,
  formatActivityElapsed,
  stepElapsedText
} from './workbench'

const router = useRouter()
const route = useRoute()

const sessions = ref<VibeSession[]>([])
const activeSessionId = ref('')
const messages = ref<VibeMessage[]>([])
const events = ref<VibeEvent[]>([])
const prompt = ref('')

// 个人投资助手上下文注入
const investmentContextEnabled = ref(false)
const useProfileContext = ref(false)
const selectedStrategyId = ref<string | undefined>(undefined)
const availableStrategies = ref<any[]>([])
const sending = ref(false)
// 模型选择
const availableModels = ref<Array<{ provider: string; provider_name: string; models: Array<{ name: string; display_name: string }> }>>([])
const selectedModel = ref<string>('')
const activeTask = ref<VibeTask | null>(null)
const tasksBySession = ref<Record<string, VibeTask>>({})
const health = ref({ available: false, status: 'unknown', diagnostics: {} as Record<string, any> })
const capabilities = ref({ tool_count: 0, skill_count: 0, swarm_count: 0, error: '' })
const streamState = ref<'idle' | 'connected' | 'disconnected' | 'reconnecting'>('idle')
const streamError = ref('')
const authRequired = ref(false)
const chatScroll = ref()
const activityOpen = ref<Record<string, boolean>>({})
let controller: AbortController | null = null
let reconnectTimer: number | null = null
let sessionLoadVersion = 0
let streamGeneration = 0

marked.setOptions({ breaks: true, gfm: true })

const sanitizeMarkdownHtml = (html: string) => html
  .replace(/<\s*(script|style|iframe|object|embed|form|meta|link)\b[^>]*>[\s\S]*?<\s*\/\s*\1\s*>/gi, '')
  .replace(/\s+on[a-z]+\s*=\s*("[^"]*"|'[^']*'|[^\s>]+)/gi, '')
  .replace(/\s+(href|src)\s*=\s*(['"])\s*javascript:[\s\S]*?\2/gi, ' $1="#"')

const renderMarkdown = (content: string) => {
  try {
    return sanitizeMarkdownHtml(String(marked.parse(content || '')))
  } catch {
    return String(content || '').replace(/[&<>"]/g, char => (
      { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[char] || char
    ))
  }
}

const activeSession = computed(() => sessions.value.find(item => item.session_id === activeSessionId.value))
const runningTask = computed(() => (
  Object.values(tasksBySession.value).find(task => canCancel(task.status)) || null
))
const hasRunningTask = computed(() => Boolean(runningTask.value))
const healthText = computed(() => health.value.available ? 'Agent 就绪' : 'Agent 不可用')
const streamStateLabel = computed(() => {
  if (streamState.value === 'connected') return '已连接'
  if (streamState.value === 'reconnecting') return '重连中'
  if (streamState.value === 'disconnected') return streamError.value || '连接已断开'
  return '未连接'
})
const lastSequence = computed(() => Math.max(0, ...events.value.map(event => Number(event.sequence || 0))))

const activityFor = (taskId: string) => buildWorkbenchActivity(
  taskId,
  events.value,
  activeTask.value?.task_id === taskId ? activeTask.value.status : undefined
)

const isActivityOpen = (activity: ReturnType<typeof buildWorkbenchActivity>) => (
  activity.state === 'running' || activityOpen.value[activity.taskId] === true
)

const toggleActivity = (taskId: string) => {
  activityOpen.value[taskId] = !isActivityOpen(activityFor(taskId))
}

const activitySummary = (activity: ReturnType<typeof buildWorkbenchActivity>) => {
  const count = activity.steps.reduce((total, step) => total + (step.count || 1), 0)
  const elapsed = formatActivityElapsed(activity.startedAt, activity.endedAt)
  if (activity.state === 'running') {
    return ['执行中', count ? `${count} 个步骤` : '准备中', elapsed].filter(Boolean).join(' · ')
  }
  if (activity.state === 'failed') return ['失败', `${count} 个步骤`, elapsed].filter(Boolean).join(' · ')
  if (activity.state === 'cancelled') return ['已取消', `${count} 个步骤`, elapsed].filter(Boolean).join(' · ')
  return ['完成', `${count} 个步骤`, elapsed].filter(Boolean).join(' · ')
}

const streamTextFor = (taskId: string) => events.value
  .filter(event => event.task_id === taskId && event.event_type === 'token')
  .map(event => String(event.payload?.text || event.payload?.delta || ''))
  .join('')

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
    return true
  } catch (error: any) {
    health.value = { available: false, status: 'unavailable', diagnostics: {} }
    if (isAuthError(error)) {
      authRequired.value = true
      capabilities.value.error = '登录已过期，请重新登录'
    } else {
      capabilities.value.error = '能力诊断不可用'
    }
    return false
  }
}

const loadSessions = async () => {
  try {
    const res = await vibeAgentApi.listSessions()
    sessions.value = ((res as any).data || []) as VibeSession[]
    await loadRunningTasks()
    const routeSessionId = typeof route.query.session_id === 'string' ? route.query.session_id : ''
    if (!activeSessionId.value && routeSessionId) {
      await selectSession(routeSessionId)
      return
    }
    if (!activeSessionId.value && sessions.value.length > 0) {
      await selectSession(sessions.value[0].session_id)
    }
  } catch (error: any) {
    if (isAuthError(error)) authRequired.value = true
    throw error
  }
}

const loadRunningTasks = async () => {
  const res = await vibeAgentApi.listTasks({ page: 1, page_size: 100 })
  const next: Record<string, VibeTask> = {}
  for (const task of (((res as any).data?.tasks || []) as VibeTask[])) {
    if (canCancel(task.status)) next[task.session_id] = task
  }
  tasksBySession.value = next
}

const createSession = async () => {
  try {
    const { value } = await ElMessageBox.prompt('请输入会话名称', '新建研究会话', {
      confirmButtonText: '创建',
      cancelButtonText: '取消',
      inputValue: '研究会话',
      inputPlaceholder: '例如：格力电器分钟线回测',
      inputValidator: (input: string) => input.trim() ? true : '会话名称不能为空'
    })
    const res = await vibeAgentApi.createSession({ title: value.trim() })
    const session = (res as any).data as VibeSession
    sessions.value.unshift(session)
    await selectSession(session.session_id)
  } catch (error: any) {
    if (error !== 'cancel' && error !== 'close') {
      ElMessage.error(error?.message || '创建会话失败')
    }
  }
}

const deleteSession = async (session: VibeSession) => {
  if (tasksBySession.value[session.session_id]) {
    ElMessage.warning('会话有任务正在执行，完成或取消后才能删除')
    return
  }
  try {
    await ElMessageBox.confirm(
      `确定删除“${session.title}”吗？会话及其历史记录将从列表中隐藏。`,
      '删除会话',
      {
        confirmButtonText: '删除',
        cancelButtonText: '取消',
        type: 'warning'
      }
    )
    await vibeAgentApi.deleteSession(session.session_id)
    const index = sessions.value.findIndex(item => item.session_id === session.session_id)
    sessions.value = sessions.value.filter(item => item.session_id !== session.session_id)
    if (session.session_id === activeSessionId.value) {
      activeSessionId.value = ''
      activeTask.value = null
      messages.value = []
      events.value = []
      controller?.abort()
      controller = null
      const nextSession = sessions.value[index] || sessions.value[0]
      if (nextSession) {
        await selectSession(nextSession.session_id)
      } else {
        await createSession()
      }
    }
    ElMessage.success('会话已删除')
  } catch (error: any) {
    if (error !== 'cancel' && error !== 'close') {
      ElMessage.error(error?.message || '删除会话失败')
    }
  }
}

const loadSessionState = async (sessionId: string) => {
  const loadVersion = ++sessionLoadVersion
  const [messagesRes, eventsRes, tasksRes] = await Promise.all([
    vibeAgentApi.listMessages(sessionId),
    vibeAgentApi.replayEvents(sessionId, 0),
    vibeAgentApi.listTasks({ session_id: sessionId, page: 1, page_size: 20 })
  ])
  if (loadVersion !== sessionLoadVersion || sessionId !== activeSessionId.value) return
  messages.value = ((messagesRes as any).data || []) as VibeMessage[]
  events.value = ((eventsRes as any).data || []) as VibeEvent[]
  activityOpen.value = {}
  const sessionTasks = (((tasksRes as any).data?.tasks || []) as VibeTask[])
  const currentTask = sessionTasks.find(task => canCancel(task.status)) || null
  activeTask.value = currentTask
  if (currentTask) tasksBySession.value[currentTask.session_id] = currentTask
  else delete tasksBySession.value[sessionId]
  await nextTick(scrollToBottom)
}

const selectSession = async (sessionId: string) => {
  if (!sessionId || sessionId === activeSessionId.value) return
  activeSessionId.value = sessionId
  activeTask.value = null
  await router.replace({ path: '/research-agent', query: { ...route.query, session_id: sessionId } })
  await loadSessionState(sessionId)
  reconnectStream()
}

const reconnectStream = () => {
  if (!activeSessionId.value) return
  const generation = ++streamGeneration
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
        if (generation !== streamGeneration) return
        streamState.value = 'connected'
      },
      onError: (error) => {
        if (generation !== streamGeneration) return
        streamState.value = 'disconnected'
        streamError.value = error.message
        scheduleReconnect(generation)
      },
      onClosed: () => {
        if (generation !== streamGeneration) return
        if (streamState.value === 'connected') streamState.value = 'disconnected'
        scheduleReconnect(generation)
      }
    },
    controller.signal
  ).catch((error) => {
    if (error.name !== 'AbortError') {
      if (generation !== streamGeneration) return
      if (error instanceof VibeAgentUnauthorizedError || error?.status === 401) {
        authRequired.value = true
        streamState.value = 'disconnected'
        streamError.value = '登录已过期，请重新登录'
        return
      }
      streamState.value = 'disconnected'
      streamError.value = error.message || '事件流已断开'
      ElMessage.warning(streamError.value)
      scheduleReconnect(generation)
    }
  })
}

const isAuthError = (error: any) => (
  error?.response?.status === 401 ||
  error?.status === 401 ||
  /登录已过期|认证失败|token无效|token 失效|invalid crypto padding/i.test(String(error?.message || ''))
)

const scheduleReconnect = (generation = streamGeneration) => {
  if (generation !== streamGeneration) return
  if (reconnectTimer) window.clearTimeout(reconnectTimer)
  reconnectTimer = window.setTimeout(() => {
    if (generation !== streamGeneration) return
    if (activeTask.value && ['queued', 'processing', 'pending', 'running'].includes(activeTask.value.status)) {
      reconnectStream()
    }
  }, 2500)
}

const handleEvent = (event: VibeEvent) => {
  if (event.session_id && event.session_id !== activeSessionId.value) return
  if (event.sequence && events.value.some(item => item.sequence === event.sequence)) return
  events.value.push(event)
  if (event.event_type === 'message_created' && event.payload?.message?.role === 'assistant') {
    const message = event.payload.message as VibeMessage
    if (message.message_id && !messages.value.some(item => item.message_id === message.message_id)) {
      messages.value.push(message)
    }
  }
  if (event.event_type === 'task_status' && event.payload?.status) {
    const taskId = String(event.task_id || event.payload.task_id || activeTask.value?.task_id || '')
    const status = String(event.payload.status)
    if (taskId) {
      const task = {
        ...(tasksBySession.value[event.session_id || activeSessionId.value] || activeTask.value || {}),
        task_id: taskId,
        session_id: event.session_id || activeSessionId.value,
        status
      } as VibeTask
      if (canCancel(status)) {
        tasksBySession.value[task.session_id] = task
        if (task.session_id === activeSessionId.value) activeTask.value = task
      } else {
        delete tasksBySession.value[task.session_id]
        if (task.session_id === activeSessionId.value && activeTask.value?.task_id === taskId) {
          activeTask.value = null
        }
      }
    }
    if (event.payload.status === 'failed') {
      streamState.value = 'disconnected'
      streamError.value = event.payload.error || '任务失败'
    }
  }
  if (event.event_type === 'error' && event.payload?.error) {
    streamError.value = event.payload.error
    scheduleReconnect(streamGeneration)
  }
  nextTick(scrollToBottom)
}

const sendMessage = async () => {
  if (!prompt.value.trim() || !activeSessionId.value || hasRunningTask.value) return
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

    // 构建消息 payload，包含可选的上下文注入参数
    const messagePayload: any = {
      content,
      idempotency_key: `web_${Date.now()}_${Math.random().toString(36).slice(2)}`
    }

    // 如果启用了投资画像上下文注入
    if (investmentContextEnabled.value && useProfileContext.value) {
      messagePayload.profile_id = 'current_user_profile' // 使用当前用户的画像
    }

    // 如果选择了策略
    if (selectedStrategyId.value) {
      messagePayload.strategy_id = selectedStrategyId.value
    }

    // 如果选择了模型
    if (selectedModel.value) {
      messagePayload.model = selectedModel.value
    }

    const res = await vibeAgentApi.sendMessage(activeSessionId.value, messagePayload)
    activeTask.value = (res as any).data as VibeTask
    tasksBySession.value[activeTask.value.session_id] = activeTask.value
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
  delete tasksBySession.value[activeTask.value.session_id]
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
  if (!await loadHealth() || authRequired.value) return
  try {
    await loadSessions()
  } catch {
    if (authRequired.value) return
    ElMessage.error('会话列表加载失败')
    return
  }
  await openSessionFromRoute()
  if (!activeSessionId.value && sessions.value.length === 0) {
    await createSession()
  }
  if (activeSessionId.value && streamState.value === 'idle') {
    reconnectStream()
  }

  // 加载可用模型列表
  try {
    availableModels.value = await configApi.getAvailableModels()
  } catch (error) {
    console.warn('Failed to load available models:', error)
  }

  // 加载个人投资助手上下文选项
  try {
    const profileResponse = await fetch('/api/investment/profile')
    if (profileResponse.ok) {
      const profileData = await profileResponse.json()
      if (profileData.success && profileData.data?.context_injection_enabled !== false) {
        investmentContextEnabled.value = true
        useProfileContext.value = true
      }
    }

    const strategiesResponse = await fetch('/api/investment/strategies?limit=20')
    if (strategiesResponse.ok) {
      const strategiesData = await strategiesResponse.json()
      if (strategiesData.success) {
        availableStrategies.value = strategiesData.data.items || []
      }
    }
  } catch (error) {
    console.warn('Failed to load investment context:', error)
  }
})

onUnmounted(() => {
  streamGeneration += 1
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
  min-width: 0;
  overflow: hidden;
  font-weight: 600;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.session-row-actions {
  display: flex;
  align-items: center;
  flex: 0 0 auto;
  gap: 2px;
}

.session-time {
  color: var(--el-text-color-secondary);
  font-size: 12px;
  white-space: nowrap;
}

.session-delete {
  opacity: 0;
  color: var(--el-color-danger);
}

.session-row:hover .session-delete,
.session-row:focus-visible .session-delete,
.session-row.active .session-delete {
  opacity: 1;
}

.session-preview {
  margin-top: 6px;
  color: var(--el-text-color-secondary);
  font-size: 12px;
  line-height: 1.45;
  display: -webkit-box;
  overflow: hidden;
  -webkit-box-orient: vertical;
  -webkit-line-clamp: 2;
  overflow-wrap: anywhere;
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

.transcript-pane {
  display: flex;
  flex-direction: column;
  flex: 1;
  min-height: 0;
  min-width: 0;
  border: 1px solid var(--el-border-color-light);
  border-radius: 8px;
  background: var(--el-bg-color);
  margin-top: 16px;
  overflow: hidden;
}

.transcript-scroll {
  display: block;
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
  flex-direction: column;
  margin-bottom: 12px;
}

.message-row.user {
  justify-content: flex-end;
  align-items: flex-end;
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

.activity-line {
  width: min(760px, 82%);
  margin: 0 0 8px;
  overflow: hidden;
  border: 1px solid var(--el-border-color-lighter);
  border-radius: 8px;
  background: var(--el-fill-color-extra-light);
}

.activity-current {
  margin: 0 0 14px;
}

.activity-running {
  border-color: var(--el-color-primary-light-5);
  background: var(--el-color-primary-light-9);
}

.activity-summary {
  display: flex;
  align-items: center;
  width: 100%;
  min-height: 34px;
  gap: 8px;
  padding: 7px 10px;
  border: 0;
  background: transparent;
  color: var(--el-text-color-regular);
  text-align: left;
  cursor: pointer;
}

.activity-summary:hover {
  background: var(--el-fill-color-light);
}

.activity-status-icon {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 16px;
  height: 16px;
  flex: 0 0 16px;
  border-radius: 50%;
  color: var(--el-color-success);
  font-size: 15px;
  font-weight: 700;
}

.status-running {
  color: var(--el-color-primary);
  animation: activity-pulse 1s ease-in-out infinite;
}

.status-failed {
  color: var(--el-color-danger);
  background: var(--el-color-danger-light-9);
}

.activity-summary-text {
  min-width: 0;
  flex: 1;
  overflow: hidden;
  color: var(--el-text-color-secondary);
  font-size: 13px;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.activity-chevron {
  flex: 0 0 auto;
  color: var(--el-text-color-secondary);
  font-size: 18px;
  line-height: 1;
}

.activity-steps {
  display: flex;
  flex-direction: column;
  max-height: min(240px, 30vh);
  overflow-y: auto;
  gap: 7px;
  padding: 8px 12px 10px 34px;
  border-top: 1px solid var(--el-border-color-lighter);
}

.activity-step {
  display: flex;
  align-items: baseline;
  min-width: 0;
  gap: 7px;
  color: var(--el-text-color-regular);
  font-size: 12px;
  line-height: 1.4;
}

.streaming-response {
  max-height: 180px;
  overflow-y: auto;
  margin: 0 12px 10px 34px;
  padding: 9px 10px;
  border-top: 1px solid var(--el-border-color-lighter);
  color: var(--el-text-color-regular);
  font-size: 13px;
  line-height: 1.65;
  white-space: pre-wrap;
}

.step-dot {
  width: 6px;
  height: 6px;
  flex: 0 0 6px;
  margin-left: -18px;
  border-radius: 50%;
  background: var(--el-color-info);
}

.step-ok {
  background: var(--el-color-success);
}

.step-error {
  background: var(--el-color-danger);
}

.step-running {
  background: var(--el-color-primary);
}

.step-title {
  flex: 0 0 auto;
  font-weight: 500;
}

.step-action {
  min-width: 0;
  overflow: hidden;
  color: var(--el-text-color-secondary);
  text-overflow: ellipsis;
  white-space: nowrap;
}

.step-elapsed {
  margin-left: auto;
  flex: 0 0 auto;
  color: var(--el-text-color-secondary);
  font-size: 11px;
  font-variant-numeric: tabular-nums;
}

.message-role {
  margin-bottom: 6px;
  font-size: 12px;
  opacity: 0.7;
}

.message-content {
  line-height: 1.65;
}

.markdown-body {
  min-width: 0;
  overflow-wrap: anywhere;
}

.markdown-body :deep(:first-child) {
  margin-top: 0;
}

.markdown-body :deep(:last-child) {
  margin-bottom: 0;
}

.markdown-body :deep(p) {
  margin: 0 0 10px;
}

.markdown-body :deep(h1),
.markdown-body :deep(h2),
.markdown-body :deep(h3),
.markdown-body :deep(h4) {
  margin: 16px 0 8px;
  color: var(--el-text-color-primary);
  line-height: 1.35;
}

.markdown-body :deep(h1) { font-size: 20px; }
.markdown-body :deep(h2) { font-size: 18px; }
.markdown-body :deep(h3) { font-size: 16px; }
.markdown-body :deep(h4) { font-size: 14px; }

.markdown-body :deep(ul),
.markdown-body :deep(ol) {
  margin: 8px 0 12px;
  padding-left: 22px;
}

.markdown-body :deep(li) {
  margin: 4px 0;
}

.markdown-body :deep(blockquote) {
  margin: 10px 0;
  padding: 6px 12px;
  border-left: 3px solid var(--el-color-primary-light-3);
  color: var(--el-text-color-secondary);
  background: var(--el-fill-color-lighter);
}

.markdown-body :deep(code) {
  padding: 2px 5px;
  border-radius: 4px;
  color: var(--el-color-danger);
  background: var(--el-fill-color-light);
  font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace;
  font-size: 0.9em;
}

.markdown-body :deep(pre) {
  max-width: 100%;
  margin: 10px 0;
  padding: 12px;
  overflow-x: auto;
  border-radius: 6px;
  background: #1f2937;
  color: #f3f4f6;
}

.markdown-body :deep(pre code) {
  padding: 0;
  color: inherit;
  background: transparent;
  white-space: pre;
}

.markdown-body :deep(table) {
  display: block;
  max-width: 100%;
  margin: 10px 0 14px;
  overflow-x: auto;
  border-collapse: collapse;
  font-size: 13px;
}

.markdown-body :deep(th),
.markdown-body :deep(td) {
  min-width: 90px;
  padding: 7px 10px;
  border: 1px solid var(--el-border-color);
  text-align: left;
  vertical-align: top;
}

.markdown-body :deep(th) {
  background: var(--el-fill-color-light);
  font-weight: 600;
}

.markdown-body :deep(a) {
  color: var(--el-color-primary);
  word-break: break-all;
}

.context-options {
  display: flex;
  align-items: center;
  padding: 8px 12px;
  margin-bottom: 8px;
  background: var(--el-fill-color-lighter);
  border-radius: 6px;
  font-size: 13px;
}

.context-options .el-checkbox {
  margin-right: 0;
}

.composer {
  position: relative;
  display: grid;
  grid-template-columns: minmax(0, 1fr) auto;
  gap: 10px;
  padding: 12px;
  border-top: 1px solid var(--el-border-color-light);
  background: var(--el-bg-color);
}

.composer-lock {
  grid-column: 1 / -1;
  color: var(--el-text-color-secondary);
  font-size: 12px;
  text-align: center;
}

.compact-section {
  margin-top: 18px;
}

@keyframes activity-pulse {
  0%, 100% { opacity: 0.35; }
  50% { opacity: 1; }
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

  .activity-line {
    width: 100%;
  }
}
</style>
