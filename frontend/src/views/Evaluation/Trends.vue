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
        <el-form-item>
          <el-button type="primary" @click="loadTrends" :loading="loading">
            刷新
          </el-button>
        </el-form-item>
      </el-form>
    </el-card>

    <!-- 趋势图表区域 -->
    <el-row :gutter="24">
      <el-col :span="12">
        <el-card shadow="never" style="margin-bottom: 24px">
          <template #header>成功率趋势</template>
          <div class="chart-placeholder">
            <div v-if="trendData.length === 0" class="empty-chart">暂无数据</div>
            <div v-else class="simple-chart">
              <div class="chart-bars">
                <div
                  v-for="(item, idx) in trendData"
                  :key="idx"
                  class="chart-bar-wrapper"
                  :title="`${formatTime(item.created_at)}: ${(item.success_rate * 100).toFixed(1)}%`"
                >
                  <div
                    class="chart-bar"
                    :style="{ height: `${item.success_rate * 100}%` }"
                    :class="getBarClass(item.success_rate)"
                  />
                  <span class="bar-label">{{ (item.success_rate * 100).toFixed(0) }}%</span>
                </div>
              </div>
              <div class="chart-axis">运行时间 →</div>
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
              <div v-for="(item, idx) in trendData.slice(-10)" :key="idx" class="score-row">
                <span class="run-label">#{{ idx + 1 }}</span>
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
            <div class="metric-value">{{ latestMetrics.totalCost }}</div>
            <div class="metric-label">总成本(USD)</div>
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

    <!-- 失败聚类分析 -->
    <el-card shadow="never">
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
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import { ElMessage } from 'element-plus'
import { TrendCharts } from '@element-plus/icons-vue'
import axios from 'axios'

// 筛选条件
const filters = ref({
  datasetId: '',
  limit: 20,
})

// 数据集列表
const datasets = ref<any[]>([])

// 趋势数据
const trendData = ref<any[]>([])
const failureClusters = ref<any[]>([])
const loading = ref(false)

// 最新指标计算
const latestMetrics = computed(() => {
  if (trendData.value.length === 0) {
    return {
      successRate: '-',
      avgLatency: '-',
      totalCost: '-',
      successTrend: 'flat',
      latencyTrend: 'flat',
    }
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
    avgLatency: latest.avg_latency_ms.toFixed(0),
    totalCost: `$${latest.total_cost_usd.toFixed(4)}`,
    successTrend,
    latencyTrend,
  }
})

// 加载数据集列表
const loadDatasets = async () => {
  try {
    const res = await axios.get('/api/eval/datasets')
    datasets.value = res.data?.data || []
  } catch (e) {
    // 静默处理
  }
}

// 加载趋势数据
const loadTrends = async () => {
  loading.value = true
  try {
    const params: any = { limit: filters.value.limit }
    if (filters.value.datasetId) {
      params.dataset_id = filters.value.datasetId
    }
    const res = await axios.get('/api/eval/trends', { params })
    const data = res.data?.data || {}
    trendData.value = data.trends || []
    failureClusters.value = data.failure_clusters || []
  } catch (e) {
    ElMessage.error('加载趋势数据失败')
  } finally {
    loading.value = false
  }
}

// 工具函数
const formatTime = (isoString: string) => {
  if (!isoString) return '-'
  return new Date(isoString).toLocaleString('zh-CN')
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
})
</script>

<style scoped>
.trends-page {
  padding: 24px;
}

.page-header {
  margin-bottom: 24px;
}

.page-title {
  font-size: 24px;
  font-weight: 600;
  color: var(--el-text-color-primary);
  display: flex;
  align-items: center;
  gap: 12px;
  margin: 0 0 8px 0;
}

.page-description {
  color: var(--el-text-color-secondary);
  margin: 0;
}

.chart-placeholder {
  min-height: 200px;
  display: flex;
  align-items: center;
  justify-content: center;
}

.empty-chart {
  color: var(--el-text-color-placeholder);
  font-size: 14px;
}

.simple-chart {
  width: 100%;
  padding: 16px;
}

.chart-bars {
  display: flex;
  align-items: flex-end;
  gap: 4px;
  height: 150px;
  padding-bottom: 8px;
  border-bottom: 1px solid var(--el-border-color-lighter);
}

.chart-bar-wrapper {
  flex: 1;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: flex-end;
  height: 100%;
}

.chart-bar {
  width: 100%;
  max-width: 24px;
  min-height: 2px;
  border-radius: 2px 2px 0 0;
  transition: height 0.3s ease;
}

.bar-success { background-color: var(--el-color-success); }
.bar-warning { background-color: var(--el-color-warning); }
.bar-danger { background-color: var(--el-color-danger); }

.bar-label {
  font-size: 10px;
  color: var(--el-text-color-secondary);
  margin-top: 4px;
}

.chart-axis {
  text-align: center;
  font-size: 12px;
  color: var(--el-text-color-secondary);
  margin-top: 8px;
}

.score-trends {
  width: 100%;
  padding: 8px;
}

.score-row {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 6px 0;
  border-bottom: 1px dashed var(--el-border-color-extra-light);
}

.run-label {
  font-size: 12px;
  color: var(--el-text-color-secondary);
  width: 30px;
}

.score-badges {
  display: flex;
  flex-wrap: wrap;
  gap: 4px;
}

.metric-card {
  text-align: center;
  padding: 12px;
}

.metric-value {
  font-size: 28px;
  font-weight: 700;
  color: var(--el-color-primary);
}

.metric-label {
  font-size: 14px;
  color: var(--el-text-color-secondary);
  margin-top: 4px;
}

.metric-trend {
  font-size: 18px;
  margin-top: 4px;
}

.metric-trend.up { color: var(--el-color-success); }
.metric-trend.down { color: var(--el-color-danger); }
.metric-trend.flat { color: var(--el-text-color-secondary); }

.card-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
}
</style>
