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
        <el-form-item>
          <el-button type="primary" :loading="loading" @click="loadAudit">查询</el-button>
          <el-button @click="loadMetrics">指标</el-button>
        </el-form-item>
      </el-form>
      <el-alert
        v-if="audit?.audit_status === 'legacy_unverified'"
        title="该标识没有结构化决策链，已保留原始 trace 和日志"
        type="warning"
        :closable="false"
        show-icon
      />
      <el-alert
        v-else-if="audit?.audit_status === 'unavailable'"
        title="未找到决策链、trace 或日志"
        type="info"
        :closable="false"
        show-icon
      />
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
import { List } from '@element-plus/icons-vue'
import { request } from '@/api/request'

const identifier = ref('')
const audit = ref<any>(null)
const metrics = ref<any[]>([])
const loading = ref(false)

const loadAudit = async () => {
  const value = identifier.value.trim()
  if (!value) {
    ElMessage.warning('请输入业务 ID、任务 ID、会话 ID 或 Trial ID')
    return
  }
  loading.value = true
  try {
    const res = await request.get(`/api/decision-audit/chains/${encodeURIComponent(value)}`)
    audit.value = res.data?.data || null
  } catch (error: any) {
    ElMessage.error(error?.response?.data?.detail || '查询决策审计链失败')
  } finally {
    loading.value = false
  }
}

const loadMetrics = async () => {
  try {
    const res = await request.get('/api/decision-audit/metrics')
    metrics.value = res.data?.data?.items || []
  } catch (error: any) {
    ElMessage.error(error?.response?.data?.detail || '读取决策指标失败')
  }
}

const formatTime = (value?: string) => value ? new Date(value).toLocaleString('zh-CN') : '-'
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
</style>
