<template>
  <div class="dataset-detail-page">
    <div class="page-header">
      <div>
        <el-button link @click="$router.push('/evaluation/datasets')">← 返回列表</el-button>
        <h1 class="page-title">
          <el-icon><Collection /></el-icon>
          {{ dataset.name || '评测集详情' }}
        </h1>
        <p class="dataset-meta">
          <el-tag size="small" :type="getStatusType(dataset.status)">{{ getStatusLabel(dataset.status) }}</el-tag>
          <span class="meta-item">版本: {{ dataset.version || '-' }}</span>
          <span class="meta-item">ID: {{ datasetId }}</span>
          <span class="meta-item" v-if="dataset.created_at">创建于: {{ formatTime(dataset.created_at) }}</span>
        </p>
      </div>
      <div>
        <el-button type="primary" @click="runEvaluation">
          <el-icon><VideoPlay /></el-icon>
          运行评测
        </el-button>
      </div>
    </div>

    <!-- 描述信息 -->
    <el-card v-if="dataset.description" shadow="never" style="margin-bottom: 24px">
      <p style="margin: 0; color: var(--el-text-color-regular)">{{ dataset.description }}</p>
      <div v-if="dataset.tags && dataset.tags.length" style="margin-top: 8px">
        <el-tag v-for="tag in dataset.tags" :key="tag" size="small" style="margin-right: 4px">{{ tag }}</el-tag>
      </div>
    </el-card>

    <!-- Case 列表 -->
    <el-card shadow="never">
      <template #header>
        <div class="card-header">
          <span>用例列表（共 {{ cases.length }} 条）</span>
          <div>
            <el-input
              v-model="searchKeyword"
              placeholder="搜索用例名称"
              size="small"
              clearable
              style="width: 200px; margin-right: 8px"
              @input="filterCases"
            />
            <el-button size="small" @click="loadCases">刷新</el-button>
          </div>
        </div>
      </template>

      <el-table :data="filteredCases" v-loading="loadingCases" stripe>
        <el-table-column prop="name" label="用例名称" min-width="180" show-overflow-tooltip />
        <el-table-column prop="case_id" label="Case ID" width="180" show-overflow-tooltip />
        <el-table-column prop="category" label="类别" width="100" />
        <el-table-column prop="difficulty" label="难度" width="80">
          <template #default="{ row }">
            <el-tag size="small" :type="getDifficultyType(row.difficulty)">{{ row.difficulty }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="tags" label="标签" width="200">
          <template #default="{ row }">
            <el-tag v-for="tag in (row.tags || []).slice(0, 3)" :key="tag" size="small" style="margin-right: 2px">{{ tag }}</el-tag>
            <span v-if="(row.tags || []).length > 3" style="font-size: 12px; color: var(--el-text-color-secondary)">+{{ row.tags.length - 3 }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="updated_at" label="更新时间" width="180">
          <template #default="{ row }">{{ formatTime(row.updated_at) }}</template>
        </el-table-column>
        <el-table-column label="操作" fixed="right" width="100">
          <template #default="{ row }">
            <el-button type="primary" link size="small" @click="viewCase(row)">查看</el-button>
          </template>
        </el-table-column>
      </el-table>
    </el-card>

    <!-- Case 详情对话框 -->
    <el-dialog v-model="caseDialogVisible" title="用例详情" width="70%">
      <div v-if="selectedCase">
        <el-descriptions :column="2" border>
          <el-descriptions-item label="名称">{{ selectedCase.name }}</el-descriptions-item>
          <el-descriptions-item label="Case ID">{{ selectedCase.case_id }}</el-descriptions-item>
          <el-descriptions-item label="类别">{{ selectedCase.category }}</el-descriptions-item>
          <el-descriptions-item label="难度">{{ selectedCase.difficulty }}</el-descriptions-item>
          <el-descriptions-item label="描述" :span="2">{{ selectedCase.description || '-' }}</el-descriptions-item>
          <el-descriptions-item label="标签" :span="2">
            <el-tag v-for="tag in (selectedCase.tags || [])" :key="tag" size="small" style="margin-right: 4px">{{ tag }}</el-tag>
          </el-descriptions-item>
        </el-descriptions>

        <h4 style="margin: 16px 0 8px">输入数据</h4>
        <pre class="json-block">{{ JSON.stringify(selectedCase.input, null, 2) }}</pre>

        <h4 style="margin: 16px 0 8px" v-if="selectedCase.expected_output">期望输出</h4>
        <pre v-if="selectedCase.expected_output" class="json-block">{{ JSON.stringify(selectedCase.expected_output, null, 2) }}</pre>

        <h4 style="margin: 16px 0 8px" v-if="selectedCase.scoring_criteria && Object.keys(selectedCase.scoring_criteria).length">评分标准</h4>
        <pre v-if="selectedCase.scoring_criteria && Object.keys(selectedCase.scoring_criteria).length" class="json-block">{{ JSON.stringify(selectedCase.scoring_criteria, null, 2) }}</pre>
      </div>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import { Collection, VideoPlay } from '@element-plus/icons-vue'
import axios from 'axios'

const route = useRoute()
const router = useRouter()

const datasetId = computed(() => route.params.id as string)
const dataset = ref<any>({})
const cases = ref<any[]>([])
const loadingCases = ref(false)
const searchKeyword = ref('')

const caseDialogVisible = ref(false)
const selectedCase = ref<any>(null)

const filteredCases = computed(() => {
  if (!searchKeyword.value) return cases.value
  const kw = searchKeyword.value.toLowerCase()
  return cases.value.filter(c =>
    (c.name || '').toLowerCase().includes(kw) ||
    (c.case_id || '').toLowerCase().includes(kw) ||
    (c.description || '').toLowerCase().includes(kw)
  )
})

const loadDataset = async () => {
  try {
    const res = await axios.get(`/api/eval/datasets/${datasetId.value}`)
    dataset.value = res.data?.data || {}
  } catch (error) {
    ElMessage.error('加载数据集详情失败')
  }
}

const loadCases = async () => {
  loadingCases.value = true
  try {
    const res = await axios.get(`/api/eval/datasets/${datasetId.value}/cases`, {
      params: { limit: 200 },
    })
    cases.value = res.data?.data?.items || []
  } catch (error) {
    ElMessage.error('加载用例列表失败')
  } finally {
    loadingCases.value = false
  }
}

const runEvaluation = () => {
  router.push(`/evaluation/runs/create?dataset_id=${datasetId.value}`)
}

const viewCase = (caseData: any) => {
  selectedCase.value = caseData
  caseDialogVisible.value = true
}

const filterCases = () => {
  // computed 自动处理
}

// 工具函数
const getStatusType = (status: string) => {
  const map: Record<string, string> = { draft: 'info', active: 'success', archived: 'warning' }
  return map[status] || 'info'
}

const getStatusLabel = (status: string) => {
  const map: Record<string, string> = { draft: '草稿', active: '活跃', archived: '已归档' }
  return map[status] || status
}

const getDifficultyType = (difficulty: string) => {
  const map: Record<string, string> = { easy: 'success', medium: 'warning', hard: 'danger' }
  return map[difficulty] || 'info'
}

const formatTime = (isoString: string) => {
  if (!isoString) return '-'
  return new Date(isoString).toLocaleString('zh-CN')
}

onMounted(async () => {
  await Promise.all([loadDataset(), loadCases()])
})
</script>

<style scoped>
.dataset-detail-page {
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

.dataset-meta {
  margin: 0;
  display: flex;
  align-items: center;
  gap: 12px;
  font-size: 13px;
  color: var(--el-text-color-secondary);
}

.meta-item {
  font-family: monospace;
}

.card-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
}

.json-block {
  margin: 0;
  padding: 12px;
  background: var(--el-fill-color-lighter);
  border-radius: 4px;
  font-size: 13px;
  font-family: monospace;
  max-height: 300px;
  overflow: auto;
  white-space: pre-wrap;
  word-break: break-all;
}
</style>
