<template>
  <div class="datasets-page">
    <div class="page-header">
      <h1 class="page-title">
        <el-icon><Collection /></el-icon>
        评测集管理
      </h1>
      <el-button type="primary" @click="showCreateDialog = true">
        <el-icon><Plus /></el-icon>
        创建评测集
      </el-button>
    </div>

    <!-- 筛选 -->
    <el-card shadow="never" style="margin-bottom: 24px">
      <el-form :inline="true">
        <el-form-item label="标签">
          <el-select v-model="filterTags" multiple collapse-tags placeholder="选择标签" clearable>
            <el-option label="golden" value="golden" />
            <el-option label="regression" value="regression" />
            <el-option label="security" value="security" />
          </el-select>
        </el-form-item>
        <el-form-item label="状态">
          <el-select v-model="filterStatus" placeholder="全部状态" clearable>
            <el-option label="全部" value="" />
            <el-option label="草稿" value="draft" />
            <el-option label="活跃" value="active" />
            <el-option label="已归档" value="archived" />
          </el-select>
        </el-form-item>
        <el-form-item>
          <el-button type="primary" @click="loadDatasets">查询</el-button>
        </el-form-item>
      </el-form>
    </el-card>

    <!-- 列表 -->
    <el-table :data="datasets" v-loading="loading" stripe>
      <el-table-column prop="dataset_id" label="数据集 ID" width="180" />
      <el-table-column prop="name" label="名称" min-width="150" />
      <el-table-column prop="version" label="版本" width="100" />
      <el-table-column prop="status" label="状态" width="100">
        <template #default="{ row }">
          <el-tag :type="getStatusType(row.status)">{{ row.status }}</el-tag>
        </template>
      </el-table-column>
      <el-table-column prop="cases.length" label="用例数" width="100" />
      <el-table-column prop="created_at" label="创建时间" width="180">
        <template #default="{ row }">{{ formatTime(row.created_at) }}</template>
      </el-table-column>
      <el-table-column label="操作" fixed="right" width="200">
        <template #default="{ row }">
          <el-button type="primary" link size="small" @click="viewDataset(row.dataset_id)">查看</el-button>
          <el-button type="primary" link size="small" @click="runEvaluation(row.dataset_id)">运行评测</el-button>
        </template>
      </el-table-column>
    </el-table>

    <!-- 创建对话框 -->
    <el-dialog v-model="showCreateDialog" title="创建评测集" width="500px">
      <el-form :model="createForm" label-width="100px">
        <el-form-item label="名称" required>
          <el-input v-model="createForm.name" placeholder="输入评测集名称" />
        </el-form-item>
        <el-form-item label="描述">
          <el-input v-model="createForm.description" type="textarea" :rows="3" placeholder="输入描述" />
        </el-form-item>
        <el-form-item label="标签">
          <el-select v-model="createForm.tags" multiple placeholder="选择标签">
            <el-option label="golden" value="golden" />
            <el-option label="regression" value="regression" />
            <el-option label="security" value="security" />
          </el-select>
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="showCreateDialog = false">取消</el-button>
        <el-button type="primary" @click="createDataset" :loading="creating">创建</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import { Collection, Plus } from '@element-plus/icons-vue'

const router = useRouter()

const datasets = ref<any[]>([])
const loading = ref(false)
const filterTags = ref<string[]>([])
const filterStatus = ref('')

const showCreateDialog = ref(false)
const creating = ref(false)
const createForm = ref({
  name: '',
  description: '',
  tags: [] as string[],
})

const loadDatasets = async () => {
  loading.value = true
  try {
    // TODO: 调用实际 API
    // const res = await axios.get('/api/eval/datasets', { params: { tags: filterTags.value.join(','), status: filterStatus.value } })
    // datasets.value = res.data.data.items

    // 模拟数据
    datasets.value = [
      {
        dataset_id: 'ds_golden_v1',
        name: 'Golden Set V1',
        version: '1.0.0',
        status: 'active',
        cases: Array(30).fill({}),
        created_at: new Date().toISOString(),
      },
    ]
  } catch (error) {
    ElMessage.error('加载失败')
  } finally {
    loading.value = false
  }
}

const createDataset = async () => {
  if (!createForm.value.name) {
    ElMessage.warning('请输入名称')
    return
  }
  creating.value = true
  try {
    // TODO: 调用实际 API
    // await axios.post('/api/eval/datasets', createForm.value)
    ElMessage.success('创建成功')
    showCreateDialog.value = false
    createForm.value = { name: '', description: '', tags: [] }
    loadDatasets()
  } catch (error) {
    ElMessage.error('创建失败')
  } finally {
    creating.value = false
  }
}

const viewDataset = (id: string) => {
  router.push(`/evaluation/datasets/${id}`)
}

const runEvaluation = (id: string) => {
  router.push(`/evaluation/runs/create?dataset_id=${id}`)
}

const getStatusType = (status: string) => {
  const map: Record<string, string> = { draft: 'info', active: 'success', archived: 'warning' }
  return map[status] || 'info'
}

const formatTime = (isoString: string) => {
  if (!isoString) return '-'
  return new Date(isoString).toLocaleString('zh-CN')
}

onMounted(() => {
  loadDatasets()
})
</script>

<style scoped>
.datasets-page {
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
