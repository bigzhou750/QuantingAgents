<template>
  <div class="bad-cases-page">
    <div class="page-header">
      <h1 class="page-title">
        <el-icon><Warning /></el-icon>
        Bad Case 池
      </h1>
      <div class="header-actions">
        <el-button type="primary" @click="onlineSampleDialogVisible = true">
          <el-icon><Upload /></el-icon>
          线上抽样入池
        </el-button>
        <el-button @click="$router.push('/evaluation/dashboard')">返回概览</el-button>
      </div>
    </div>

    <!-- 统计卡片 -->
    <el-row :gutter="16" style="margin-bottom: 24px">
      <el-col :span="6">
        <el-card shadow="never" class="stat-card">
          <div class="stat-value">{{ stats.total || 0 }}</div>
          <div class="stat-label">总数</div>
        </el-card>
      </el-col>
      <el-col :span="6">
        <el-card shadow="never" class="stat-card">
          <div class="stat-value">{{ stats.pending_count || 0 }}</div>
          <div class="stat-label">待处理</div>
        </el-card>
      </el-col>
      <el-col :span="6">
        <el-card shadow="never" class="stat-card">
          <div class="stat-value">{{ stats.converted_count || 0 }}</div>
          <div class="stat-label">已回流</div>
        </el-card>
      </el-col>
      <el-col :span="6">
        <el-card shadow="never" class="stat-card">
          <div class="stat-value">{{ highRiskCount }}</div>
          <div class="stat-label">高风险</div>
        </el-card>
      </el-col>
    </el-row>

    <!-- 筛选 -->
    <el-card shadow="never" style="margin-bottom: 24px">
      <el-form :inline="true">
        <el-form-item label="来源">
          <el-select v-model="filterSource" placeholder="全部" clearable>
            <el-option label="Trial 失败" value="trial_failure" />
            <el-option label="人工复核" value="human_review" />
            <el-option label="安全拦截" value="safety_intercept" />
            <el-option label="用户反馈" value="user_feedback" />
            <el-option label="线上抽样" value="online_sampling" />
          </el-select>
        </el-form-item>
        <el-form-item label="风险级别">
          <el-select v-model="filterRisk" placeholder="全部" clearable>
            <el-option label="低" value="low" />
            <el-option label="中" value="medium" />
            <el-option label="高" value="high" />
            <el-option label="严重" value="critical" />
          </el-select>
        </el-form-item>
        <el-form-item>
          <el-button type="primary" @click="loadBadCases">查询</el-button>
        </el-form-item>
      </el-form>
    </el-card>

    <!-- 列表 -->
    <el-table :data="badCases" v-loading="loading" stripe>
      <el-table-column prop="bad_case_id" label="ID" width="160" show-overflow-tooltip />
      <el-table-column prop="source" label="来源" width="130">
        <template #default="{ row }">
          <el-tag size="small" :type="getSourceType(row.source)">{{ getSourceLabel(row.source) }}</el-tag>
        </template>
      </el-table-column>
      <el-table-column prop="risk_level" label="风险" width="90">
        <template #default="{ row }">
          <el-tag size="small" :type="getRiskType(row.risk_level)">{{ row.risk_level }}</el-tag>
        </template>
      </el-table-column>
      <el-table-column prop="failure_reason" label="失败原因" min-width="200" show-overflow-tooltip />
      <el-table-column prop="failure_family" label="失败家族" width="150" show-overflow-tooltip />
      <el-table-column prop="tags" label="标签" width="180">
        <template #default="{ row }">
          <el-tag v-for="tag in (row.tags || []).slice(0, 3)" :key="tag" size="small" style="margin-right: 2px">{{ tag }}</el-tag>
        </template>
      </el-table-column>
      <el-table-column label="状态" width="90">
        <template #default="{ row }">
          <el-tag v-if="row.converted_to_case_id" type="success" size="small">已回流</el-tag>
          <el-tag v-else type="warning" size="small">待处理</el-tag>
        </template>
      </el-table-column>
      <el-table-column label="复核" width="100">
        <template #default="{ row }">
          <el-tag v-if="row.review_status === 'approved' || row.review_status === 'manual' || row.review_status === 'auto_confirmed'" type="success" size="small">已确认</el-tag>
          <el-tag v-else-if="row.review_status === 'rejected'" type="danger" size="small">已拒绝</el-tag>
          <el-tag v-else type="warning" size="small">待复核</el-tag>
        </template>
      </el-table-column>
      <el-table-column prop="created_at" label="创建时间" width="170">
        <template #default="{ row }">{{ formatTime(row.created_at) }}</template>
      </el-table-column>
      <el-table-column label="操作" fixed="right" width="160">
        <template #default="{ row }">
          <el-button type="primary" link size="small" @click="viewDetail(row)">详情</el-button>
          <el-button
            v-if="row.review_status === 'pending'"
            type="warning"
            link
            size="small"
            @click="openReviewDialog(row)"
          >
            复核
          </el-button>
          <el-button
            v-if="!row.converted_to_case_id"
            type="success"
            link
            size="small"
            @click="openConvertDialog(row)"
          >
            回流
          </el-button>
        </template>
      </el-table-column>
    </el-table>

    <!-- 详情对话框 -->
    <el-dialog v-model="detailVisible" title="Bad Case 详情" width="70%">
      <div v-if="selectedBadCase">
        <el-descriptions :column="2" border>
          <el-descriptions-item label="ID">{{ selectedBadCase.bad_case_id }}</el-descriptions-item>
          <el-descriptions-item label="来源">{{ getSourceLabel(selectedBadCase.source) }}</el-descriptions-item>
          <el-descriptions-item label="风险级别">{{ selectedBadCase.risk_level }}</el-descriptions-item>
          <el-descriptions-item label="失败家族">{{ selectedBadCase.failure_family || '-' }}</el-descriptions-item>
          <el-descriptions-item label="检测置信度">{{ selectedBadCase.detection_confidence ?? '-' }}</el-descriptions-item>
          <el-descriptions-item label="检测状态">{{ selectedBadCase.detection_status || '-' }}</el-descriptions-item>
          <el-descriptions-item label="复核状态">{{ selectedBadCase.review_status || '-' }}</el-descriptions-item>
          <el-descriptions-item label="失败原因" :span="2">{{ selectedBadCase.failure_reason }}</el-descriptions-item>
        </el-descriptions>
        <h4 style="margin: 16px 0 8px">输入数据</h4>
        <pre class="json-block">{{ JSON.stringify(selectedBadCase.input_data, null, 2) }}</pre>
        <h4 v-if="selectedBadCase.output_data" style="margin: 16px 0 8px">输出数据</h4>
        <pre v-if="selectedBadCase.output_data" class="json-block">{{ JSON.stringify(selectedBadCase.output_data, null, 2) }}</pre>
        <h4 v-if="selectedBadCase.detection_signals?.length" style="margin: 16px 0 8px">检测信号</h4>
        <pre v-if="selectedBadCase.detection_signals?.length" class="json-block">{{ JSON.stringify(selectedBadCase.detection_signals, null, 2) }}</pre>
      </div>
    </el-dialog>
    <el-dialog v-model="reviewVisible" title="复核 Bad Case" width="500px">
      <el-form label-width="90px">
        <el-form-item label="失败家族">
          <el-select v-model="reviewForm.failure_family" clearable style="width: 100%">
            <el-option label="执行失败" value="execution" />
            <el-option label="工具轨迹" value="tool_trajectory" />
            <el-option label="安全合规" value="safety_compliance" />
            <el-option label="证据幻觉" value="evidence_hallucination" />
            <el-option label="输出质量" value="output_quality" />
            <el-option label="用户反馈" value="user_feedback" />
          </el-select>
        </el-form-item>
        <el-form-item label="复核意见">
          <el-input v-model="reviewForm.comment" type="textarea" :rows="3" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="reviewVisible = false">取消</el-button>
        <el-button type="danger" :loading="reviewing" @click="submitReview('reject')">拒绝</el-button>
        <el-button type="primary" :loading="reviewing" @click="submitReview('approve')">确认</el-button>
      </template>
    </el-dialog>

    <!-- 回流对话框 -->
    <el-dialog v-model="convertVisible" title="回流到评测集" width="500px">
      <el-form label-width="100px">
        <el-form-item label="目标数据集">
          <el-select v-model="convertDatasetId" placeholder="选择数据集" filterable style="width: 100%">
            <el-option v-for="ds in datasets" :key="ds.dataset_id" :label="ds.name" :value="ds.dataset_id" />
          </el-select>
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="convertVisible = false">取消</el-button>
        <el-button type="primary" :loading="converting" @click="doConvert">确认回流</el-button>
      </template>
    </el-dialog>
    <!-- 线上抽样入池对话框 (6.5) -->
    <el-dialog v-model="onlineSampleDialogVisible" title="线上抽样入池" width="600px">
      <el-form :model="onlineSampleForm" label-width="100px">
        <el-form-item label="来源">
          <el-select v-model="onlineSampleForm.source" style="width: 100%">
            <el-option label="线上抽样" value="online_sampling" />
            <el-option label="用户反馈" value="user_feedback" />
            <el-option label="安全拦截" value="safety_intercept" />
          </el-select>
        </el-form-item>
        <el-form-item label="风险级别">
          <el-select v-model="onlineSampleForm.risk_level" style="width: 100%">
            <el-option label="低" value="low" />
            <el-option label="中" value="medium" />
            <el-option label="高" value="high" />
            <el-option label="严重" value="critical" />
          </el-select>
        </el-form-item>
        <el-form-item label="输入数据">
          <el-input v-model="onlineSampleForm.input_data_json" type="textarea" :rows="4" placeholder='JSON 格式，如 {"query": "帮我分析贵州茅台"}' />
        </el-form-item>
        <el-form-item label="输出数据">
          <el-input v-model="onlineSampleForm.output_data_json" type="textarea" :rows="3" placeholder="可选，Agent 的实际输出" />
        </el-form-item>
        <el-form-item label="失败原因">
          <el-input v-model="onlineSampleForm.failure_reason" placeholder="描述问题所在" />
        </el-form-item>
        <el-form-item label="Session ID">
          <el-input v-model="onlineSampleForm.session_id" placeholder="可选，关联的会话ID" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="onlineSampleDialogVisible = false">取消</el-button>
        <el-button type="primary" :loading="submittingSample" @click="submitOnlineSample">提交入池</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import { ElMessage } from 'element-plus'
import { Warning, Upload } from '@element-plus/icons-vue'
import { evalApiClient as axios } from '@/api/evalClient'

const badCases = ref<any[]>([])
const loading = ref(false)
const stats = ref<any>({})
const filterSource = ref('')
const filterRisk = ref('')

const detailVisible = ref(false)
const selectedBadCase = ref<any>(null)
const reviewVisible = ref(false)
const reviewing = ref(false)
const reviewTarget = ref<any>(null)
const reviewForm = ref({ failure_family: '', comment: '' })

const convertVisible = ref(false)
const convertDatasetId = ref('')
const converting = ref(false)
const convertTarget = ref<any>(null)
const datasets = ref<any[]>([])

const highRiskCount = computed(() => {
  return (stats.value.by_risk_level?.high || 0) + (stats.value.by_risk_level?.critical || 0)
})

const loadBadCases = async () => {
  loading.value = true
  try {
    const res = await axios.get('/api/eval/bad-cases', {
      params: { source: filterSource.value, risk_level: filterRisk.value, limit: 50 },
    })
    badCases.value = res.data?.data?.items || []
    stats.value = res.data?.data?.stats || {}
  } catch (error) {
    ElMessage.error('加载失败')
  } finally {
    loading.value = false
  }
}

const viewDetail = (row: any) => {
  selectedBadCase.value = row
  detailVisible.value = true
}

const openReviewDialog = (row: any) => {
  reviewTarget.value = row
  reviewForm.value = { failure_family: row.failure_family || '', comment: '' }
  reviewVisible.value = true
}

const submitReview = async (action: string) => {
  if (!reviewTarget.value) return
  reviewing.value = true
  try {
    await axios.post(`/api/eval/bad-cases/${reviewTarget.value.bad_case_id}/review`, {
      action,
      comment: reviewForm.value.comment,
      failure_family: reviewForm.value.failure_family || undefined,
    })
    ElMessage.success('复核完成')
    reviewVisible.value = false
    await loadBadCases()
  } catch (error: any) {
    ElMessage.error(error?.response?.data?.detail || '复核失败')
  } finally {
    reviewing.value = false
  }
}

const openConvertDialog = async (row: any) => {
  convertTarget.value = row
  convertDatasetId.value = ''
  convertVisible.value = true
  // 加载数据集列表
  try {
    const res = await axios.get('/api/eval/datasets', { params: { limit: 100 } })
    datasets.value = res.data?.data?.items || []
  } catch {
    ElMessage.error('加载数据集列表失败')
  }
}

const doConvert = async () => {
  if (!convertDatasetId.value || !convertTarget.value) return
  converting.value = true
  try {
    await axios.post(`/api/eval/bad-cases/${convertTarget.value.bad_case_id}/convert`, {
      dataset_id: convertDatasetId.value,
    })
    ElMessage.success('回流成功')
    convertVisible.value = false
    await loadBadCases()
  } catch (error: any) {
    ElMessage.error(error.response?.data?.detail || '回流失败')
  } finally {
    converting.value = false
  }
}

// 线上抽样入池 (6.5)
const onlineSampleDialogVisible = ref(false)
const submittingSample = ref(false)
const onlineSampleForm = ref({
  source: 'online_sampling',
  risk_level: 'medium',
  input_data_json: '',
  output_data_json: '',
  failure_reason: '',
  session_id: '',
})

const submitOnlineSample = async () => {
  submittingSample.value = true
  try {
    let input_data: any = {}
    try {
      input_data = JSON.parse(onlineSampleForm.value.input_data_json || '{}')
    } catch {
      ElMessage.error('输入数据格式不正确，请使用 JSON 格式')
      submittingSample.value = false
      return
    }

    let output_data: any = undefined
    if (onlineSampleForm.value.output_data_json.trim()) {
      try {
        output_data = JSON.parse(onlineSampleForm.value.output_data_json)
      } catch {
        ElMessage.error('输出数据格式不正确，请使用 JSON 格式')
        submittingSample.value = false
        return
      }
    }

    const payload: any = {
      source: onlineSampleForm.value.source,
      input_data,
      output_data,
      failure_reason: onlineSampleForm.value.failure_reason,
      risk_level: onlineSampleForm.value.risk_level,
      tags: [],
    }
    if (onlineSampleForm.value.session_id) {
      payload.session_id = onlineSampleForm.value.session_id
    }

    await axios.post('/api/eval/online-sample', payload)
    ElMessage.success('样本已入池')
    onlineSampleDialogVisible.value = false
    // Reset form
    onlineSampleForm.value = {
      source: 'online_sampling',
      risk_level: 'medium',
      input_data_json: '',
      output_data_json: '',
      failure_reason: '',
      session_id: '',
    }
    await loadBadCases()
  } catch (error: any) {
    ElMessage.error(error?.response?.data?.detail || '提交失败')
  } finally {
    submittingSample.value = false
  }
}

const getSourceType = (source: string): 'primary' | 'success' | 'warning' | 'info' | 'danger' => {
  const map: Record<string, 'primary' | 'success' | 'warning' | 'info' | 'danger'> = {
    trial_failure: 'danger', human_review: 'warning', safety_intercept: 'danger',
    user_feedback: 'info', online_sampling: 'primary',
  }
  return map[source] || 'info'
}

const getSourceLabel = (source: string) => {
  const map: Record<string, string> = { trial_failure: 'Trial 失败', human_review: '人工复核', safety_intercept: '安全拦截', user_feedback: '用户反馈', online_sampling: '线上抽样' }
  return map[source] || source
}

const getRiskType = (level: string): 'primary' | 'success' | 'warning' | 'info' | 'danger' => {
  const map: Record<string, 'primary' | 'success' | 'warning' | 'info' | 'danger'> = { low: 'success', medium: 'warning', high: 'danger', critical: 'danger' }
  return map[level] || 'info'
}

const formatTime = (isoString: string) => {
  if (!isoString) return '-'
  return new Date(isoString).toLocaleString('zh-CN')
}

onMounted(() => {
  loadBadCases()
})
</script>

<style scoped>
.bad-cases-page { padding: 24px; }
.page-header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 24px; }
.header-actions { display: flex; gap: 8px; }
.page-title { font-size: 24px; font-weight: 600; display: flex; align-items: center; gap: 12px; margin: 0; }
.stat-card { text-align: center; height: 100px; display: flex; flex-direction: column; justify-content: center; }
.stat-value { font-size: 28px; font-weight: 700; color: var(--el-color-primary); }
.stat-label { font-size: 13px; color: var(--el-text-color-secondary); margin-top: 4px; }
.json-block { margin: 0; padding: 12px; background: var(--el-fill-color-lighter); border-radius: 4px; font-size: 13px; font-family: monospace; max-height: 300px; overflow: auto; white-space: pre-wrap; word-break: break-all; }
</style>
