<template>
  <div class="decision-audit-page">
    <div class="page-header">
      <h1 class="page-title">
        <el-icon><List /></el-icon>
        决策审计
      </h1>
      <p>按业务 ID、任务 ID、会话 ID 或 Trial ID 聚合完整决策链</p>
    </div>

    <el-card shadow="never" style="margin-bottom: 24px">
      <el-form :inline="true" @submit.prevent="loadAudit">
        <el-form-item label="审计标识">
          <el-input
            v-model="identifier"
            placeholder="task_id / session_id / trial_id"
            clearable
            style="width: 340px"
          />
        </el-form-item>
        <el-form-item label="范围">
          <el-radio-group v-model="scope" size="small">
            <el-radio-button value="session">会话</el-radio-button>
            <el-radio-button value="task">单轮对话</el-radio-button>
          </el-radio-group>
        </el-form-item>
        <el-form-item>
          <el-button type="primary" :loading="loading" @click="loadAudit">查询</el-button>
          <el-button @click="loadMetrics">指标</el-button>
        </el-form-item>
      </el-form>
      <el-alert
        v-if="audit?.audit_status === 'events_without_chain' || audit?.audit_status === 'legacy_unverified'"
        title="本次对话存在运行事件，但尚未生成结构化决策链。以下内容为原始运行事件。"
        type="warning"
        :closable="false"
        show-icon
      />
      <el-alert
        v-if="audit?.audit_status === 'partial'"
        title="已生成部分结构化决策链，部分关联数据或解释校验不完整"
        type="warning"
        :closable="false"
        show-icon
      />
      <el-descriptions v-if="audit" :column="2" border size="small" style="margin-top: 12px">
        <el-descriptions-item label="查询范围">{{ audit.scope === 'session' ? '会话级' : '单轮对话级' }}</el-descriptions-item>
        <el-descriptions-item label="业务 ID">{{ audit.business_id || '-' }}</el-descriptions-item>
        <el-descriptions-item label="会话 ID">{{ audit.session_id || '-' }}</el-descriptions-item>
        <el-descriptions-item label="任务 ID">{{ audit.task_id || '会话内多任务' }}</el-descriptions-item>
      </el-descriptions>
      <el-alert
        v-if="audit?.audit_status === 'empty' || audit?.audit_status === 'unavailable'"
        title="未找到决策链、trace 或日志"
        type="info"
        :closable="false"
        show-icon
      />
      <el-descriptions v-if="audit?.audit_counts" :column="3" border size="small" style="margin-top: 12px">
        <el-descriptions-item label="运行事件数">{{ audit.audit_counts.vibe_events || 0 }}</el-descriptions-item>
        <el-descriptions-item label="Trace 数">{{ audit.audit_counts.trace_events || 0 }}</el-descriptions-item>
        <el-descriptions-item label="决策记录数">{{ audit.audit_counts.decision_records || 0 }}</el-descriptions-item>
        <el-descriptions-item label="解释">{{ audit.audit_counts.explanations || 0 }}</el-descriptions-item>
        <el-descriptions-item label="校验">{{ audit.audit_counts.validations || 0 }}</el-descriptions-item>
        <el-descriptions-item label="复核">{{ audit.audit_counts.reviews || 0 }}</el-descriptions-item>
      </el-descriptions>
    </el-card>

    <template v-if="audit">
      <el-row :gutter="16" style="margin-bottom: 24px">
        <el-col :span="6">
          <el-card shadow="never" class="stat-card">
            <div class="stat-value">{{ (audit.decision_chain || []).length }}</div>
            <div class="stat-label">决策节点</div>
          </el-card>
        </el-col>
        <el-col :span="6">
          <el-card shadow="never" class="stat-card">
            <div class="stat-value">{{ (audit.trace_events || []).length }}</div>
            <div class="stat-label">Trace 事件</div>
          </el-card>
        </el-col>
        <el-col :span="6">
          <el-card shadow="never" class="stat-card">
            <div class="stat-value">{{ (audit.evidence_events || []).length }}</div>
            <div class="stat-label">证据事件</div>
          </el-card>
        </el-col>
        <el-col :span="6">
          <el-card shadow="never" class="stat-card">
            <div class="stat-value">{{ audit.query_latency_ms || 0 }}ms</div>
            <div class="stat-label">审计查询耗时</div>
          </el-card>
        </el-col>
      </el-row>

      <el-card v-if="audit.scope === 'session' && (audit.tasks || []).length" shadow="never" style="margin-bottom: 24px">
        <template #header><span>会话内对话</span></template>
        <el-table :data="audit.tasks" size="small" stripe @row-click="selectTask">
          <el-table-column prop="task_id" label="单轮对话 ID" min-width="250" show-overflow-tooltip>
            <template #default="{ row }">
              <div class="id-cell">
                <span>{{ row.task_id }}</span>
                <el-button text size="small" :icon="DocumentCopy" aria-label="复制单轮对话 ID" @click.stop="copyId(row.task_id)" />
              </div>
            </template>
          </el-table-column>
          <el-table-column prop="status" label="状态" width="100" />
          <el-table-column prop="prompt" label="用户问题" min-width="260" show-overflow-tooltip />
          <el-table-column prop="created_at" label="时间" width="170">
            <template #default="{ row }">{{ formatTime(row.created_at) }}</template>
          </el-table-column>
        </el-table>
      </el-card>

      <el-card v-if="(audit.messages || []).length" shadow="never" style="margin-bottom: 24px">
        <template #header><span>对话上下文</span></template>
        <div class="message-context">
          <div v-for="message in audit.messages" :key="message.message_id || `${message.role}-${message.created_at}`" class="context-message">
            <span class="context-role">{{ message.role === 'user' ? '用户' : 'Agent' }}</span>
            <span class="context-content">{{ message.content }}</span>
            <span class="context-time">{{ formatTime(message.created_at) }}</span>
          </div>
        </div>
      </el-card>

      <el-card v-if="events.length || eventsTotal" shadow="never" style="margin-bottom: 24px">
        <template #header><span>运行事件</span></template>
        <el-table :data="events" v-loading="eventsLoading" size="small" stripe>
          <el-table-column label="#" width="70">
            <template #default="{ $index }">{{ eventRowNumber($index) }}</template>
          </el-table-column>
          <el-table-column label="事件" width="150">
            <template #default="{ row }">{{ eventDisplayName(row) }}</template>
          </el-table-column>
          <el-table-column label="内容" min-width="420">
            <template #default="{ row }">
              <pre class="event-content">{{ formatEventPayload(row.payload) }}</pre>
            </template>
          </el-table-column>
          <el-table-column prop="created_at" label="时间" width="170">
            <template #default="{ row }">{{ formatTime(row.created_at) }}</template>
          </el-table-column>
        </el-table>
        <el-pagination
          v-if="eventsTotal > eventsPageSize"
          style="margin-top: 12px; justify-content: flex-end"
          layout="prev, pager, next"
          :total="eventsTotal"
          :page-size="eventsPageSize"
          :current-page="eventsPage"
          @current-change="loadEvents"
        />
      </el-card>

      <el-card shadow="never" style="margin-bottom: 24px">
        <template #header><span>决策链</span></template>
        <el-table :data="audit.decision_chain || []" size="small" stripe>
          <el-table-column prop="scenario" label="场景" min-width="140" show-overflow-tooltip />
          <el-table-column prop="selected_option" label="选择" width="130" show-overflow-tooltip />
          <el-table-column prop="selection_reason" label="依据" min-width="200" show-overflow-tooltip />
          <el-table-column prop="conclusion" label="结论" min-width="240" show-overflow-tooltip />
          <el-table-column prop="status" label="状态" width="110" />
          <el-table-column prop="risk_level" label="风险" width="80" />
        </el-table>
      </el-card>

      <el-card shadow="never" style="margin-bottom: 24px">
        <template #header><span>最终输出</span></template>
        <pre class="output-block">{{ audit.final_output || '（无最终输出）' }}</pre>
      </el-card>

      <el-row :gutter="16">
        <el-col :span="12">
          <el-card shadow="never">
            <template #header><span>解释与校验</span></template>
            <el-table :data="audit.validations || []" size="small" stripe>
              <el-table-column prop="status" label="状态" width="110" />
              <el-table-column prop="reason" label="原因" min-width="180" show-overflow-tooltip />
              <el-table-column prop="confidence" label="置信度" width="90" />
            </el-table>
          </el-card>
        </el-col>
        <el-col :span="12">
          <el-card shadow="never">
            <template #header><span>人工复核</span></template>
            <el-table :data="audit.reviews || []" size="small" stripe>
              <el-table-column prop="status" label="状态" width="100" />
              <el-table-column prop="action" label="动作" width="120" />
              <el-table-column prop="reason" label="原因" min-width="180" show-overflow-tooltip />
            </el-table>
          </el-card>
        </el-col>
      </el-row>
    </template>

    <el-card v-if="metrics.length" shadow="never">
      <template #header><span>生产决策链指标</span></template>
      <el-table :data="metrics" size="small" stripe>
        <el-table-column prop="task_type" label="任务类型" width="130" />
        <el-table-column prop="decision_nodes" label="决策节点" width="100" />
        <el-table-column prop="completeness_rate" label="完整率" width="100">
          <template #default="{ row }">{{ ((row.completeness_rate || 0) * 100).toFixed(1) }}%</template>
        </el-table-column>
        <el-table-column prop="consistency_rate" label="一致率" width="100">
          <template #default="{ row }">{{ ((row.consistency_rate || 0) * 100).toFixed(1) }}%</template>
        </el-table-column>
        <el-table-column prop="inconsistent_count" label="不一致" width="90" />
        <el-table-column prop="high_risk_pauses" label="高风险暂停" width="110" />
        <el-table-column prop="created_at" label="时间" min-width="160">
          <template #default="{ row }">{{ formatTime(row.created_at) }}</template>
        </el-table-column>
      </el-table>
    </el-card>
  </div>
</template>

<script setup lang="ts">
import { ref } from 'vue'
import { ElMessage } from 'element-plus'
import { DocumentCopy, List } from '@element-plus/icons-vue'
import { useRoute, useRouter } from 'vue-router'
import { request } from '@/api/request'

const route = useRoute()
const router = useRouter()
const identifier = ref('')
const scope = ref<'auto' | 'session' | 'task'>('auto')
const audit = ref<any>(null)
const metrics = ref<any[]>([])
const loading = ref(false)
const events = ref<any[]>([])
const eventsPage = ref(1)
const eventsPageSize = ref(20)
const eventsTotal = ref(0)
const eventsLoading = ref(false)

const loadAudit = async () => {
  const value = identifier.value.trim()
  if (!value) {
    ElMessage.warning('请输入业务 ID、任务 ID、会话 ID 或 Trial ID')
    return
  }
  loading.value = true
  try {
    const res = await request.get(`/api/decision-audit/chains/${encodeURIComponent(value)}`, { params: { scope: scope.value } })
    audit.value = unwrapApiData(res)
    eventsPage.value = 1
    void loadEvents(1)
  } catch (error: any) {
    ElMessage.error(error?.response?.data?.detail || '查询决策审计链失败')
  } finally {
    loading.value = false
  }
}

const loadEvents = async (page = eventsPage.value) => {
  const value = identifier.value.trim()
  if (!value) return
  eventsPage.value = Math.max(1, Number(page) || 1)
  eventsLoading.value = true
  try {
    const res = await request.get(`/api/decision-audit/chains/${encodeURIComponent(value)}/events`, {
      params: {
        scope: scope.value,
        page: eventsPage.value,
        page_size: eventsPageSize.value,
      }
    })
    const data = unwrapApiData(res)
    events.value = (data?.items || []).filter((item: any) => item?.event_type !== 'token')
    eventsTotal.value = data?.total || 0
  } catch (error: any) {
    ElMessage.error(error?.response?.data?.detail || '加载运行事件失败')
  } finally {
    eventsLoading.value = false
  }
}

const loadMetrics = async () => {
  try {
    const res = await request.get('/api/decision-audit/metrics')
    const data = unwrapApiData(res)
    metrics.value = data?.items || []
  } catch (error: any) {
    ElMessage.error(error?.response?.data?.detail || '读取决策指标失败')
  }
}

const formatTime = (value?: string) => value ? new Date(value).toLocaleString('zh-CN') : '-'
const EVENT_LABELS: Record<string, string> = {
  task_created: '创建任务',
  session_created: '创建会话',
  task_queued: '任务排队',
  task_started: '开始任务',
  task_status: '任务状态变更',
  message_created: '生成消息',
  'message.received': '接收消息',
  tool_call: '调用工具',
  tool_result: '工具返回',
  decision: '形成决策',
  evidence: '获取证据',
  retrieval: '检索信息',
  citation: '添加引用',
  message: '生成消息',
  skill_route: '路由技能',
  skill_execute: '执行技能',
  react_summary: '生成分析总结',
  swarm_status: '协同分析状态',
  'attempt.created': '创建执行尝试',
  'attempt.started': '开始执行尝试',
  'attempt.completed': '完成执行尝试',
  'attempt.failed': '执行尝试失败',
  'attempt.cancelled': '取消执行尝试',
  llm_call: '调用模型',
  llm_usage: '模型用量',
  error: '执行异常'
}
const eventDisplayName = (row: any) => {
  if (row.event_name) return row.event_name
  const phase = row.payload?.phase || row.payload?._meta?.original_type
  if (row.event_type === 'worker_status' && phase) return EVENT_LABELS[phase] || '运行状态变更'
  if (row.event_type === 'tool_call' && row.payload?.phase === 'tool_result') return '工具返回'
  return EVENT_LABELS[row.event_type || ''] || '运行事件'
}
const eventRowNumber = (index: number) => (eventsPage.value - 1) * eventsPageSize.value + index + 1
const formatEventPayload = (payload: unknown) => {
  if (payload == null) return '-'
  if (typeof payload === 'string') return payload
  try { return JSON.stringify(payload, null, 2) } catch { return String(payload) }
}

const unwrapApiData = (response: any) => response?.data?.data ?? response?.data ?? response ?? null

const copyId = async (value?: string) => {
  if (!value) return
  try {
    await navigator.clipboard.writeText(value)
    ElMessage.success('ID 已复制')
  } catch {
    ElMessage.warning('复制失败，请手动选择 ID')
  }
}

const selectTask = (task: any) => {
  identifier.value = String(task.task_id || '')
  scope.value = 'task'
  void router.replace({ query: { ...route.query, id: identifier.value, scope: 'task' } })
  void loadAudit()
}

const initialId = String(route.query.id || '')
if (initialId) {
  identifier.value = initialId
  scope.value = route.query.scope === 'session' ? 'session' : 'task'
  void loadAudit()
}
</script>

<style scoped>
.decision-audit-page { padding: 24px; }
.page-header { margin-bottom: 24px; }
.page-title { display: flex; align-items: center; gap: 10px; font-size: 24px; font-weight: 600; margin: 8px 0 4px; }
.page-header p { color: var(--el-text-color-secondary); font-size: 13px; margin: 0; }
.stat-card { text-align: center; padding: 10px 0; }
.stat-value { font-size: 24px; font-weight: 600; }
.stat-label { color: var(--el-text-color-secondary); font-size: 12px; margin-top: 4px; }
.output-block { max-height: 320px; overflow: auto; margin: 0; white-space: pre-wrap; word-break: break-word; font-size: 13px; line-height: 1.6; }
.event-content { max-height: 180px; overflow: auto; margin: 0; white-space: pre-wrap; word-break: break-word; font-size: 12px; line-height: 1.45; }
.id-cell { display: flex; align-items: center; gap: 4px; min-width: 0; }
.id-cell span { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.message-context { display: grid; gap: 8px; max-height: 360px; overflow: auto; }
.context-message { display: grid; grid-template-columns: 48px minmax(0, 1fr) 150px; gap: 10px; align-items: start; padding: 8px 10px; border-bottom: 1px solid var(--el-border-color-lighter); font-size: 13px; }
.context-role { color: var(--el-color-primary); font-weight: 600; }
.context-content { white-space: pre-wrap; word-break: break-word; line-height: 1.5; }
.context-time { color: var(--el-text-color-secondary); font-size: 12px; text-align: right; }
</style>
