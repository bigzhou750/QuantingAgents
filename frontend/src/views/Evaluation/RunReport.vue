<template>
  <div class="run-report-page">
    <div class="page-header">
      <div>
        <el-button link @click="$router.push(`/evaluation/runs/${runId}`)">← 返回运行详情</el-button>
        <h1 class="page-title">
          <el-icon><Document /></el-icon>
          评测报告
        </h1>
        <p class="run-id">{{ runId }}</p>
      </div>
      <div class="header-actions">
        <el-button @click="exportJson" :loading="exporting">
          <el-icon><Download /></el-icon>
          导出 JSON
        </el-button>
        <el-button @click="exportCsv" :loading="exporting">
          <el-icon><Download /></el-icon>
          导出 CSV
        </el-button>
      </div>
    </div>

    <div v-loading="loading">
      <!-- 运行配置 -->
      <el-card shadow="never" style="margin-bottom: 24px">
        <template #header><span>运行配置</span></template>
        <el-descriptions :column="3" border size="small">
          <el-descriptions-item label="Run ID">{{ report.run_id }}</el-descriptions-item>
          <el-descriptions-item label="数据集">{{ report.dataset_id }}</el-descriptions-item>
          <el-descriptions-item label="版本">{{ report.dataset_version }}</el-descriptions-item>
          <el-descriptions-item label="状态">
            <el-tag :type="getStatusType(report.status)" size="small">{{ getStatusLabel(report.status) }}</el-tag>
          </el-descriptions-item>
          <el-descriptions-item label="创建时间">{{ formatTime(report.created_at) }}</el-descriptions-item>
          <el-descriptions-item label="生成时间">{{ formatTime(report.generated_at) }}</el-descriptions-item>
        </el-descriptions>
      </el-card>

      <!-- 核心指标 -->
      <el-card shadow="never" style="margin-bottom: 24px">
        <template #header><span>核心指标</span></template>
        <el-row :gutter="16">
          <el-col :span="4">
            <div class="metric-item">
              <div class="metric-label">成功率</div>
              <div class="metric-value" :class="metricClass(metrics.success_rate, 0.8, 0.7)">
                {{ pct(metrics.success_rate) }}
              </div>
            </div>
          </el-col>
          <el-col :span="4">
            <div class="metric-item">
              <div class="metric-label">失败率</div>
              <div class="metric-value" :class="{'text-danger': metrics.failure_rate > 0.3}">
                {{ pct(metrics.failure_rate) }}
              </div>
            </div>
          </el-col>
          <el-col :span="4">
            <div class="metric-item">
              <div class="metric-label">pass@{{ passK }}</div>
              <div class="metric-value">{{ pct(passMetrics.pass_at_k) }}</div>
            </div>
          </el-col>
          <el-col :span="4">
            <div class="metric-item">
              <div class="metric-label">pass^{{ passK }}</div>
              <div class="metric-value">{{ pct(passMetrics.pass_pow_k) }}</div>
            </div>
          </el-col>
          <el-col :span="4">
            <div class="metric-item">
              <div class="metric-label">平均延迟</div>
              <div class="metric-value">{{ metrics.latency?.mean_ms ? `${Math.round(metrics.latency.mean_ms)}ms` : '-' }}</div>
            </div>
          </el-col>
          <el-col :span="4">
            <div class="metric-item">
              <div class="metric-label">总成本</div>
              <div class="metric-value">${{ (metrics.cost?.total_usd || 0).toFixed(4) }}</div>
            </div>
          </el-col>
        </el-row>
      </el-card>

      <!-- 评分汇总 -->
      <el-card shadow="never" style="margin-bottom: 24px" v-if="scoreSummary && Object.keys(scoreSummary).length">
        <template #header><span>评分维度汇总</span></template>
        <el-table :data="scoreTableData" stripe size="small">
          <el-table-column prop="name" label="评分维度" width="180" />
          <el-table-column prop="avg_score" label="平均分" width="100">
            <template #default="{ row }">{{ pct(row.avg_score) }}</template>
          </el-table-column>
          <el-table-column prop="min_score" label="最低分" width="100">
            <template #default="{ row }">{{ pct(row.min_score) }}</template>
          </el-table-column>
          <el-table-column prop="max_score" label="最高分" width="100">
            <template #default="{ row }">{{ pct(row.max_score) }}</template>
          </el-table-column>
          <el-table-column prop="count" label="样本数" width="80" />
          <el-table-column prop="pass_rate" label="通过率" width="100">
            <template #default="{ row }">{{ pct(row.pass_rate) }}</template>
          </el-table-column>
        </el-table>
      </el-card>

      <!-- Trial 统计 -->
      <el-card shadow="never" style="margin-bottom: 24px">
        <template #header><span>Trial 统计</span></template>
        <el-row :gutter="16">
          <el-col :span="6">
            <div class="metric-item">
              <div class="metric-label">总 Trial 数</div>
              <div class="metric-value">{{ metrics.total_trials || 0 }}</div>
            </div>
          </el-col>
          <el-col :span="6">
            <div class="metric-item">
              <div class="metric-label">成功</div>
              <div class="metric-value text-success">{{ metrics.completed_trials || 0 }}</div>
            </div>
          </el-col>
          <el-col :span="6">
            <div class="metric-item">
              <div class="metric-label">失败</div>
              <div class="metric-value text-danger">{{ metrics.failed_trials || 0 }}</div>
            </div>
          </el-col>
          <el-col :span="6">
            <div class="metric-item">
              <div class="metric-label">超时</div>
              <div class="metric-value text-warning">{{ metrics.timeout_trials || 0 }}</div>
            </div>
          </el-col>
        </el-row>
      </el-card>

      <!-- Claim-Evidence 汇总 (5.3) -->
      <el-card shadow="never" style="margin-bottom: 24px" v-if="claimSummary.total > 0">
        <template #header>
          <div style="display: flex; justify-content: space-between; align-items: center;">
            <span>Claim-Evidence Grounding 汇总</span>
            <el-tag size="small" type="info">共 {{ claimSummary.total }} 条 claim</el-tag>
          </div>
        </template>
        <el-row :gutter="16" style="margin-bottom: 16px">
          <el-col :span="6">
            <div class="metric-item">
              <div class="metric-label">有证据支撑</div>
              <div class="metric-value text-success">{{ claimSummary.supported }}</div>
            </div>
          </el-col>
          <el-col :span="6">
            <div class="metric-item">
              <div class="metric-label">弱支撑</div>
              <div class="metric-value text-warning">{{ claimSummary.weaklySupported }}</div>
            </div>
          </el-col>
          <el-col :span="6">
            <div class="metric-item">
              <div class="metric-label">无证据</div>
              <div class="metric-value text-danger">{{ claimSummary.unsupported }}</div>
            </div>
          </el-col>
          <el-col :span="6">
            <div class="metric-item">
              <div class="metric-label">与证据矛盾</div>
              <div class="metric-value text-danger">{{ claimSummary.contradicted }}</div>
            </div>
          </el-col>
        </el-row>
        <el-progress
          :percentage="claimSummary.coveragePct"
          :color="claimSummary.coveragePct >= 70 ? 'var(--el-color-success)' : claimSummary.coveragePct >= 40 ? 'var(--el-color-warning)' : 'var(--el-color-danger)'"
          :format="() => `覆盖率 ${claimSummary.coveragePct}%`"
          :stroke-width="20"
          :text-inside="true"
        />
      </el-card>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import { useRoute } from 'vue-router'
import { ElMessage } from 'element-plus'
import { Document, Download } from '@element-plus/icons-vue'
import { evalApiClient as axios } from '@/api/evalClient'

const route = useRoute()
const runId = computed(() => route.params.id as string)

const loading = ref(false)
const exporting = ref(false)
const report = ref<any>({})
const metrics = ref<any>({})
const passMetrics = ref<any>({})
const scoreSummary = ref<any>({})

const passK = computed(() => passMetrics.value.k || 3)

// Claim-Evidence 汇总 (5.3)
const claimSummary = computed(() => {
  const cs = metrics.value.claim_summary || {}
  const total = cs.total_claims || 0
  const supported = cs.supported || 0
  const weaklySupported = cs.weakly_supported || 0
  const unsupported = cs.unsupported || 0
  const contradicted = cs.contradicted || 0
  const coveragePct = total > 0 ? Math.round(((supported + weaklySupported) / total) * 100) : 0
  return { total, supported, weaklySupported, unsupported, contradicted, coveragePct }
})

const scoreTableData = computed(() => {
  if (!scoreSummary.value) return []
  return Object.entries(scoreSummary.value).map(([name, data]: [string, any]) => ({
    name,
    avg_score: data.avg_score || 0,
    min_score: data.min_score || 0,
    max_score: data.max_score || 0,
    count: data.count || 0,
    pass_rate: data.pass_rate || 0,
  }))
})

const loadReport = async () => {
  loading.value = true
  try {
    const [reportRes, metricsRes] = await Promise.all([
      axios.get(`/api/eval/report/${runId.value}`),
      axios.get(`/api/eval/runs/${runId.value}/metrics`, { params: { k: 3 } }),
    ])
    report.value = reportRes.data?.data || {}
    const m = metricsRes.data?.data || {}
    metrics.value = m
    passMetrics.value = m
    scoreSummary.value = m.score_aggregation || {}
  } catch (error) {
    ElMessage.error('加载报告失败')
  } finally {
    loading.value = false
  }
}

const exportJson = () => {
  exporting.value = true
  try {
    const data = { ...report.value, metrics: metrics.value }
    const blob = new Blob([JSON.stringify(data, null, 2)], { type: 'application/json' })
    downloadBlob(blob, `eval-report-${runId.value}.json`)
    ElMessage.success('JSON 导出成功')
  } catch {
    ElMessage.error('导出失败')
  } finally {
    exporting.value = false
  }
}

const exportCsv = () => {
  exporting.value = true
  try {
    const rows = [
      ['指标', '值'],
      ['成功率', pct(metrics.value.success_rate)],
      ['失败率', pct(metrics.value.failure_rate)],
      [`pass@${passK.value}`, pct(passMetrics.value.pass_at_k)],
      [`pass^${passK.value}`, pct(passMetrics.value.pass_pow_k)],
      ['平均延迟(ms)', metrics.value.latency?.mean_ms || 0],
      ['总成本(USD)', metrics.value.cost?.total_usd || 0],
      ['总Trial数', metrics.value.total_trials || 0],
      ['成功Trial数', metrics.value.completed_trials || 0],
      ['失败Trial数', metrics.value.failed_trials || 0],
    ]
    // Add score dimensions
    for (const [name, data] of Object.entries(scoreSummary.value || {})) {
      rows.push([`评分-${name}-平均`, pct((data as any).avg_score)])
      rows.push([`评分-${name}-通过率`, pct((data as any).pass_rate)])
    }

    const csv = rows.map(r => r.join(',')).join('\n')
    const blob = new Blob(['﻿' + csv], { type: 'text/csv;charset=utf-8' })
    downloadBlob(blob, `eval-report-${runId.value}.csv`)
    ElMessage.success('CSV 导出成功')
  } catch {
    ElMessage.error('导出失败')
  } finally {
    exporting.value = false
  }
}

const downloadBlob = (blob: Blob, filename: string) => {
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = filename
  document.body.appendChild(a)
  a.click()
  document.body.removeChild(a)
  URL.revokeObjectURL(url)
}

const pct = (v: number | undefined) => v !== undefined ? `${(v * 100).toFixed(1)}%` : '-'

const metricClass = (v: number | undefined, goodThreshold: number, warnThreshold: number) => {
  if (v === undefined) return ''
  if (v >= goodThreshold) return 'text-success'
  if (v < warnThreshold) return 'text-danger'
  return 'text-warning'
}

const getStatusType = (status: string): 'primary' | 'success' | 'warning' | 'info' | 'danger' => {
  const map: Record<string, 'primary' | 'success' | 'warning' | 'info' | 'danger'> = { pending: 'info', running: 'warning', completed: 'success', failed: 'danger', cancelled: 'info' }
  return map[status] || 'info'
}

const getStatusLabel = (status: string) => {
  const map: Record<string, string> = { pending: '等待中', running: '运行中', completed: '已完成', failed: '失败', cancelled: '已取消' }
  return map[status] || status
}

const formatTime = (isoString: string) => {
  if (!isoString) return '-'
  return new Date(isoString).toLocaleString('zh-CN')
}

onMounted(loadReport)
</script>

<style scoped>
.run-report-page { padding: 24px; }
.page-header { display: flex; justify-content: space-between; align-items: flex-start; margin-bottom: 24px; }
.page-title { font-size: 24px; font-weight: 600; display: flex; align-items: center; gap: 12px; margin: 8px 0 4px 0; }
.header-actions { display: flex; gap: 8px; }
.run-id { margin: 0; font-size: 13px; color: var(--el-text-color-secondary); font-family: monospace; }
.metric-item { text-align: center; padding: 8px 0; }
.metric-label { font-size: 12px; color: var(--el-text-color-secondary); margin-bottom: 4px; }
.metric-value { font-size: 20px; font-weight: 700; }
.text-success { color: var(--el-color-success); }
.text-danger { color: var(--el-color-danger); }
.text-warning { color: var(--el-color-warning); }
</style>
