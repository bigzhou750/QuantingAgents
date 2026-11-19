<template>
  <div class="trends-page">
    <div class="page-header">
      <h1 class="page-title">
        <el-icon><TrendCharts /></el-icon>
        质量趋势
      </h1>
      <p class="page-description">
        追踪评测指标随时间的变化趋势，识别失败模式聚类
      </p>
    </div>

    <!-- 筛选条件 -->
    <el-card shadow="never" style="margin-bottom: 24px">
      <el-form :inline="true">
        <el-form-item label="数据集">
          <el-select v-model="filters.datasetId" placeholder="全部数据集" clearable style="width: 200px">
            <el-option
              v-for="ds in datasets"
              :key="ds.dataset_id"
              :label="ds.name"
              :value="ds.dataset_id"
            />
          </el-select>
        </el-form-item>
        <el-form-item label="最近运行数">
          <el-select v-model="filters.limit" style="width: 120px">
            <el-option :value="10" label="10 次" />
            <el-option :value="20" label="20 次" />
            <el-option :value="50" label="50 次" />
          </el-select>
        </el-form-item>
        <el-form-item label="稳定性指标">
          <el-radio-group v-model="stabilityMetric" size="small">
            <el-radio-button value="pass_at_k">pass@k</el-radio-button>
            <el-radio-button value="pass_pow_k">pass^k</el-radio-button>
          </el-radio-group>
        </el-form-item>
        <el-form-item>
          <el-button type="primary" @click="loadTrends" :loading="loading">刷新</el-button>
        </el-form-item>
      </el-form>
    </el-card>

    <!-- 口径说明 (6.1) -->
    <el-alert
      type="info"
      :closable="false"
      show-icon
      style="margin-bottom: 24px"
    >
      <template #title>指标口径说明</template>
      <div style="font-size: 13px; line-height: 1.8">
        <strong>成功率</strong> = completed_trials / (completed + failed)；
        <strong>pass@k</strong> = k 次 trial 中至少 1 次通过的概率（衡量最好表现）；
        <strong>pass^k</strong> = k 次 trial 全部通过的概率（衡量稳定性）；
        <strong>阈值线</strong>：绿色虚线 = 发布门禁阈值，红色虚线 = 告警阈值。
        当前 k={{ currentK }}。
      </div>
    </el-alert>

    <!-- 趋势图表区域 -->
    <el-row :gutter="24">
      <el-col :span="12">
        <el-card shadow="never" style="margin-bottom: 24px">
          <template #header>
            <div class="card-header">
              <span>成功率 & 稳定性趋势</span>
              <div class="chart-legend">
                <span class="legend-item"><span class="legend-dot bar-success"></span>成功率</span>
                <span class="legend-item"><span class="legend-dot bar-primary"></span>{{ stabilityLabel }}</span>
                <span class="legend-item legend-line release-gate-line">发布门禁</span>
                <span class="legend-item legend-line alert-line">告警阈值</span>
              </div>
            </div>
          </template>
          <div class="chart-placeholder">
            <div v-if="trendData.length === 0" class="empty-chart">暂无数据</div>
            <div v-else class="simple-chart">
              <div class="chart-bars">
                <!-- 阈值参考线 -->
                <div class="threshold-line release-gate" :style="{ bottom: `${releaseGateThreshold * 100}%` }" title="发布门禁阈值" />
                <div class="threshold-line alert" :style="{ bottom: `${alertThreshold * 100}%` }" title="告警阈值" />

                <div
                  v-for="(item, idx) in trendData"
                  :key="idx"
                  class="chart-bar-wrapper"
                  :title="tooltipText(item)"
                  @click="drillDown(item)"
                  style="cursor: pointer"
                >
                  <div class="dual-bar">
                    <div
                      class="chart-bar bar-left"
                      :style="{ height: `${item.success_rate * 100}%` }"
                      :class="getBarClass(item.success_rate)"
                    />
                    <div
                      class="chart-bar bar-right"
                      :style="{ height: `${getStabilityValue(item) * 100}%` }"
                      :class="'bar-primary'"
                    />
                  </div>
                  <span class="bar-label">{{ (item.success_rate * 100).toFixed(0) }}%</span>
                </div>
              </div>
              <div class="chart-axis">运行时间 → （点击柱体可下钻到运行详情）</div>
            </div>
          </div>
        </el-card>
      </el-col>

      <el-col :span="12">
        <el-card shadow="never" style="margin-bottom: 24px">
          <template #header>评分维度趋势</template>
          <div class="chart-placeholder">
            <div v-if="trendData.length === 0" class="empty-chart">暂无数据</div>
            <div v-else class="score-trends">
              <div v-for="(item, idx) in trendData.slice(-10)" :key="idx" class="score-row" @click="drillDown(item)" style="cursor: pointer">
                <span class="run-label">#{{ trendData.length - 10 + idx + 1 }}</span>
                <span class="run-time">{{ formatTimeShort(item.created_at) }}</span>
                <div class="score-badges">
                  <el-tag
                    v-for="(score, name) in item.score_summary"
                    :key="name"
                    size="small"
                    :type="getScoreType(score)"
                  >
                    {{ name }}: {{ (score * 100).toFixed(0) }}
                  </el-tag>
                </div>
              </div>
            </div>
          </div>
        </el-card>
      </el-col>
    </el-row>

    <!-- 关键指标卡片 -->
    <el-row :gutter="24" style="margin-bottom: 24px">
      <el-col :span="6">
        <el-card shadow="never">
          <div class="metric-card">
            <div class="metric-value">{{ latestMetrics.successRate }}</div>
            <div class="metric-label">最新成功率</div>
            <div class="metric-trend" :class="latestMetrics.successTrend">
              {{ latestMetrics.successTrend === 'up' ? '↑' : latestMetrics.successTrend === 'down' ? '↓' : '→' }}
            </div>
          </div>
        </el-card>
      </el-col>
      <el-col :span="6">
        <el-card shadow="never">
          <div class="metric-card">
            <div class="metric-value">{{ latestMetrics.stabilityValue }}</div>
            <div class="metric-label">{{ stabilityLabel }}</div>
          </div>
        </el-card>
      </el-col>
      <el-col :span="6">
        <el-card shadow="never">
          <div class="metric-card">
            <div class="metric-value">{{ latestMetrics.avgLatency }}</div>
            <div class="metric-label">平均延迟(ms)</div>
            <div class="metric-trend" :class="latestMetrics.latencyTrend">
              {{ latestMetrics.latencyTrend === 'up' ? '↑' : latestMetrics.latencyTrend === 'down' ? '↓' : '→' }}
            </div>
          </div>
        </el-card>
      </el-col>
      <el-col :span="6">
        <el-card shadow="never">
          <div class="metric-card">
            <div class="metric-value">{{ failureClusters.length }}</div>
            <div class="metric-label">失败模式数</div>
          </div>
        </el-card>
      </el-col>
    </el-row>

    <!-- 失败聚类分析 (6.2) -->
    <el-card shadow="never" style="margin-bottom: 24px">
      <template #header>
        <div class="card-header">
          <span>失败模式聚类</span>
          <el-tag type="info">{{ failureClusters.length }} 种模式</el-tag>
        </div>
      </template>

      <el-table :data="failureClusters" stripe v-loading="loading">
        <el-table-column prop="pattern" label="错误模式" min-width="300" show-overflow-tooltip />
        <el-table-column prop="count" label="出现次数" width="120" sortable />
        <el-table-column label="示例运行" width="280">
          <template #default="{ row }">
            <el-tag
              v-for="runId in row.sample_run_ids"
              :key="runId"
              size="small"
              type="info"
              style="margin-right: 4px; cursor: pointer"
              @click="$router.push(`/evaluation/runs/${runId}`)"
            >
              {{ runId.substring(0, 12) }}
            </el-tag>
          </template>
        </el-table-column>
      </el-table>
    </el-card>

    <!-- 按评分维度/来源聚类 (6.2) -->
    <el-row :gutter="24" style="margin-bottom: 24px">
      <el-col :span="12">
        <el-card shadow="never">
          <template #header><span>失败按评分维度分布</span></template>
          <el-table v-if="failureByScorer.length" :data="failureByScorer" stripe size="small">
            <el-table-column prop="scorer" label="评分器" width="160" />
            <el-table-column prop="count" label="低分次数" width="100" sortable />
            <el-table-column label="示例 Trial" min-width="200">
              <template #default="{ row }">
                <el-tag v-for="tid in row.sample_trial_ids" :key="tid" size="small" type="info" style="margin-right: 4px">{{ tid.substring(0, 16) }}</el-tag>
              </template>
            </el-table-column>
          </el-table>
          <div v-else style="text-align: center; padding: 24px; color: var(--el-text-color-secondary)">暂无数据</div>
        </el-card>
      </el-col>
      <el-col :span="12">
        <el-card shadow="never">
          <template #header><span>失败按来源分布</span></template>
          <el-table v-if="failureBySource.length" :data="failureBySource" stripe size="small">
            <el-table-column prop="source" label="来源" width="140" />
            <el-table-column prop="count" label="低分次数" width="100" sortable />
            <el-table-column label="示例 Trial" min-width="200">
              <template #default="{ row }">
                <el-tag v-for="tid in row.sample_trial_ids" :key="tid" size="small" type="info" style="margin-right: 4px">{{ tid.substring(0, 16) }}</el-tag>
              </template>
            </el-table-column>
          </el-table>
          <div v-else style="text-align: center; padding: 24px; color: var(--el-text-color-secondary)">暂无数据</div>
        </el-card>
      </el-col>
    </el-row>

    <!-- Release Gate 配置 (6.3) -->
    <el-card shadow="never" style="margin-bottom: 24px">
      <template #header>
        <div class="card-header">
          <span>Release Gate 配置</span>
          <el-switch v-model="releaseGateConfig.enabled" active-text="已启用" inactive-text="未启用" @change="saveReleaseGateConfig" />
        </div>
      </template>
      <el-form :model="releaseGateConfig" label-width="160px" size="small" :disabled="!releaseGateConfig.enabled">
        <el-row :gutter="24">
          <el-col :span="8">
            <el-form-item label="最低成功率">
              <el-slider v-model="releaseGateConfig.min_success_rate" :min="0" :max="1" :step="0.05" show-input />
            </el-form-item>
          </el-col>
          <el-col :span="8">
            <el-form-item label="最低 pass@3">
              <el-slider v-model="releaseGateConfig.min_pass_at_3" :min="0" :max="1" :step="0.05" show-input />
            </el-form-item>
          </el-col>
          <el-col :span="8">
            <el-form-item label="最大失败率">
              <el-slider v-model="releaseGateConfig.max_failure_rate" :min="0" :max="1" :step="0.05" show-input />
            </el-form-item>
          </el-col>
        </el-row>
        <el-form-item label="安全评分阻断">
          <el-switch v-model="releaseGateConfig.block_on_safety_failure" />
        </el-form-item>
        <el-form-item label="必须通过的评分器">
          <el-select v-model="releaseGateConfig.required_scorers" multiple placeholder="选择评分器" style="width: 100%">
            <el-option v-for="s in availableScorers" :key="s.name" :label="`${s.name} (${s.source})`" :value="s.name" />
          </el-select>
        </el-form-item>
        <el-form-item>
          <el-button type="primary" @click="saveReleaseGateConfig" :loading="savingConfig">保存配置</el-button>
        </el-form-item>
      </el-form>
    </el-card>

    <!-- 告警检查 (6.6) -->
    <el-card shadow="never">
      <template #header>
        <div class="card-header">
          <span>告警状态</span>
          <el-button size="small" @click="checkAlerts" :loading="checkingAlerts">检查告警</el-button>
        </div>
      </template>
      <div v-if="alerts.length === 0 && !checkingAlerts" style="text-align: center; padding: 24px; color: var(--el-text-color-secondary)">
        ✅ 无告警触发
      </div>
      <el-table v-else :data="alerts" stripe>
        <el-table-column prop="severity" label="级别" width="100">
          <template #default="{ row }">
            <el-tag :type="row.severity === 'critical' ? 'danger' : 'warning'" size="small">{{ row.severity }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="message" label="告警信息" min-width="300" />
        <el-table-column prop="current_value" label="当前值" width="100">
          <template #default="{ row }">{{ typeof row.current_value === 'number' ? (row.current_value * 100).toFixed(1) + '%' : row.current_value }}</template>
        </el-table-column>
        <el-table-column prop="threshold" label="阈值" width="100">
          <template #default="{ row }">{{ typeof row.threshold === 'number' ? (row.threshold * 100).toFixed(1) + '%' : row.threshold }}</template>
        </el-table-column>
      </el-table>
    </el-card>

    <!-- 定时回归任务 (6.4) -->
    <el-row :gutter="24" style="margin-top: 24px">
      <el-col :span="12">
        <el-card shadow="never">
          <template #header><span>定时回归任务</span></template>
          <el-form :inline="true" size="small" style="margin-bottom: 12px">
            <el-input v-model="regressionForm.name" placeholder="任务名称" style="width: 150px" />
            <el-select v-model="regressionForm.dataset_id" placeholder="数据集" style="width: 150px">
              <el-option v-for="ds in datasets" :key="ds.dataset_id" :label="ds.name" :value="ds.dataset_id" />
            </el-select>
            <el-input v-model="regressionForm.schedule_cron" placeholder="Cron（可选）" style="width: 150px" />
            <el-button type="primary" :loading="regressionSaving" @click="createRegressionTask">创建</el-button>
          </el-form>
          <el-table :data="regressionTasks" size="small" stripe empty-text="暂无回归任务">
            <el-table-column prop="name" label="名称" min-width="130" />
            <el-table-column prop="schedule_cron" label="Cron" width="120" />
            <el-table-column label="状态" width="90">
              <template #default="{ row }">
                <el-switch :model-value="row.enabled" @change="toggleRegressionTask(row)" />
              </template>
            </el-table-column>
            <el-table-column label="操作" width="90">
              <template #default="{ row }">
                <el-button link type="primary" size="small" @click="triggerRegressionTask(row)">立即运行</el-button>
              </template>
            </el-table-column>
          </el-table>
        </el-card>
      </el-col>

      <!-- 成本预算、告警和第三方观测配置 (6.6) -->
      <el-col :span="12">
        <el-card shadow="never">
          <template #header><span>成本预算与观测配置</span></template>
          <el-form :model="governanceConfig" label-width="120px" size="small">
            <el-form-item label="每日成本预算">
              <el-input-number v-model="governanceConfig.daily_cost_budget_usd" :min="0" :precision="4" />
            </el-form-item>
            <el-form-item label="告警订阅">
              <el-switch v-model="governanceConfig.alert_enabled" />
            </el-form-item>
            <el-form-item label="告警 Webhook">
              <el-input v-model="governanceConfig.alert_webhook" placeholder="可选" />
            </el-form-item>
            <el-form-item label="观测后端">
              <el-select v-model="governanceConfig.observability_backend" style="width: 160px">
                <el-option label="关闭" value="none" />
                <el-option label="Langfuse" value="langfuse" />
                <el-option label="Phoenix" value="phoenix" />
              </el-select>
            </el-form-item>
            <el-form-item label="观测地址">
              <el-input v-model="governanceConfig.observability_host" placeholder="可选" />
            </el-form-item>
            <el-form-item label="项目名">
              <el-input v-model="governanceConfig.observability_project" />
            </el-form-item>
            <el-form-item label="API Key">
              <el-input v-model="governanceConfig.observability_api_key" type="password" show-password />
            </el-form-item>
            <el-form-item>
              <el-button type="primary" :loading="savingGovernance" @click="saveGovernanceConfig">保存配置</el-button>
            </el-form-item>
          </el-form>
        </el-card>
      </el-col>
    </el-row>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import { TrendCharts } from '@element-plus/icons-vue'
import { evalApiClient as axios } from '@/api/evalClient'

const router = useRouter()

// 筛选条件
const filters = ref({ datasetId: '', limit: 20 })
const stabilityMetric = ref('pass_at_k')
const datasets = ref<any[]>([])
const trendData = ref<any[]>([])
const failureClusters = ref<any[]>([])
const failureByScorer = ref<any[]>([])
const failureBySource = ref<any[]>([])
const loading = ref(false)

// Release Gate (6.3)
const releaseGateConfig = ref({
  enabled: false,
  min_success_rate: 0.9,
  min_pass_at_3: 0.8,
  max_failure_rate: 0.1,
  required_scorers: ['rule_based', 'safety'] as string[],
  block_on_safety_failure: true,
})
const savingConfig = ref(false)
const availableScorers = ref<any[]>([])

// Alerts (6.6)
const alerts = ref<any[]>([])
const checkingAlerts = ref(false)

const regressionTasks = ref<any[]>([])
const regressionSaving = ref(false)
const regressionForm = ref({
  name: '',
  dataset_id: '',
  schedule_cron: '',
  num_trials_per_case: 1,
  scorer_names: [] as string[],
})

const savingGovernance = ref(false)
const governanceConfig = ref({
  daily_cost_budget_usd: 0,
  alert_enabled: true,
  alert_webhook: '',
  observability_backend: 'none',
  observability_api_key: '',
  observability_host: '',
  observability_project: 'quantingagents-eval',
})

// 阈值常量
const releaseGateThreshold = computed(() => releaseGateConfig.value.enabled ? releaseGateConfig.value.min_success_rate : 0.9)
const alertThreshold = 0.7

const stabilityLabel = computed(() => stabilityMetric.value === 'pass_at_k' ? 'pass@k' : 'pass^k')
const currentK = computed(() => trendData.value.length > 0 ? (trendData.value[0].pass_k || 3) : 3)

const getStabilityValue = (item: any) => {
  return stabilityMetric.value === 'pass_at_k' ? (item.pass_at_k || 0) : (item.pass_pow_k || 0)
}

// 最新指标计算
const latestMetrics = computed(() => {
  if (trendData.value.length === 0) {
    return { successRate: '-', avgLatency: '-', totalCost: '-', successTrend: 'flat', latencyTrend: 'flat', stabilityValue: '-' }
  }
  const latest = trendData.value[trendData.value.length - 1]
  const prev = trendData.value.length > 1 ? trendData.value[trendData.value.length - 2] : null

  const successTrend = prev
    ? latest.success_rate > prev.success_rate ? 'up' : latest.success_rate < prev.success_rate ? 'down' : 'flat'
    : 'flat'
  const latencyTrend = prev
    ? latest.avg_latency_ms < prev.avg_latency_ms ? 'down' : latest.avg_latency_ms > prev.avg_latency_ms ? 'up' : 'flat'
    : 'flat'

  return {
    successRate: `${(latest.success_rate * 100).toFixed(1)}%`,
    avgLatency: latest.avg_latency_ms?.toFixed(0) || '-',
    totalCost: `$${(latest.total_cost_usd || 0).toFixed(4)}`,
    successTrend,
    latencyTrend,
    stabilityValue: `${(getStabilityValue(latest) * 100).toFixed(1)}%`,
  }
})

// 趋势点下钻 (6.1)
const drillDown = (item: any) => {
  if (item.run_id) {
    router.push(`/evaluation/runs/${item.run_id}`)
  }
}

const tooltipText = (item: any) => {
  const time = formatTime(item.created_at)
  const sr = (item.success_rate * 100).toFixed(1)
  const pak = (item.pass_at_k * 100).toFixed(1)
  const ppk = (item.pass_pow_k * 100).toFixed(1)
  return `${time}\n成功率: ${sr}%\npass@k: ${pak}%\npass^k: ${ppk}%\n点击查看详情`
}

const loadDatasets = async () => {
  try {
    const res = await axios.get('/api/eval/datasets')
    const data = res.data?.data || {}
    datasets.value = Array.isArray(data) ? data : (data.items || [])
  } catch { /* ignore */ }
}

const loadTrends = async () => {
  loading.value = true
  try {
    const params: any = { limit: filters.value.limit }
    if (filters.value.datasetId) params.dataset_id = filters.value.datasetId
    const res = await axios.get('/api/eval/trends', { params })
    const data = res.data?.data || {}
    trendData.value = data.trends || []
    failureClusters.value = data.failure_clusters || []
    failureByScorer.value = data.failure_by_scorer || []
    failureBySource.value = data.failure_by_source || []
  } catch {
    ElMessage.error('加载趋势数据失败')
  } finally {
    loading.value = false
  }
}

const loadReleaseGateConfig = async () => {
  try {
    const res = await axios.get('/api/eval/release-gate/config')
    const cfg = res.data?.data || {}
    releaseGateConfig.value = { ...releaseGateConfig.value, ...cfg }
  } catch { /* use defaults */ }
}

const saveReleaseGateConfig = async () => {
  savingConfig.value = true
  try {
    await axios.put('/api/eval/release-gate/config', releaseGateConfig.value)
    ElMessage.success('Release Gate 配置已保存')
  } catch {
    ElMessage.error('保存失败')
  } finally {
    savingConfig.value = false
  }
}

const checkAlerts = async () => {
  checkingAlerts.value = true
  try {
    const params: any = {}
    if (filters.value.datasetId) params.dataset_id = filters.value.datasetId
    const res = await axios.get('/api/eval/alerts/check', { params })
    alerts.value = res.data?.data?.alerts || []
    if (alerts.value.length === 0) {
      ElMessage.success('无告警触发')
    } else {
      ElMessage.warning(`发现 ${alerts.value.length} 条告警`)
    }
  } catch {
    ElMessage.error('告警检查失败')
  } finally {
    checkingAlerts.value = false
  }
}

const loadScorers = async () => {
  try {
    const res = await axios.get('/api/eval/scorers')
    availableScorers.value = res.data?.data || []
  } catch { /* ignore */ }
}

const loadRegressionTasks = async () => {
  try {
    const res = await axios.get('/api/eval/regression-tasks')
    regressionTasks.value = res.data?.data?.items || []
  } catch { /* ignore */ }
}

const createRegressionTask = async () => {
  if (!regressionForm.value.name || !regressionForm.value.dataset_id) {
    ElMessage.warning('请输入任务名称并选择数据集')
    return
  }
  regressionSaving.value = true
  try {
    await axios.post('/api/eval/regression-tasks', regressionForm.value)
    ElMessage.success('回归任务已创建，默认禁用')
    regressionForm.value.name = ''
    regressionForm.value.schedule_cron = ''
    await loadRegressionTasks()
  } catch {
    ElMessage.error('创建回归任务失败')
  } finally {
    regressionSaving.value = false
  }
}

const toggleRegressionTask = async (row: any) => {
  try {
    await axios.put(`/api/eval/regression-tasks/${row.task_id}/toggle`, undefined, {
      params: { enabled: !row.enabled },
    })
    await loadRegressionTasks()
  } catch {
    ElMessage.error('更新回归任务状态失败')
  }
}

const triggerRegressionTask = async (row: any) => {
  try {
    await axios.post(`/api/eval/regression-tasks/${row.task_id}/trigger`)
    ElMessage.success('回归运行已触发')
    await loadRegressionTasks()
  } catch {
    ElMessage.error('触发回归运行失败')
  }
}

const loadGovernanceConfig = async () => {
  try {
    const res = await axios.get('/api/eval/governance/config')
    governanceConfig.value = { ...governanceConfig.value, ...(res.data?.data || {}) }
  } catch { /* use defaults */ }
}

const saveGovernanceConfig = async () => {
  savingGovernance.value = true
  try {
    await axios.put('/api/eval/governance/config', governanceConfig.value)
    ElMessage.success('评测治理配置已保存')
  } catch {
    ElMessage.error('保存评测治理配置失败')
  } finally {
    savingGovernance.value = false
  }
}

const formatTime = (isoString: string) => {
  if (!isoString) return '-'
  return new Date(isoString).toLocaleString('zh-CN')
}

const formatTimeShort = (isoString: string) => {
  if (!isoString) return ''
  const d = new Date(isoString)
  return `${d.getMonth() + 1}/${d.getDate()} ${d.getHours()}:${String(d.getMinutes()).padStart(2, '0')}`
}

const getBarClass = (rate: number) => {
  if (rate >= 0.9) return 'bar-success'
  if (rate >= 0.7) return 'bar-warning'
  return 'bar-danger'
}

const getScoreType = (score: number) => {
  if (score >= 0.8) return 'success'
  if (score >= 0.6) return 'warning'
  return 'danger'
}

onMounted(() => {
  loadDatasets()
  loadTrends()
  loadReleaseGateConfig()
  loadScorers()
  checkAlerts()
  loadRegressionTasks()
  loadGovernanceConfig()
})
</script>

<style scoped>
.trends-page { padding: 24px; }
.page-header { margin-bottom: 24px; }
.page-title { font-size: 24px; font-weight: 600; display: flex; align-items: center; gap: 12px; margin: 0 0 8px 0; }
.page-description { color: var(--el-text-color-secondary); margin: 0; }

.card-header { display: flex; justify-content: space-between; align-items: center; }

.chart-legend { display: flex; gap: 16px; font-size: 12px; align-items: center; }
.legend-item { display: flex; align-items: center; gap: 4px; }
.legend-dot { width: 10px; height: 10px; border-radius: 2px; display: inline-block; }
.legend-line { position: relative; padding-left: 16px; }
.legend-line::before { content: ''; position: absolute; left: 0; top: 50%; width: 12px; height: 0; border-top: 2px dashed; transform: translateY(-50%); }
.release-gate-line::before { border-color: var(--el-color-success); }
.alert-line::before { border-color: var(--el-color-danger); }

.chart-placeholder { min-height: 200px; display: flex; align-items: center; justify-content: center; }
.empty-chart { color: var(--el-text-color-placeholder); font-size: 14px; }
.simple-chart { width: 100%; padding: 16px; }

.chart-bars {
  display: flex; align-items: flex-end; gap: 4px; height: 180px;
  padding-bottom: 8px; border-bottom: 1px solid var(--el-border-color-lighter);
  position: relative;
}

.threshold-line {
  position: absolute; left: 0; right: 0; height: 0;
  border-top: 2px dashed; z-index: 1; pointer-events: none;
}
.threshold-line.release-gate { border-color: var(--el-color-success); opacity: 0.6; }
.threshold-line.alert { border-color: var(--el-color-danger); opacity: 0.6; }

.chart-bar-wrapper {
  flex: 1; display: flex; flex-direction: column;
  align-items: center; justify-content: flex-end; height: 100%; z-index: 2;
}

.dual-bar { display: flex; gap: 1px; align-items: flex-end; width: 100%; justify-content: center; height: 100%; }

.chart-bar {
  width: 45%; max-width: 14px; min-height: 2px;
  border-radius: 2px 2px 0 0; transition: height 0.3s ease;
}

.bar-success { background-color: var(--el-color-success); }
.bar-warning { background-color: var(--el-color-warning); }
.bar-danger { background-color: var(--el-color-danger); }
.bar-primary { background-color: var(--el-color-primary); }

.bar-label { font-size: 10px; color: var(--el-text-color-secondary); margin-top: 4px; }
.chart-axis { text-align: center; font-size: 12px; color: var(--el-text-color-secondary); margin-top: 8px; }

.score-trends { width: 100%; padding: 8px; }
.score-row {
  display: flex; align-items: center; gap: 12px; padding: 6px 0;
  border-bottom: 1px dashed var(--el-border-color-extra-light);
}
.score-row:hover { background: var(--el-fill-color-lighter); border-radius: 4px; }
.run-label { font-size: 12px; color: var(--el-text-color-secondary); width: 30px; }
.run-time { font-size: 11px; color: var(--el-text-color-placeholder); width: 80px; }
.score-badges { display: flex; flex-wrap: wrap; gap: 4px; }

.metric-card { text-align: center; padding: 12px; }
.metric-value { font-size: 28px; font-weight: 700; color: var(--el-color-primary); }
.metric-label { font-size: 14px; color: var(--el-text-color-secondary); margin-top: 4px; }
.metric-trend { font-size: 18px; margin-top: 4px; }
.metric-trend.up { color: var(--el-color-success); }
.metric-trend.down { color: var(--el-color-danger); }
.metric-trend.flat { color: var(--el-text-color-secondary); }
</style>
