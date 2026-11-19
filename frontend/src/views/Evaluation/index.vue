<template>
  <div class="evaluation-platform">
    <!-- 页面标题 -->
    <div class="page-header">
      <h1 class="page-title">
        <el-icon><DataAnalysis /></el-icon>
        Agent 评测平台
      </h1>
      <p class="page-description">
        Vibe Agent runtime 的评测集管理、批量运行、trace 回放和质量评分
      </p>
    </div>

    <!-- 功能导航卡片 -->
    <el-row :gutter="24" style="margin-top: 24px">
      <el-col :span="6">
        <el-card class="nav-card" shadow="hover" @click="$router.push('/evaluation/datasets')">
          <div class="nav-content">
            <el-icon class="nav-icon" size="40"><Collection /></el-icon>
            <h3>评测集管理</h3>
            <p>创建和管理评测数据集</p>
          </div>
        </el-card>
      </el-col>

      <el-col :span="6">
        <el-card class="nav-card" shadow="hover" @click="$router.push('/evaluation/runs')">
          <div class="nav-content">
            <el-icon class="nav-icon" size="40"><VideoPlay /></el-icon>
            <h3>评测运行</h3>
            <p>发起评测，查看运行状态</p>
          </div>
        </el-card>
      </el-col>

      <el-col :span="6">
        <el-card class="nav-card" shadow="hover" @click="$router.push('/evaluation/trends')">
          <div class="nav-content">
            <el-icon class="nav-icon" size="40"><TrendCharts /></el-icon>
            <h3>质量趋势</h3>
            <p>追踪指标变化，失败聚类分析</p>
          </div>
        </el-card>
      </el-col>

      <el-col :span="6">
        <el-card class="nav-card" shadow="hover" @click="$router.push('/evaluation/bad-cases')">
          <div class="nav-content">
            <el-icon class="nav-icon" size="40"><Warning /></el-icon>
            <h3>Bad Case 池</h3>
            <p>管理失败样本，回流为用例</p>
          </div>
        </el-card>
      </el-col>
    </el-row>

    <!-- 快速统计 -->
    <el-row :gutter="24" style="margin-top: 24px">
      <el-col :span="6">
        <el-card class="stat-card" shadow="never">
          <div class="stat-content">
            <div class="stat-value">{{ stats.datasetCount }}</div>
            <div class="stat-label">评测集数量</div>
          </div>
        </el-card>
      </el-col>
      <el-col :span="6">
        <el-card class="stat-card" shadow="never">
          <div class="stat-content">
            <div class="stat-value">{{ stats.runCount }}</div>
            <div class="stat-label">评测运行数</div>
          </div>
        </el-card>
      </el-col>
      <el-col :span="6">
        <el-card class="stat-card" shadow="never">
          <div class="stat-content">
            <div class="stat-value">{{ stats.trialCount }}</div>
            <div class="stat-label">Trial 总数</div>
          </div>
        </el-card>
      </el-col>
      <el-col :span="6">
        <el-card class="stat-card" shadow="never">
          <div class="stat-content">
            <div class="stat-value">{{ stats.badCaseCount }}</div>
            <div class="stat-label">Bad Case 数</div>
          </div>
        </el-card>
      </el-col>
    </el-row>

    <!-- 最近运行列表 -->
    <el-card style="margin-top: 24px" shadow="never">
      <template #header>
        <div class="card-header">
          <span>最近的评测运行</span>
          <el-button type="primary" link @click="$router.push('/evaluation/runs')">
            查看全部
          </el-button>
        </div>
      </template>

      <el-table :data="recentRuns" v-loading="loading" stripe>
        <el-table-column prop="run_id" label="运行 ID" width="180" />
        <el-table-column prop="dataset_id" label="数据集" width="150" />
        <el-table-column prop="status" label="状态" width="120">
          <template #default="{ row }">
            <el-tag :type="getStatusType(row.status)">
              {{ getStatusLabel(row.status) }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="completed_trials" label="完成 Trials" width="120" />
        <el-table-column prop="failed_trials" label="失败 Trials" width="120" />
        <el-table-column prop="created_at" label="创建时间" width="180">
          <template #default="{ row }">
            {{ formatTime(row.created_at) }}
          </template>
        </el-table-column>
        <el-table-column label="操作" fixed="right" width="120">
          <template #default="{ row }">
            <el-button type="primary" link size="small" @click="viewRunDetail(row.run_id)">
              详情
            </el-button>
          </template>
        </el-table-column>
      </el-table>
    </el-card>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import { DataAnalysis, Collection, VideoPlay, Warning, TrendCharts } from '@element-plus/icons-vue'
import { evalApiClient as axios } from '@/api/evalClient'

const router = useRouter()

// 统计数据
const stats = ref({
  datasetCount: 0,
  runCount: 0,
  trialCount: 0,
  badCaseCount: 0,
})

// 最近运行列表
const recentRuns = ref<any[]>([])
const loading = ref(false)

// 加载数据
const loadData = async () => {
  loading.value = true
  try {
    const [datasetsRes, runsRes, badCasesRes] = await Promise.all([
      axios.get('/api/eval/datasets'),
      axios.get('/api/eval/runs', { params: { limit: 10 } }),
      axios.get('/api/eval/bad-cases').catch(() => ({ data: { data: [] } })),
    ])

    const datasetsData = datasetsRes.data?.data || {}
    const runsData = runsRes.data?.data || {}
    const datasets = Array.isArray(datasetsData) ? datasetsData : (datasetsData.items || [])
    const runs = Array.isArray(runsData) ? runsData : (runsData.items || [])
    const badCases = badCasesRes.data?.data || []

    stats.value = {
      datasetCount: datasets.length,
      runCount: runs.length,
      trialCount: runs.reduce((sum: number, r: any) => sum + (r.completed_trials || 0) + (r.failed_trials || 0), 0),
      badCaseCount: Array.isArray(badCases) ? badCases.length : (badCases.items?.length || 0),
    }

    recentRuns.value = runs.slice(0, 10)
  } catch (error) {
    console.error('Failed to load evaluation dashboard:', error)
    ElMessage.error('加载数据失败')
  } finally {
    loading.value = false
  }
}

// 工具函数
const getStatusType = (status: string): 'primary' | 'success' | 'warning' | 'info' | 'danger' => {
  const map: Record<string, 'primary' | 'success' | 'warning' | 'info' | 'danger'> = {
    pending: 'info',
    running: 'warning',
    completed: 'success',
    failed: 'danger',
    cancelled: 'info',
  }
  return map[status] || 'info'
}

const getStatusLabel = (status: string) => {
  const map: Record<string, string> = {
    pending: '等待中',
    running: '运行中',
    completed: '已完成',
    failed: '失败',
    cancelled: '已取消',
  }
  return map[status] || status
}

const formatTime = (isoString: string) => {
  if (!isoString) return '-'
  return new Date(isoString).toLocaleString('zh-CN')
}

const viewRunDetail = (runId: string) => {
  router.push(`/evaluation/runs/${runId}`)
}

onMounted(() => {
  loadData()
})
</script>

<style scoped>
.evaluation-platform {
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

.nav-card {
  cursor: pointer;
  transition: all 0.3s ease;
  height: 200px;
}

.nav-card:hover {
  transform: translateY(-4px);
}

.nav-card-disabled {
  cursor: default;
  opacity: 0.6;
}

.nav-card-disabled:hover {
  transform: none;
}

.nav-content {
  text-align: center;
  padding: 24px;
}

.nav-icon {
  color: var(--el-color-primary);
  margin-bottom: 16px;
}

.nav-content h3 {
  margin: 0 0 8px 0;
  font-size: 18px;
  color: var(--el-text-color-primary);
}

.nav-content p {
  margin: 0;
  color: var(--el-text-color-secondary);
  font-size: 14px;
}

.stat-card {
  height: 120px;
}

.stat-content {
  display: flex;
  flex-direction: column;
  justify-content: center;
  align-items: center;
  height: 100%;
}

.stat-value {
  font-size: 32px;
  font-weight: 700;
  color: var(--el-color-primary);
}

.stat-label {
  font-size: 14px;
  color: var(--el-text-color-secondary);
  margin-top: 8px;
}

.card-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
}
</style>
