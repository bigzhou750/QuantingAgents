<template>
  <div class="runs-page">
    <div class="page-header">
      <h1 class="page-title">
        <el-icon><VideoPlay /></el-icon>
        评测运行
      </h1>
      <el-button type="primary" @click="$router.push('/evaluation/runs/create')">
        <el-icon><Plus /></el-icon>
        新建运行
      </el-button>
    </div>

    <!-- 筛选 -->
    <el-card shadow="never" style="margin-bottom: 24px">
      <el-form :inline="true">
        <el-form-item label="数据集">
          <el-select v-model="filterDataset" placeholder="全部数据集" clearable>
            <el-option v-for="ds in datasetOptions" :key="ds.value" :label="ds.label" :value="ds.value" />
          </el-select>
        </el-form-item>
        <el-form-item label="状态">
          <el-select v-model="filterStatus" placeholder="全部状态" clearable>
            <el-option label="全部" value="" />
            <el-option label="等待中" value="pending" />
            <el-option label="运行中" value="running" />
            <el-option label="已完成" value="completed" />
            <el-option label="失败" value="failed" />
            <el-option label="已取消" value="cancelled" />
          </el-select>
        </el-form-item>
        <el-form-item>
          <el-button type="primary" @click="loadRuns">查询</el-button>
        </el-form-item>
      </el-form>
    </el-card>

    <!-- 列表 -->
    <el-table :data="runs" v-loading="loading" stripe>
      <el-table-column prop="run_id" label="运行 ID" width="180" />
      <el-table-column prop="dataset_id" label="数据集" width="150" />
      <el-table-column prop="dataset_version" label="版本" width="100" />
      <el-table-column prop="status" label="状态" width="120">
        <template #default="{ row }">
          <el-tag :type="getStatusType(row.status)">{{ getStatusLabel(row.status) }}</el-tag>
        </template>
      </el-table-column>
      <el-table-column label="进度" width="150">
        <template #default="{ row }">
          <el-progress
            :percentage="calculateProgress(row)"
            :status="row.status === 'failed' ? 'exception' : undefined"
          />
        </template>
      </el-table-column>
      <el-table-column prop="num_trials_per_case" label="Trials/Case" width="120" />
      <el-table-column prop="created_at" label="创建时间" width="180">
        <template #default="{ row }">{{ formatTime(row.created_at) }}</template>
      </el-table-column>
      <el-table-column label="操作" fixed="right" width="150">
        <template #default="{ row }">
          <el-button type="primary" link size="small" @click="viewRun(row.run_id)">详情</el-button>
          <el-button
            v-if="row.status === 'running' || row.status === 'pending'"
            type="danger"
            link
            size="small"
            @click="cancelRun(row.run_id)"
          >
            取消
          </el-button>
        </template>
      </el-table-column>
    </el-table>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'
import { VideoPlay, Plus } from '@element-plus/icons-vue'

const router = useRouter()

const runs = ref<any[]>([])
const loading = ref(false)
const filterDataset = ref('')
const filterStatus = ref('')
const datasetOptions = ref([
  { label: 'Golden Set V1', value: 'ds_golden_v1' },
])

const loadRuns = async () => {
  loading.value = true
  try {
    // TODO: 调用实际 API
    // const res = await axios.get('/api/eval/runs', { params: { dataset_id: filterDataset.value } })
    // runs.value = res.data.data.items

    // 模拟数据
    runs.value = [
      {
        run_id: 'run_abc123',
        dataset_id: 'ds_golden_v1',
        dataset_version: '1.0.0',
        status: 'completed',
        total_cases: 30,
        completed_trials: 30,
        failed_trials: 2,
        num_trials_per_case: 1,
        created_at: new Date().toISOString(),
      },
    ]
  } catch (error) {
    ElMessage.error('加载失败')
  } finally {
    loading.value = false
  }
}

const cancelRun = async (runId: string) => {
  try {
    await ElMessageBox.confirm('确定要取消这个运行吗？', '确认取消', { type: 'warning' })
    // TODO: 调用实际 API
    // await axios.post(`/api/eval/runs/${runId}/cancel`)
    ElMessage.success('已取消')
    loadRuns()
  } catch {
    // 用户取消
  }
}

const viewRun = (runId: string) => {
  router.push(`/evaluation/runs/${runId}`)
}

const calculateProgress = (row: any) => {
  if (!row.total_cases || row.total_cases === 0) return 0
  const completed = (row.completed_trials || 0) + (row.failed_trials || 0)
  const total = row.total_cases * (row.num_trials_per_case || 1)
  return Math.round((completed / total) * 100)
}

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

onMounted(() => {
  loadRuns()
})
</script>

<style scoped>
.runs-page {
  padding: 24px;
}

.page-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 24px;
}

.page-title {
  font-size: 24px;
  font-weight: 600;
  display: flex;
  align-items: center;
  gap: 12px;
  margin: 0;
}
</style>
