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
      <div class="header-actions">
        <el-button @click="openPublishVersionDialog">
          <el-icon><Stamp /></el-icon>
          发布版本
        </el-button>
        <el-dropdown trigger="click" @command="handleImportCommand">
          <el-button>
            <el-icon><Upload /></el-icon>
            导入用例
            <el-icon class="el-icon--right"><ArrowDown /></el-icon>
          </el-button>
          <template #dropdown>
            <el-dropdown-menu>
              <el-dropdown-item command="golden">导入内置 Golden Set</el-dropdown-item>
              <el-dropdown-item command="json">JSON 批量导入</el-dropdown-item>
            </el-dropdown-menu>
          </template>
        </el-dropdown>
        <el-button @click="openCreateCaseDialog">
          <el-icon><Plus /></el-icon>
          添加用例
        </el-button>
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

    <!-- 空数据引导 (2.6) -->
    <el-card v-if="!loadingCases && cases.length === 0" shadow="never" class="empty-guide">
      <el-empty description="暂无评测用例">
        <template #description>
          <p style="color: var(--el-text-color-secondary); margin-bottom: 16px">
            评测集还没有用例，请选择以下方式添加：
          </p>
        </template>
        <div class="guide-actions">
          <el-button type="primary" @click="openCreateCaseDialog">
            <el-icon><Plus /></el-icon>
            手动添加用例
          </el-button>
          <el-button @click="importGoldenSet" :loading="importingGolden">
            <el-icon><Star /></el-icon>
            导入内置 Golden Set
          </el-button>
          <el-button @click="openBatchImportDialog">
            <el-icon><Upload /></el-icon>
            JSON 批量导入
          </el-button>
          <el-button @click="$router.push('/evaluation/bad-cases')">
            <el-icon><WarningFilled /></el-icon>
            从 Bad Case 回流
          </el-button>
        </div>
      </el-empty>
    </el-card>

    <!-- Case 列表 -->
    <el-card v-if="cases.length > 0 || loadingCases" shadow="never">
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
            <el-button
              v-if="selectedCaseIds.length > 0"
              size="small"
              @click="openBatchEditDialog"
            >
              批量编辑 ({{ selectedCaseIds.length }})
            </el-button>
            <el-button size="small" @click="loadCases">刷新</el-button>
          </div>
        </div>
      </template>

      <el-table
        :data="filteredCases"
        v-loading="loadingCases"
        stripe
        @selection-change="handleSelectionChange"
      >
        <el-table-column type="selection" width="45" />
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
        <el-table-column label="操作" fixed="right" width="180">
          <template #default="{ row }">
            <el-button type="primary" link size="small" @click="viewCase(row)">查看</el-button>
            <el-button type="primary" link size="small" @click="openEditCaseDialog(row)">编辑</el-button>
            <el-popconfirm
              title="确认删除此用例？"
              confirm-button-text="删除"
              cancel-button-text="取消"
              @confirm="deleteCase(row.case_id)"
            >
              <template #reference>
                <el-button type="danger" link size="small">删除</el-button>
              </template>
            </el-popconfirm>
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

    <!-- 创建 Case 对话框 -->
    <el-dialog v-model="createCaseDialogVisible" title="添加评测用例" width="720px">
      <el-form :model="caseForm" label-width="110px">
        <el-form-item label="名称" required>
          <el-input v-model="caseForm.name" placeholder="例如：A股基本面研究" />
        </el-form-item>
        <el-form-item label="描述">
          <el-input v-model="caseForm.description" type="textarea" :rows="2" placeholder="说明这个用例要验证什么" />
        </el-form-item>
        <el-form-item label="类别">
          <el-input v-model="caseForm.category" placeholder="financial_research / safety / tool_process" />
        </el-form-item>
        <el-form-item label="难度">
          <el-select v-model="caseForm.difficulty" style="width: 180px">
            <el-option label="easy" value="easy" />
            <el-option label="medium" value="medium" />
            <el-option label="hard" value="hard" />
          </el-select>
        </el-form-item>
        <el-form-item label="标签">
          <el-select v-model="caseForm.tags" multiple filterable allow-create default-first-option placeholder="输入后回车添加标签" style="width: 100%">
            <el-option label="golden" value="golden" />
            <el-option label="regression" value="regression" />
            <el-option label="safety" value="safety" />
            <el-option label="evidence" value="evidence" />
          </el-select>
        </el-form-item>
        <el-form-item label="输入 JSON" required>
          <el-input v-model="caseForm.inputJson" type="textarea" :rows="4" />
        </el-form-item>
        <el-form-item label="期望输出 JSON">
          <el-input v-model="caseForm.expectedOutputJson" type="textarea" :rows="4" />
        </el-form-item>
        <el-form-item label="评分标准 JSON">
          <el-input v-model="caseForm.scoringCriteriaJson" type="textarea" :rows="4" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="createCaseDialogVisible = false">取消</el-button>
        <el-button type="primary" :loading="creatingCase" @click="createCase">添加</el-button>
      </template>
    </el-dialog>

    <!-- 编辑 Case 对话框 (2.1) -->
    <el-dialog v-model="editCaseDialogVisible" title="编辑评测用例" width="720px">
      <el-form :model="editCaseForm" label-width="110px">
        <el-form-item label="名称" required>
          <el-input v-model="editCaseForm.name" />
        </el-form-item>
        <el-form-item label="描述">
          <el-input v-model="editCaseForm.description" type="textarea" :rows="2" />
        </el-form-item>
        <el-form-item label="类别">
          <el-input v-model="editCaseForm.category" />
        </el-form-item>
        <el-form-item label="难度">
          <el-select v-model="editCaseForm.difficulty" style="width: 180px">
            <el-option label="easy" value="easy" />
            <el-option label="medium" value="medium" />
            <el-option label="hard" value="hard" />
          </el-select>
        </el-form-item>
        <el-form-item label="标签">
          <el-select v-model="editCaseForm.tags" multiple filterable allow-create default-first-option placeholder="输入后回车添加标签" style="width: 100%">
            <el-option label="golden" value="golden" />
            <el-option label="regression" value="regression" />
            <el-option label="safety" value="safety" />
            <el-option label="evidence" value="evidence" />
          </el-select>
        </el-form-item>
        <el-form-item label="输入 JSON" required>
          <el-input v-model="editCaseForm.inputJson" type="textarea" :rows="4" />
        </el-form-item>
        <el-form-item label="期望输出 JSON">
          <el-input v-model="editCaseForm.expectedOutputJson" type="textarea" :rows="4" />
        </el-form-item>
        <el-form-item label="评分标准 JSON">
          <el-input v-model="editCaseForm.scoringCriteriaJson" type="textarea" :rows="4" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="editCaseDialogVisible = false">取消</el-button>
        <el-button type="primary" :loading="updatingCase" @click="updateCase">保存</el-button>
      </template>
    </el-dialog>

    <!-- 批量编辑对话框 (2.4) -->
    <el-dialog v-model="batchEditDialogVisible" title="批量编辑用例" width="560px">
      <p style="margin-bottom: 16px; color: var(--el-text-color-secondary)">
        已选择 {{ selectedCaseIds.length }} 条用例，修改以下字段将应用到所有选中项。
      </p>
      <el-form :model="batchEditForm" label-width="110px">
        <el-form-item label="标签">
          <el-select v-model="batchEditForm.tags" multiple filterable allow-create default-first-option placeholder="留空则不修改" style="width: 100%">
            <el-option label="golden" value="golden" />
            <el-option label="regression" value="regression" />
            <el-option label="safety" value="safety" />
            <el-option label="evidence" value="evidence" />
          </el-select>
        </el-form-item>
        <el-form-item label="类别">
          <el-input v-model="batchEditForm.category" placeholder="留空则不修改" />
        </el-form-item>
        <el-form-item label="难度">
          <el-select v-model="batchEditForm.difficulty" placeholder="留空则不修改" clearable style="width: 180px">
            <el-option label="easy" value="easy" />
            <el-option label="medium" value="medium" />
            <el-option label="hard" value="hard" />
          </el-select>
        </el-form-item>
        <el-form-item label="评分标准 JSON">
          <el-input v-model="batchEditForm.scoringCriteriaJson" type="textarea" :rows="4" placeholder="留空则不修改" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="batchEditDialogVisible = false">取消</el-button>
        <el-button type="primary" :loading="batchUpdating" @click="batchUpdateCases">应用</el-button>
      </template>
    </el-dialog>

    <!-- 批量导入对话框 (2.3) -->
    <el-dialog v-model="batchImportDialogVisible" title="JSON 批量导入用例" width="720px">
      <p style="margin-bottom: 12px; color: var(--el-text-color-secondary)">
        请输入 JSON 数组，每个元素包含 name、input（必填）、description、category、difficulty、tags、expected_output、scoring_criteria（可选）。
      </p>
      <el-input
        v-model="batchImportJson"
        type="textarea"
        :rows="12"
        placeholder='[{"name": "示例用例", "input": {"prompt": "分析问题"}, "category": "general", "difficulty": "medium"}]'
      />
      <template #footer>
        <el-button @click="batchImportDialogVisible = false">取消</el-button>
        <el-button type="primary" :loading="batchImporting" @click="batchImportCases">导入</el-button>
      </template>
    </el-dialog>

    <!-- 发布版本对话框 (2.5) -->
    <el-dialog v-model="publishVersionDialogVisible" title="发布数据集版本" width="480px">
      <p style="margin-bottom: 12px; color: var(--el-text-color-secondary)">
        当前版本: {{ dataset.version || '-' }}。发布新版本后，该版本可用于后续评测运行。
      </p>
      <el-form label-width="100px">
        <el-form-item label="版本号" required>
          <el-input v-model="newVersion" placeholder="例如: 2.0.0" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="publishVersionDialogVisible = false">取消</el-button>
        <el-button type="primary" :loading="publishingVersion" @click="publishVersion">发布</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import { Collection, VideoPlay, Plus, Upload, ArrowDown, Star, WarningFilled, Stamp } from '@element-plus/icons-vue'
import { evalApiClient as axios } from '@/api/evalClient'

const route = useRoute()
const router = useRouter()

const datasetId = computed(() => route.params.id as string)
const dataset = ref<any>({})
const cases = ref<any[]>([])
const loadingCases = ref(false)
const searchKeyword = ref('')
const selectedCaseIds = ref<string[]>([])

// Dialog states
const caseDialogVisible = ref(false)
const selectedCase = ref<any>(null)
const createCaseDialogVisible = ref(false)
const creatingCase = ref(false)
const editCaseDialogVisible = ref(false)
const updatingCase = ref(false)
const editingCaseId = ref('')
const batchEditDialogVisible = ref(false)
const batchUpdating = ref(false)
const batchImportDialogVisible = ref(false)
const batchImporting = ref(false)
const batchImportJson = ref('')
const publishVersionDialogVisible = ref(false)
const publishingVersion = ref(false)
const newVersion = ref('')
const importingGolden = ref(false)

const caseForm = ref({
  name: '',
  description: '',
  category: 'financial_research',
  difficulty: 'medium',
  tags: [] as string[],
  inputJson: '{\n  "prompt": "请分析贵州茅台的基本面、估值和主要风险。"\n}',
  expectedOutputJson: '{\n  "must_include": ["基本面", "估值", "风险"]\n}',
  scoringCriteriaJson: '{\n  "min_output_length": 300\n}',
})

const editCaseForm = ref({
  name: '',
  description: '',
  category: '',
  difficulty: 'medium',
  tags: [] as string[],
  inputJson: '',
  expectedOutputJson: '',
  scoringCriteriaJson: '',
})

const batchEditForm = ref({
  tags: [] as string[],
  category: '',
  difficulty: '',
  scoringCriteriaJson: '',
})

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

const openCreateCaseDialog = () => {
  caseForm.value = {
    name: '',
    description: '',
    category: 'financial_research',
    difficulty: 'medium',
    tags: [],
    inputJson: '{\n  "prompt": "请分析贵州茅台的基本面、估值和主要风险。"\n}',
    expectedOutputJson: '{\n  "must_include": ["基本面", "估值", "风险"]\n}',
    scoringCriteriaJson: '{\n  "min_output_length": 300\n}',
  }
  createCaseDialogVisible.value = true
}

// Edit case (2.1)
const openEditCaseDialog = (caseData: any) => {
  editingCaseId.value = caseData.case_id
  editCaseForm.value = {
    name: caseData.name || '',
    description: caseData.description || '',
    category: caseData.category || '',
    difficulty: caseData.difficulty || 'medium',
    tags: [...(caseData.tags || [])],
    inputJson: JSON.stringify(caseData.input || {}, null, 2),
    expectedOutputJson: caseData.expected_output ? JSON.stringify(caseData.expected_output, null, 2) : '',
    scoringCriteriaJson: caseData.scoring_criteria && Object.keys(caseData.scoring_criteria).length
      ? JSON.stringify(caseData.scoring_criteria, null, 2) : '',
  }
  editCaseDialogVisible.value = true
}

const updateCase = async () => {
  if (!editCaseForm.value.name.trim()) {
    ElMessage.warning('请输入用例名称')
    return
  }

  updatingCase.value = true
  try {
    const input = parseJsonField(editCaseForm.value.inputJson, '输入 JSON')
    if (!input) {
      ElMessage.warning('请输入输入 JSON')
      return
    }

    const updateData: any = {
      name: editCaseForm.value.name,
      description: editCaseForm.value.description,
      category: editCaseForm.value.category,
      difficulty: editCaseForm.value.difficulty,
      tags: editCaseForm.value.tags,
      input,
    }

    const expectedOutput = parseJsonField(editCaseForm.value.expectedOutputJson, '期望输出 JSON')
    if (expectedOutput !== undefined) updateData.expected_output = expectedOutput

    const scoringCriteria = parseJsonField(editCaseForm.value.scoringCriteriaJson, '评分标准 JSON')
    if (scoringCriteria !== undefined) updateData.scoring_criteria = scoringCriteria

    await axios.put(`/api/eval/cases/${editingCaseId.value}`, updateData)

    ElMessage.success('用例已更新')
    editCaseDialogVisible.value = false
    await Promise.all([loadDataset(), loadCases()])
  } catch (error: any) {
    ElMessage.error(error?.message || error?.response?.data?.detail || '更新用例失败')
  } finally {
    updatingCase.value = false
  }
}

// Delete case (2.1)
const deleteCase = async (caseId: string) => {
  try {
    await axios.delete(`/api/eval/cases/${caseId}`)
    ElMessage.success('用例已删除')
    await Promise.all([loadDataset(), loadCases()])
  } catch (error: any) {
    ElMessage.error(error?.message || error?.response?.data?.detail || '删除用例失败')
  }
}

// Selection for batch operations
const handleSelectionChange = (selection: any[]) => {
  selectedCaseIds.value = selection.map(s => s.case_id)
}

// Batch edit (2.4)
const openBatchEditDialog = () => {
  batchEditForm.value = {
    tags: [],
    category: '',
    difficulty: '',
    scoringCriteriaJson: '',
  }
  batchEditDialogVisible.value = true
}

const batchUpdateCases = async () => {
  batchUpdating.value = true
  try {
    const updateData: any = {
      case_ids: selectedCaseIds.value,
    }
    if (batchEditForm.value.tags.length > 0) updateData.tags = batchEditForm.value.tags
    if (batchEditForm.value.category) updateData.category = batchEditForm.value.category
    if (batchEditForm.value.difficulty) updateData.difficulty = batchEditForm.value.difficulty
    if (batchEditForm.value.scoringCriteriaJson.trim()) {
      updateData.scoring_criteria = parseJsonField(batchEditForm.value.scoringCriteriaJson, '评分标准 JSON')
    }

    await axios.put(`/api/eval/datasets/${datasetId.value}/cases/batch-update`, updateData)
    ElMessage.success(`已更新 ${selectedCaseIds.value.length} 条用例`)
    batchEditDialogVisible.value = false
    selectedCaseIds.value = []
    await loadCases()
  } catch (error: any) {
    ElMessage.error(error?.message || error?.response?.data?.detail || '批量更新失败')
  } finally {
    batchUpdating.value = false
  }
}

// Import commands
const handleImportCommand = (command: string) => {
  if (command === 'golden') importGoldenSet()
  else if (command === 'json') openBatchImportDialog()
}

// Golden Set import (2.2)
const importGoldenSet = async () => {
  importingGolden.value = true
  try {
    const res = await axios.post(`/api/eval/datasets/${datasetId.value}/import-golden`)
    const data = res.data?.data || {}
    ElMessage.success(`导入完成：${data.imported || 0} 条新增，${data.skipped || 0} 条跳过`)
    await Promise.all([loadDataset(), loadCases()])
  } catch (error: any) {
    ElMessage.error(error?.message || error?.response?.data?.detail || '导入 Golden Set 失败')
  } finally {
    importingGolden.value = false
  }
}

// Batch import (2.3)
const openBatchImportDialog = () => {
  batchImportJson.value = ''
  batchImportDialogVisible.value = true
}

const batchImportCases = async () => {
  if (!batchImportJson.value.trim()) {
    ElMessage.warning('请输入 JSON 数据')
    return
  }

  let parsedCases: any[]
  try {
    parsedCases = JSON.parse(batchImportJson.value)
    if (!Array.isArray(parsedCases)) {
      ElMessage.warning('JSON 必须是数组格式')
      return
    }
  } catch {
    ElMessage.warning('JSON 格式不合法')
    return
  }

  batchImporting.value = true
  try {
    const res = await axios.post(`/api/eval/datasets/${datasetId.value}/cases/batch-import`, {
      cases: parsedCases,
    })
    const data = res.data?.data || {}
    ElMessage.success(`导入完成：${data.imported || 0} 条成功，${data.failed || 0} 条失败`)
    batchImportDialogVisible.value = false
    await Promise.all([loadDataset(), loadCases()])
  } catch (error: any) {
    ElMessage.error(error?.message || error?.response?.data?.detail || '批量导入失败')
  } finally {
    batchImporting.value = false
  }
}

// Publish version (2.5)
const openPublishVersionDialog = () => {
  // Suggest next version
  const current = dataset.value.version || '1.0.0'
  const parts = current.split('.')
  if (parts.length === 3) {
    parts[0] = String(parseInt(parts[0]) + 1)
    parts[1] = '0'
    parts[2] = '0'
    newVersion.value = parts.join('.')
  } else {
    newVersion.value = '2.0.0'
  }
  publishVersionDialogVisible.value = true
}

const publishVersion = async () => {
  if (!newVersion.value.trim()) {
    ElMessage.warning('请输入版本号')
    return
  }

  publishingVersion.value = true
  try {
    await axios.post(`/api/eval/datasets/${datasetId.value}/publish-version`, {
      version: newVersion.value,
    })
    ElMessage.success(`已发布版本 ${newVersion.value}`)
    publishVersionDialogVisible.value = false
    await loadDataset()
  } catch (error: any) {
    ElMessage.error(error?.message || error?.response?.data?.detail || '发布版本失败')
  } finally {
    publishingVersion.value = false
  }
}

const parseJsonField = (value: string, label: string) => {
  const trimmed = value.trim()
  if (!trimmed) return undefined

  try {
    return JSON.parse(trimmed)
  } catch {
    throw new Error(`${label} 不是合法 JSON`)
  }
}

const createCase = async () => {
  if (!caseForm.value.name.trim()) {
    ElMessage.warning('请输入用例名称')
    return
  }

  creatingCase.value = true
  try {
    const input = parseJsonField(caseForm.value.inputJson, '输入 JSON')
    if (!input) {
      ElMessage.warning('请输入输入 JSON')
      return
    }

    await axios.post(`/api/eval/datasets/${datasetId.value}/cases`, {
      name: caseForm.value.name,
      description: caseForm.value.description,
      category: caseForm.value.category,
      difficulty: caseForm.value.difficulty,
      tags: caseForm.value.tags,
      input,
      expected_output: parseJsonField(caseForm.value.expectedOutputJson, '期望输出 JSON'),
      scoring_criteria: parseJsonField(caseForm.value.scoringCriteriaJson, '评分标准 JSON') || {},
    })

    ElMessage.success('用例已添加')
    createCaseDialogVisible.value = false
    await Promise.all([loadDataset(), loadCases()])
  } catch (error: any) {
    ElMessage.error(error?.message || error?.response?.data?.detail || '添加用例失败')
  } finally {
    creatingCase.value = false
  }
}

const filterCases = () => {
  // computed 自动处理
}

// 工具函数
const getStatusType = (status: string): 'primary' | 'success' | 'warning' | 'info' | 'danger' => {
  const map: Record<string, 'primary' | 'success' | 'warning' | 'info' | 'danger'> = { draft: 'info', active: 'success', archived: 'warning' }
  return map[status] || 'info'
}

const getStatusLabel = (status: string) => {
  const map: Record<string, string> = { draft: '草稿', active: '活跃', archived: '已归档' }
  return map[status] || status
}

const getDifficultyType = (difficulty: string): 'primary' | 'success' | 'warning' | 'info' | 'danger' => {
  const map: Record<string, 'primary' | 'success' | 'warning' | 'info' | 'danger'> = { easy: 'success', medium: 'warning', hard: 'danger' }
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

.header-actions {
  display: flex;
  gap: 8px;
  align-items: center;
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

.empty-guide {
  text-align: center;
  padding: 48px 0;
}

.guide-actions {
  display: flex;
  gap: 12px;
  justify-content: center;
  flex-wrap: wrap;
}
</style>
