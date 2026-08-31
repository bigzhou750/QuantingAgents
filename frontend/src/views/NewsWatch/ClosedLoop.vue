<template>
  <div class="closed-loop">
    <div style="margin-bottom: 12px;">
      <el-button link @click="$router.push('/news-watch/workbench')">← 回到工作台</el-button>
    </div>

    <!-- 闭环指标概览 -->
    <el-card>
      <template #header><span>📊 闭环指标概览</span></template>
      <el-row :gutter="16" v-loading="metricsLoading">
        <el-col :span="4" v-for="metric in metricCards" :key="metric.key">
          <el-statistic :title="metric.label" :value="metric.value" :suffix="metric.suffix" />
        </el-col>
      </el-row>
    </el-card>

    <!-- 告警管理 -->
    <el-card style="margin-top: 16px;">
      <template #header>
        <div class="card-header">
          <span>🔔 告警记录</span>
          <el-button size="small" @click="loadAlerts">刷新</el-button>
        </div>
      </template>
      <el-table :data="alerts" border stripe empty-text="暂无告警记录" v-loading="alertsLoading">
        <el-table-column prop="stock_code" label="代码" width="100" />
        <el-table-column prop="stock_name" label="名称" width="120" />
        <el-table-column label="影响等级" width="100">
          <template #default="{ row }">
            <el-tag :type="impactType(row.impact_level)" size="small">{{ row.impact_level }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column label="状态" width="100">
          <template #default="{ row }">
            <el-tag :type="alertStatusType(row.status)" size="small">{{ alertStatusLabel(row.status) }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="trigger_reason" label="触发原因" min-width="200" />
        <el-table-column label="操作" width="260" fixed="right">
          <template #default="{ row }">
            <template v-if="row.status === 'pending' || row.status === 'simulated'">
              <el-button size="small" type="success" @click="handleAlertAction(row, 'confirm')">确认</el-button>
              <el-button size="small" type="info" @click="handleAlertAction(row, 'ignore')">忽略</el-button>
              <el-button size="small" type="warning" @click="handleConvertToObservation(row)">转观察</el-button>
            </template>
            <span v-else class="muted">{{ alertStatusLabel(row.status) }}</span>
          </template>
        </el-table-column>
      </el-table>
    </el-card>

    <!-- 复盘汇总 -->
    <el-card style="margin-top: 16px;">
      <template #header><span>📝 复盘汇总</span></template>
      <div v-loading="reviewLoading">
        <el-descriptions :column="3" border v-if="reviewSummary">
          <el-descriptions-item label="总复盘数">{{ reviewSummary.total_reviews }}</el-descriptions-item>
          <el-descriptions-item label="已验证">{{ reviewSummary.verified_count }}</el-descriptions-item>
          <el-descriptions-item label="反向验证">{{ reviewSummary.contradicted_count }}</el-descriptions-item>
          <el-descriptions-item label="验证率">
            {{ ((reviewSummary.verification_rate || 0) * 100).toFixed(1) }}%
          </el-descriptions-item>
        </el-descriptions>
        <div v-if="reviewSummary?.recent?.length" style="margin-top: 12px;">
          <h4>最近复盘</h4>
          <el-timeline>
            <el-timeline-item
              v-for="(r, idx) in reviewSummary.recent"
              :key="idx"
              :timestamp="r.created_at"
              :type="verdictTimelineType(r.verdict)"
            >
              {{ r.stock_code }} — {{ r.predicted_direction }} → 实际 {{ r.actual_change_pct?.toFixed(2) }}%
              <el-tag :type="verdictTagType(r.verdict)" size="small">{{ verdictLabel(r.verdict) }}</el-tag>
            </el-timeline-item>
          </el-timeline>
        </div>
        <el-empty v-else description="暂无复盘记录" :image-size="60" />
      </div>
    </el-card>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import { ElMessage } from 'element-plus'
import { newsWatchApi } from '@/api/newsWatch'

// 指标
const metricsLoading = ref(false)
const metrics = ref<any>({})
const metricCards = computed(() => [
  { key: 'coverage', label: '新闻覆盖率', value: ((metrics.value.coverage_rate || 0) * 100).toFixed(1), suffix: '%' },
  { key: 'analysis', label: '分析成功率', value: ((metrics.value.analysis_success_rate || 0) * 100).toFixed(1), suffix: '%' },
  { key: 'alert_hit', label: '告警命中率', value: ((metrics.value.alert_hit_rate || 0) * 100).toFixed(1), suffix: '%' },
  { key: 'task', label: '任务完成率', value: ((metrics.value.task_completion_rate || 0) * 100).toFixed(1), suffix: '%' },
  { key: 'review', label: '复盘验证率', value: ((metrics.value.review_verification_rate || 0) * 100).toFixed(1), suffix: '%' },
  { key: 'noise', label: '噪声率', value: ((metrics.value.noise_rate || 0) * 100).toFixed(1), suffix: '%' },
])

// 告警
const alertsLoading = ref(false)
const alerts = ref<any[]>([])

// 复盘
const reviewLoading = ref(false)
const reviewSummary = ref<any>(null)

const loadMetrics = async () => {
  metricsLoading.value = true
  try {
    const res = await newsWatchApi.closedLoopMetrics()
    metrics.value = res.data || {}
  } catch { /* silent */ }
  finally { metricsLoading.value = false }
}

const loadAlerts = async () => {
  alertsLoading.value = true
  try {
    const res = await newsWatchApi.listAlerts({ limit: 50 })
    alerts.value = res.data?.records || []
  } catch { /* silent */ }
  finally { alertsLoading.value = false }
}

const loadReviewSummary = async () => {
  reviewLoading.value = true
  try {
    const res = await newsWatchApi.reviewSummary()
    reviewSummary.value = res.data
  } catch { /* silent */ }
  finally { reviewLoading.value = false }
}

const handleAlertAction = async (row: any, action: string) => {
  try {
    await newsWatchApi.updateAlertStatus(row._id, action)
    ElMessage.success(`已${alertStatusLabel(action)}`)
    await loadAlerts()
    await loadMetrics()
  } catch (e: any) {
    ElMessage.error(e.response?.data?.detail || '操作失败')
  }
}

const handleConvertToObservation = async (row: any) => {
  try {
    await newsWatchApi.createObservationFromNews({
      stock_code: row.stock_code,
      stock_name: row.stock_name,
      user_notes: `来自告警: ${row.trigger_reason}`,
    })
    await newsWatchApi.updateAlertStatus(row._id, 'convert', '已转为观察任务')
    ElMessage.success('已转为观察任务')
    await loadAlerts()
    await loadMetrics()
  } catch (e: any) {
    ElMessage.error(e.response?.data?.detail || '转换失败')
  }
}

// Labels
const impactType = (l: string) => ({ high: 'danger', medium: 'warning', low: 'info' }[l] || '')
const alertStatusLabel = (s: string) => ({ pending: '待处理', simulated: '待处理', confirmed: '已确认', ignored: '已忽略', converted: '已转观察', reviewed: '已复盘' }[s] || s)
const alertStatusType = (s: string): '' | 'success' | 'warning' | 'info' | 'danger' => ({ pending: 'warning', simulated: 'warning', confirmed: 'success', ignored: 'info', converted: '', reviewed: 'success' }[s] as any || '')
const verdictLabel = (v: string) => ({ verified: '已验证', unverified: '未验证', contradicted: '反向验证' }[v] || v)
const verdictTagType = (v: string): '' | 'success' | 'warning' | 'danger' => ({ verified: 'success', unverified: 'warning', contradicted: 'danger' }[v] as any || '')
const verdictTimelineType = (v: string): '' | 'success' | 'warning' | 'danger' => ({ verified: 'success', unverified: 'warning', contradicted: 'danger' }[v] as any || '')

onMounted(() => {
  loadMetrics()
  loadAlerts()
  loadReviewSummary()
})
</script>

<style scoped>
.closed-loop { padding: 20px; }
.card-header { display: flex; justify-content: space-between; align-items: center; }
.muted { color: #909399; font-size: 12px; }
</style>
