<template>
  <div class="human-review-page">
    <div class="page-header">
      <h1 class="page-title">
        <el-icon><EditPen /></el-icon>
        人工复核
      </h1>
      <el-button @click="$router.push('/evaluation/dashboard')">返回概览</el-button>
    </div>

    <!-- 筛选条件 (4.4) -->
    <el-card shadow="never" style="margin-bottom: 24px">
      <el-form :inline="true" size="small">
        <el-form-item label="Run ID">
          <el-input v-model="filters.runId" placeholder="可选" clearable style="width: 180px" />
        </el-form-item>
        <el-form-item label="评分来源">
          <el-select v-model="filters.source" placeholder="全部" clearable style="width: 140px">
            <el-option label="规则评分" value="rule_based" />
            <el-option label="金融评分" value="financial" />
            <el-option label="证据评分" value="evidence" />
            <el-option label="轨迹评分" value="trace" />
            <el-option label="安全评分" value="safety" />
            <el-option label="LLM Judge" value="llm_judge" />
          </el-select>
        </el-form-item>
        <el-form-item label="置信度上限">
          <el-slider v-model="filters.maxConfidence" :min="0" :max="1" :step="0.1" show-input style="width: 200px" />
        </el-form-item>
        <el-form-item>
          <el-button type="primary" @click="loadPending">筛选</el-button>
          <el-button @click="resetFilters">重置</el-button>
        </el-form-item>
      </el-form>
    </el-card>

    <!-- 待复核列表 -->
    <el-card shadow="never">
      <template #header>
        <div class="card-header">
          <span>待复核评分（{{ pendingReviews.length }} 条）</span>
          <el-button size="small" @click="loadPending">刷新</el-button>
        </div>
      </template>

      <el-table :data="pendingReviews" v-loading="loading" stripe>
        <el-table-column prop="score_id" label="Score ID" width="160" show-overflow-tooltip />
        <el-table-column prop="trial_id" label="Trial ID" width="220" show-overflow-tooltip />
        <el-table-column prop="score_name" label="评分维度" width="130" />
        <el-table-column prop="source" label="来源" width="110">
          <template #default="{ row }">
            <el-tag size="small">{{ row.source }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="score" label="分数" width="80">
          <template #default="{ row }">
            <span :style="{ color: row.score < 0.5 ? 'var(--el-color-danger)' : '' }">
              {{ (row.score * 100).toFixed(0) }}%
            </span>
          </template>
        </el-table-column>
        <el-table-column prop="confidence" label="置信度" width="80">
          <template #default="{ row }">{{ (row.confidence * 100).toFixed(0) }}%</template>
        </el-table-column>
        <el-table-column prop="reason" label="原因" min-width="180" show-overflow-tooltip />
        <el-table-column label="操作" fixed="right" width="80">
          <template #default="{ row }">
            <el-button type="primary" link size="small" @click="openReviewDialog(row)">复核</el-button>
          </template>
        </el-table-column>
      </el-table>

      <div v-if="!loading && pendingReviews.length === 0" style="text-align: center; padding: 40px; color: var(--el-text-color-secondary)">
        暂无待复核项 🎉
      </div>
    </el-card>

    <!-- 复核对话框 (4.2, 4.3) -->
    <el-dialog v-model="reviewDialogVisible" title="人工复核" width="75%" top="5vh">
      <div v-if="selectedScore" v-loading="contextLoading">
        <!-- 评分基本信息 -->
        <el-descriptions :column="3" border size="small" style="margin-bottom: 16px">
          <el-descriptions-item label="Score ID">{{ selectedScore.score_id }}</el-descriptions-item>
          <el-descriptions-item label="Trial ID">{{ selectedScore.trial_id }}</el-descriptions-item>
          <el-descriptions-item label="评分维度">{{ selectedScore.score_name }}</el-descriptions-item>
          <el-descriptions-item label="来源">{{ selectedScore.source }}</el-descriptions-item>
          <el-descriptions-item label="原始分数">
            <span :style="{ color: selectedScore.score < 0.5 ? 'var(--el-color-danger)' : '' }">
              {{ (selectedScore.score * 100).toFixed(1) }}%
            </span>
          </el-descriptions-item>
          <el-descriptions-item label="置信度">{{ (selectedScore.confidence * 100).toFixed(1) }}%</el-descriptions-item>
          <el-descriptions-item label="评分原因" :span="3">{{ selectedScore.reason }}</el-descriptions-item>
        </el-descriptions>

        <!-- Case 输入和 Agent 输出 (4.2) -->
        <el-row :gutter="16" style="margin-bottom: 16px">
          <el-col :span="12">
            <div class="section-label">Case 输入</div>
            <pre class="json-block context-block">{{ JSON.stringify(trialContext?.input_data || {}, null, 2) }}</pre>
          </el-col>
          <el-col :span="12">
            <div class="section-label">Agent 输出 (Final Output)</div>
            <div v-if="trialContext?.output_data?.content" class="output-block">
              {{ trialContext.output_data.content }}
            </div>
            <pre v-else class="json-block context-block">{{ JSON.stringify(trialContext?.output_data || {}, null, 2) }}</pre>
          </el-col>
        </el-row>

        <!-- Claim-Evidence Grounding (5.3) -->
        <div v-if="claimEvidenceList.length" style="margin-bottom: 16px">
          <div class="section-label">
            Claim-Evidence Grounding
            <el-tag size="small" type="info" style="margin-left: 8px">{{ claimEvidenceList.length }} 条</el-tag>
          </div>
          <el-table :data="claimEvidenceList" size="small" border max-height="300">
            <el-table-column label="Verdict" width="140">
              <template #default="{ row }">
                <el-tag
                  :type="verdictTagType(row.verdict)"
                  size="small"
                  effect="dark"
                >{{ verdictLabel(row.verdict) }}</el-tag>
              </template>
            </el-table-column>
            <el-table-column prop="claim_text" label="Claim" min-width="200" show-overflow-tooltip />
            <el-table-column prop="evidence_snippet" label="证据片段" min-width="200" show-overflow-tooltip>
              <template #default="{ row }">
                {{ row.evidence_snippet || '—' }}
              </template>
            </el-table-column>
            <el-table-column label="置信度" width="90">
              <template #default="{ row }">{{ ((row.confidence || 0) * 100).toFixed(0) }}%</template>
            </el-table-column>
            <el-table-column prop="verification_method" label="判定方法" width="140" show-overflow-tooltip>
              <template #default="{ row }">{{ row.verification_method || '—' }}</template>
            </el-table-column>
            <el-table-column prop="reason" label="判定理由" min-width="180" show-overflow-tooltip />
            <el-table-column prop="evidence_source" label="来源" width="120" show-overflow-tooltip>
              <template #default="{ row }">{{ row.evidence_source || '—' }}</template>
            </el-table-column>
            <el-table-column label="标注历史" width="90">
              <template #default="{ row }">
                <el-tag v-if="(row.annotation_history || []).length" type="info" size="small">
                  {{ row.annotation_history.length }} 条
                </el-tag>
                <span v-else>-</span>
              </template>
            </el-table-column>
          </el-table>
          <el-collapse v-if="hasAnnotationHistory" style="margin-top: 8px">
            <el-collapse-item title="Claim 标注历史与证据引用">
              <pre class="json-block">{{ JSON.stringify(claimEvidenceList.map((claim: any) => ({
                claim_id: claim.claim_id,
                truth_label: claim.truth_label,
                annotation_history: claim.annotation_history || [],
              })), null, 2) }}</pre>
            </el-collapse-item>
          </el-collapse>
        </div>

        <!-- Judge 维度理由和原始输出 -->
        <div v-if="judgeDimensions.length" style="margin-bottom: 16px">
          <div class="section-label">Judge 维度理由</div>
          <el-table :data="judgeDimensions" size="small" border>
            <el-table-column prop="name" label="维度" width="160" />
            <el-table-column label="分数" width="100">
              <template #default="{ row }">{{ (Number(row.score || 0) * 100).toFixed(1) }}%</template>
            </el-table-column>
            <el-table-column prop="reason" label="理由" min-width="220" show-overflow-tooltip />
          </el-table>
        </div>

        <div v-if="judgeRawOutput" style="margin-bottom: 16px">
          <el-collapse>
            <el-collapse-item title="原始 Judge 输出">
              <pre class="json-block">{{ JSON.stringify(judgeRawOutput, null, 2) }}</pre>
            </el-collapse-item>
          </el-collapse>
        </div>

        <!-- 历史评分 -->
        <div v-if="historicalScores.length" style="margin-bottom: 16px">
          <div class="section-label">历史评分</div>
          <el-table :data="historicalScores" size="small" stripe>
            <el-table-column prop="score_name" label="维度" width="140" />
            <el-table-column prop="score" label="分数" width="80">
              <template #default="{ row }">{{ (row.score * 100).toFixed(0) }}%</template>
            </el-table-column>
            <el-table-column prop="source" label="来源" width="100" />
            <el-table-column prop="human_reviewed" label="已复核" width="80">
              <template #default="{ row }">
                <el-tag v-if="row.human_reviewed" type="success" size="small">是</el-tag>
              </template>
            </el-table-column>
            <el-table-column prop="reason" label="原因" min-width="200" show-overflow-tooltip />
          </el-table>
        </div>

        <el-divider content-position="left">复核操作</el-divider>

        <el-form label-width="100px">
          <el-form-item label="复核动作">
            <el-radio-group v-model="reviewForm.action">
              <el-radio value="approve">通过</el-radio>
              <el-radio value="reject">驳回</el-radio>
              <el-radio value="adjust_score">调整分数</el-radio>
              <el-radio value="add_bad_case">加入 Bad Case</el-radio>
              <el-radio value="reflow">回流数据集</el-radio>
            </el-radio-group>
          </el-form-item>

          <el-form-item label="新分数" v-if="reviewForm.action !== 'add_bad_case'">
            <el-slider v-model="reviewForm.newScore" :min="0" :max="1" :step="0.05" show-input />
          </el-form-item>

          <el-form-item label="目标数据集" v-if="reviewForm.action === 'reflow'">
            <el-select v-model="reviewForm.targetDatasetId" placeholder="选择目标数据集" filterable style="width: 100%">
              <el-option v-for="ds in datasets" :key="ds.dataset_id" :label="`${ds.name} (v${ds.version})`" :value="ds.dataset_id" />
            </el-select>
          </el-form-item>

          <el-form-item label="复核意见">
            <el-input v-model="reviewForm.comment" type="textarea" :rows="3" placeholder="请输入复核意见" />
          </el-form-item>
        </el-form>
      </div>

      <template #footer>
        <el-button @click="reviewDialogVisible = false">取消</el-button>
        <el-button type="primary" :loading="submitting" @click="submitReview">提交复核</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import { ElMessage } from 'element-plus'
import { EditPen } from '@element-plus/icons-vue'
import { evalApiClient as axios } from '@/api/evalClient'

const pendingReviews = ref<any[]>([])
const loading = ref(false)
const datasets = ref<any[]>([])

// Filters (4.4)
const filters = ref({
  runId: '',
  source: '',
  maxConfidence: 0.7,
})

const resetFilters = () => {
  filters.value = { runId: '', source: '', maxConfidence: 0.7 }
  loadPending()
}

// Review dialog
const reviewDialogVisible = ref(false)
const selectedScore = ref<any>(null)
const submitting = ref(false)
const contextLoading = ref(false)
const trialContext = ref<any>(null)
const historicalScores = ref<any[]>([])

const reviewForm = ref({
  newScore: 0.5,
  comment: '',
  action: 'adjust_score',
  targetDatasetId: '',
})

const judgeRawOutput = computed(() => selectedScore.value?.raw_output || null)
const judgeDimensions = computed(() => judgeRawOutput.value?.parsed?.dimensions || [])

// Claim-Evidence (5.3)
const claimEvidenceList = computed(() => {
  const claims = selectedScore.value?.claims || []
  return Array.isArray(claims) ? claims : []
})
const hasAnnotationHistory = computed(() =>
  claimEvidenceList.value.some((claim: any) => (claim.annotation_history || []).length > 0),
)

const verdictTagType = (verdict: string): 'primary' | 'success' | 'warning' | 'info' | 'danger' => {
  const map: Record<string, 'primary' | 'success' | 'warning' | 'info' | 'danger'> = {
    supported: 'success',
    weakly_supported: 'warning',
    unsupported: 'danger',
    contradicted: 'danger',
    unscorable: 'info',
  }
  return map[verdict] || 'info'
}

const verdictLabel = (verdict: string) => {
  const map: Record<string, string> = {
    supported: '有证据支撑',
    weakly_supported: '弱支撑',
    unsupported: '无证据',
    contradicted: '与证据矛盾',
    unscorable: '不可评分',
  }
  return map[verdict] || verdict
}

const loadPending = async () => {
  loading.value = true
  try {
    const params: any = { limit: 50, low_confidence_threshold: filters.value.maxConfidence }
    if (filters.value.source) params.source = filters.value.source
    // Note: run_id filter requires backend support
    const res = await axios.get('/api/eval/scores/pending-review', { params })
    pendingReviews.value = res.data?.data?.items || []
  } catch (error) {
    ElMessage.error('加载待复核列表失败')
  } finally {
    loading.value = false
  }
}

const loadDatasets = async () => {
  try {
    const res = await axios.get('/api/eval/datasets', { params: { limit: 100 } })
    datasets.value = res.data?.data?.items || []
  } catch { /* ignore */ }
}

const openReviewDialog = async (score: any) => {
  selectedScore.value = score
  reviewForm.value = { newScore: score.score, comment: '', action: 'adjust_score', targetDatasetId: '' }
  reviewDialogVisible.value = true
  contextLoading.value = true

  try {
    // Load trial context (4.2)
    const [trialRes, scoresRes] = await Promise.all([
      axios.get(`/api/eval/trials/${score.trial_id}`),
      axios.get(`/api/eval/trials/${score.trial_id}/scores`),
    ])
    trialContext.value = trialRes.data?.data || null
    historicalScores.value = (scoresRes.data?.data?.items || []).filter(
      (s: any) => s.score_id !== score.score_id
    )
  } catch {
    trialContext.value = null
    historicalScores.value = []
  } finally {
    contextLoading.value = false
  }
}

const submitReview = async () => {
  if (!selectedScore.value) return
  submitting.value = true
  try {
    const payload: any = {
      score_id: selectedScore.value.score_id,
      new_score: reviewForm.value.newScore,
      comment: reviewForm.value.comment,
      action: reviewForm.value.action,
    }
    if (reviewForm.value.action === 'reflow' && reviewForm.value.targetDatasetId) {
      payload.target_dataset_id = reviewForm.value.targetDatasetId
    }

    await axios.post('/api/eval/scores/human-review', payload)
    ElMessage.success('复核已提交')
    reviewDialogVisible.value = false
    await loadPending()
  } catch (error: any) {
    ElMessage.error(error?.message || error?.response?.data?.detail || '提交失败')
  } finally {
    submitting.value = false
  }
}

onMounted(() => {
  loadPending()
  loadDatasets()
})
</script>

<style scoped>
.human-review-page { padding: 24px; }
.page-header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 24px; }
.page-title { font-size: 24px; font-weight: 600; display: flex; align-items: center; gap: 12px; margin: 0; }
.card-header { display: flex; justify-content: space-between; align-items: center; }
.section-label { margin-bottom: 8px; font-size: 13px; font-weight: 600; color: var(--el-text-color-primary); }

.json-block {
  margin: 0; padding: 12px; background: var(--el-fill-color-lighter); border-radius: 4px;
  font-size: 13px; font-family: monospace; max-height: 300px; overflow: auto;
  white-space: pre-wrap; word-break: break-all;
}

.context-block { max-height: 200px; }

.output-block {
  padding: 12px; background: var(--el-fill-color-lighter); border-radius: 4px;
  font-size: 13px; line-height: 1.6; max-height: 200px; overflow: auto;
  white-space: pre-wrap; word-break: break-word;
}
</style>
