<template>
  <div class="run-detail-page">
    <div class="page-header">
      <div>
        <el-button link @click="$router.push('/evaluation/runs')">← 返回列表</el-button>
        <h1 class="page-title">
          <el-icon><VideoPlay /></el-icon>
          评测运行详情
        </h1>
        <p class="run-id">{{ runId }}</p>
      </div>
      <div>
        <el-tag :type="getStatusType(run.status)" size="large" v-if="run.status">
          {{ getStatusLabel(run.status) }}
        </el-tag>
        <el-button
          v-if="run.status === 'running' || run.status === 'pending'"
          type="danger"
          style="margin-left: 12px"
          @click="cancelRun"
        >
          取消运行
        </el-button>
      </div>
    </div>

    <!-- 运行信息卡片 -->
    <el-row :gutter="16" style="margin-bottom: 24px">
      <el-col :span="6">
        <el-card shadow="never" class="info-card">
          <div class="info-label">数据集</div>
          <div class="info-value">{{ run.dataset_id || '-' }}</div>
        </el-card>
      </el-col>
      <el-col :span="6">
        <el-card shadow="never" class="info-card">
          <div class="info-label">版本</div>
          <div class="info-value">{{ run.dataset_version || '-' }}</div>
        </el-card>
      </el-col>
      <el-col :span="6">
        <el-card shadow="never" class="info-card">
          <div class="info-label">进度</div>
          <div class="info-value">
            <el-progress
              :percentage="progress"
              :status="run.status === 'failed' ? 'exception' : undefined"
            />
            <span style="font-size: 12px; color: var(--el-text-color-secondary)">
              {{ run.completed_trials || 0 }}/{{ totalTrials }} 完成，{{ run.failed_trials || 0 }} 失败
            </span>
          </div>
        </el-card>
      </el-col>
      <el-col :span="6">
        <el-card shadow="never" class="info-card">
          <div class="info-label">创建时间</div>
          <div class="info-value">{{ formatTime(run.created_at) }}</div>
        </el-card>
      </el-col>
    </el-row>

    <!-- Trial 列表 -->
    <el-card shadow="never">
      <template #header>
        <div class="card-header">
          <span>Trial 列表（共 {{ trials.length }} 条）</span>
          <el-button size="small" @click="loadTrials">刷新</el-button>
        </div>
      </template>

      <el-table :data="trials" v-loading="loadingTrials" stripe>
        <el-table-column prop="trial_id" label="Trial ID" width="280" show-overflow-tooltip />
        <el-table-column prop="case_id" label="Case ID" width="180" show-overflow-tooltip />
        <el-table-column prop="trial_index" label="#" width="60" />
        <el-table-column prop="status" label="状态" width="120">
          <template #default="{ row }">
            <el-tag :type="getTrialStatusType(row.status)" size="small">
              {{ getTrialStatusLabel(row.status) }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="latency_ms" label="耗时" width="100">
          <template #default="{ row }">
            {{ row.latency_ms ? `${row.latency_ms}ms` : '-' }}
          </template>
        </el-table-column>
        <el-table-column prop="error_message" label="错误信息" min-width="200" show-overflow-tooltip>
          <template #default="{ row }">
            <span v-if="row.error_message" style="color: var(--el-color-danger)">
              {{ row.error_message }}
            </span>
            <span v-else>-</span>
          </template>
        </el-table-column>
        <el-table-column label="操作" fixed="right" width="120">
          <template #default="{ row }">
            <el-button type="primary" link size="small" @click="viewTrialTrace(row.trial_id)">
              Trace
            </el-button>
          </template>
        </el-table-column>
      </el-table>
    </el-card>

    <!-- Trace 查看抽屉 -->
    <el-drawer v-model="traceDrawerVisible" title="Trial Trace" size="60%" direction="rtl">
      <div v-if="traceLoading" v-loading="true" style="height: 200px"></div>
      <div v-else-if="traceEvents.length === 0" style="text-align: center; padding: 40px; color: var(--el-text-color-secondary)">
        暂无 trace 事件
      </div>
      <el-timeline v-else>
        <el-timeline-item
          v-for="event in traceEvents"
          :key="event.event_id"
          :timestamp="formatTime(event.timestamp)"
          :type="getTraceEventType(event.event_type)"
          placement="top"
        >
          <el-card shadow="never" class="trace-event-card">
            <div class="trace-event-header">
              <el-tag size="small" :type="getTraceEventTagType(event.event_type)">
                {{ event.event_type }}
              </el-tag>
              <span class="trace-sequence">#{{ event.sequence }}</span>
            </div>
            <pre class="trace-data">{{ JSON.stringify(event.data, null, 2) }}</pre>
          </el-card>
        </el-timeline-item>
      </el-timeline>
    </el-drawer>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import { useRoute } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'
import { VideoPlay } from '@element-plus/icons-vue'
import axios from 'axios'

const route = useRoute()

const runId = computed(() => route.params.id as string)
const run = ref<any>({})
const trials = ref<any[]>([])
const loadingTrials = ref(false)

const traceDrawerVisible = ref(false)
const traceEvents = ref<any[]>([])
const traceLoading = ref(false)

const totalTrials = computed(() => {
  return (run.value.total_cases || 0) * (run.value.num_trials_per_case || 1)
})

const progress = computed(() => {
  if (!totalTrials.value) return 0
  const completed = (run.value.completed_trials || 0) + (run.value.failed_trials || 0)
  return Math.round((completed / totalTrials.value) * 100)
})

const loadRun = async () => {
  try {
    const res = await axios.get(`/api/eval/runs/${runId.value}`)
    run.value = res.data?.data || {}
  } catch (error) {
    ElMessage.error('加载运行详情失败')
  }
}

const loadTrials = async () => {
  loadingTrials.value = true
  try {
    const res = await axios.get(`/api/eval/runs/${runId.value}/trials`)
    trials.value = res.data?.data?.items || []
  } catch (error) {
    ElMessage.error('加载 trial 列表失败')
  } finally {
    loadingTrials.value = false
  }
}

const cancelRun = async () => {
  try {
    await ElMessageBox.confirm('确定要取消这个运行吗？', '确认取消', { type: 'warning' })
    await axios.post(`/api/eval/runs/${runId.value}/cancel`)
    ElMessage.success('已取消')
    await loadRun()
    await loadTrials()
  } catch {
    // 用户取消
  }
}

const viewTrialTrace = async (trialId: string) => {
  traceDrawerVisible.value = true
  traceLoading.value = true
  traceEvents.value = []
  try {
    const res = await axios.get(`/api/eval/trials/${trialId}/trace`, { params: { limit: 200 } })
    traceEvents.value = res.data?.data?.items || []
  } catch (error) {
    ElMessage.error('加载 trace 失败')
  } finally {
    traceLoading.value = false
  }
}

// 工具函数
const getStatusType = (status: string): 'primary' | 'success' | 'warning' | 'info' | 'danger' => {
  const map: Record<string, 'primary' | 'success' | 'warning' | 'info' | 'danger'> = { pending: 'info', running: 'warning', completed: 'success', failed: 'danger', cancelled: 'info' }
  return map[status] || 'info'
}

const getStatusLabel = (status: string) => {
  const map: Record<string, string> = { pending: '等待中', running: '运行中', completed: '已完成', failed: '失败', cancelled: '已取消' }
  return map[status] || status
}

const getTrialStatusType = (status: string): 'primary' | 'success' | 'warning' | 'info' | 'danger' => {
  const map: Record<string, 'primary' | 'success' | 'warning' | 'info' | 'danger'> = { pending: 'info', running: 'warning', completed: 'success', failed: 'danger', timeout: 'danger', cancelled: 'info' }
  return map[status] || 'info'
}

const getTrialStatusLabel = (status: string) => {
  const map: Record<string, string> = { pending: '等待中', running: '运行中', completed: '已完成', failed: '失败', timeout: '超时', cancelled: '已取消' }
  return map[status] || status
}

const getTraceEventType = (eventType: string) => {
  if (eventType === 'error') return 'danger'
  if (eventType === 'llm_call' || eventType === 'tool_call') return 'primary'
  if (eventType === 'lifecycle') return 'info'
  if (eventType === 'streaming') return 'success'
  return 'primary'
}

const getTraceEventTagType = (eventType: string): 'primary' | 'success' | 'warning' | 'info' | 'danger' => {
  if (eventType === 'error') return 'danger'
  if (eventType === 'llm_call') return 'primary'
  if (eventType === 'tool_call') return 'warning'
  if (eventType === 'lifecycle') return 'info'
  if (eventType === 'streaming') return 'success'
  if (eventType === 'evidence') return 'success'
  return 'info'
}

const formatTime = (isoString: string) => {
  if (!isoString) return '-'
  return new Date(isoString).toLocaleString('zh-CN')
}

onMounted(async () => {
  await Promise.all([loadRun(), loadTrials()])
})
</script>

<style scoped>
.run-detail-page {
  padding: 24px;
}

.page-header {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  margin-bottom: 24px;
}

.page-title {
  font-size: 24px;
  font-weight: 600;
  display: flex;
  align-items: center;
  gap: 12px;
  margin: 8px 0 4px 0;
}

.run-id {
  margin: 0;
  font-size: 13px;
  color: var(--el-text-color-secondary);
  font-family: monospace;
}

.info-card {
  height: 100px;
}

.info-label {
  font-size: 12px;
  color: var(--el-text-color-secondary);
  margin-bottom: 8px;
}

.info-value {
  font-size: 16px;
  font-weight: 600;
  color: var(--el-text-color-primary);
}

.card-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
}

.trace-event-card {
  padding: 0;
}

.trace-event-header {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 8px;
}

.trace-sequence {
  font-size: 12px;
  color: var(--el-text-color-secondary);
  font-family: monospace;
}

.trace-data {
  margin: 0;
  padding: 8px;
  background: var(--el-fill-color-lighter);
  border-radius: 4px;
  font-size: 12px;
  font-family: monospace;
  max-height: 300px;
  overflow: auto;
  white-space: pre-wrap;
  word-break: break-all;
}
</style>
