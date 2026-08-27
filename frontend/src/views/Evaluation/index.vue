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
      <el-col :span="8">
        <el-card class="nav-card" shadow="hover" @click="$router.push('/evaluation/datasets')">
          <div class="nav-content">
            <el-icon class="nav-icon" size="48"><Collection /></el-icon>
            <h3>评测集管理</h3>
            <p>创建和管理评测数据集，定义测试用例和评分标准</p>
          </div>
        </el-card>
      </el-col>

      <el-col :span="8">
        <el-card class="nav-card" shadow="hover" @click="$router.push('/evaluation/runs')">
          <div class="nav-content">
            <el-icon class="nav-icon" size="48"><VideoPlay /></el-icon>
            <h3>评测运行</h3>
            <p>发起评测运行，查看运行状态和进度</p>
          </div>
        </el-card>
      </el-col>

      <el-col :span="8">
        <el-card class="nav-card" shadow="hover" @click="$router.push('/evaluation/bad-cases')">
          <div class="nav-content">
            <el-icon class="nav-icon" size="48"><Warning /></el-icon>
            <h3>Bad Case 池</h3>
            <p>管理失败样本，回流为新的评测用例</p>
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
import { DataAnalysis, Collection, VideoPlay, Warning } from '@element-plus/icons-vue'
import axios from 'axios'

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
    // TODO: 调用实际的 API
    // const datasetsRes = await axios.get('/api/eval/datasets')
    // const runsRes = await axios.get('/api/eval/runs?limit=10')

    // 模拟数据
    stats.value = {
      datasetCount: 5,
      runCount: 12,
      trialCount: 156,
      badCaseCount: 8,
    }

    recentRuns.value = [
      {
        run_id: 'run_abc123',
        dataset_id: 'ds_golden_v1',
        status: 'completed',
        completed_trials: 30,
        failed_trials: 2,
        created_at: new Date().toISOString(),
      },
    ]
  } catch (error) {
    ElMessage.error('加载数据失败')
  } finally {
    loading.value = false
  }
}

// 工具函数
const getStatusType = (status: string) => {
  const map: Record<string, string> = {
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
