<template>
  <div class="run-detail-page">
    <div class="page-header">
      <div>
        <el-button link @click="$router.push('/evaluation/runs')">← 返回列表</el-button>
        <h1 class="page-title">
          <el-icon><VideoPlay /></el-icon>
          评测运行详情
        </h1>
        <p class="run-id">{{ runId }}</p>
      </div>
      <div class="header-actions">
        <el-tag :type="getStatusType(run.status)" size="large" v-if="run.status">
          {{ getStatusLabel(run.status) }}
        </el-tag>
        <el-button v-if="run.status === 'completed'" @click="viewReport">
          <el-icon><Document /></el-icon>
          查看报告
        </el-button>
        <el-button
          v-if="run.status === 'running' || run.status === 'pending'"
          type="danger"
          @click="cancelRun"
        >
          取消运行
        </el-button>
      </div>
    </div>

    <!-- 运行信息卡片 -->
    <el-row :gutter="16" style="margin-bottom: 24px">
      <el-col :span="6">
        <el-card shadow="never" class="info-card">
          <div class="info-label">数据集</div>
          <div class="info-value text-ellipsis">{{ run.dataset_id || '-' }}</div>
        </el-card>
      </el-col>
      <el-col :span="6">
        <el-card shadow="never" class="info-card">
          <div class="info-label">版本</div>
          <div class="info-value">{{ run.dataset_version || '-' }}</div>
        </el-card>
      </el-col>
      <el-col :span="6">
        <el-card shadow="never" class="info-card">
          <div class="info-label">进度</div>
          <div class="info-value">
            <el-progress
              :percentage="progress"
              :status="run.status === 'failed' ? 'exception' : undefined"
            />
            <span style="font-size: 12px; color: var(--el-text-color-secondary)">
              {{ run.completed_trials || 0 }}/{{ totalTrials }} 完成，{{ run.failed_trials || 0 }} 失败
            </span>
          </div>
        </el-card>
      </el-col>
      <el-col :span="6">
        <el-card shadow="never" class="info-card">
          <div class="info-label">创建时间</div>
          <div class="info-value">{{ formatTime(run.created_at) }}</div>
        </el-card>
      </el-col>
    </el-row>

    <el-alert
      v-if="run.status === 'failed'"
      type="error"
      :closable="false"
      show-icon
      style="margin-bottom: 24px"
    >
      <template #title>运行状态：失败</template>
      <div style="display: grid; gap: 4px; margin-top: 6px">
        <div>失败阶段：{{ failureStageLabel }}</div>
        <div>错误代码：{{ run.error_code || '-' }}</div>
        <div v-if="run.error_message">错误原因：{{ run.error_message }}</div>
        <div>Trial 已创建：{{ run.trial_count || 0 }}</div>
      </div>
    </el-alert>

    <!-- 指标摘要 (3.1) -->
    <el-card v-if="metrics" shadow="never" style="margin-bottom: 24px">
      <template #header>
        <span>指标摘要</span>
      </template>
      <el-row :gutter="16">
        <el-col :span="4">
          <div class="metric-item">
            <div class="metric-label">成功率</div>
            <div class="metric-value" :class="{'text-success': metrics.success_rate >= 0.8, 'text-danger': metrics.success_rate < 0.7}">
              {{ (metrics.success_rate * 100).toFixed(1) }}%
            </div>
          </div>
        </el-col>
        <el-col :span="4">
          <div class="metric-item">
            <div class="metric-label">失败率</div>
            <div class="metric-value" :class="{'text-danger': metrics.failure_rate > 0.3}">
              {{ (metrics.failure_rate * 100).toFixed(1) }}%
            </div>
          </div>
        </el-col>
        <el-col :span="4" v-if="run.num_trials_per_case > 1">
          <div class="metric-item">
            <div class="metric-label">质量 pass@{{ metrics.pass_k || 3 }}</div>
            <div class="metric-value">{{ ((metrics.pass_at_k || 0) * 100).toFixed(1) }}%</div>
          </div>
        </el-col>
        <el-col :span="4" v-if="run.num_trials_per_case > 1">
          <div class="metric-item">
            <div class="metric-label">质量 pass^{{ metrics.pass_k || 3 }}</div>
            <div class="metric-value">{{ ((metrics.pass_pow_k || 0) * 100).toFixed(1) }}%</div>
          </div>
        </el-col>
        <el-col :span="4">
          <div class="metric-item">
            <div class="metric-label">平均延迟</div>
            <div class="metric-value">{{ metrics.latency?.mean_ms ? `${Math.round(metrics.latency.mean_ms)}ms` : '-' }}</div>
          </div>
        </el-col>
        <el-col :span="4">
          <div class="metric-item">
            <div class="metric-label">总成本</div>
            <div class="metric-value">${{ (metrics.cost?.total_usd || 0).toFixed(4) }}</div>
          </div>
        </el-col>
      </el-row>

      <!-- 评分维度汇总 -->
      <div v-if="metrics.score_aggregation && Object.keys(metrics.score_aggregation).length" style="margin-top: 16px">
        <div class="metric-label" style="margin-bottom: 8px">评分维度</div>
        <el-row :gutter="12">
          <el-col :span="6" v-for="(scoreData, scoreName) in metrics.score_aggregation" :key="scoreName">
            <div class="score-dimension">
              <span class="score-name">{{ scoreName }}</span>
              <el-tag v-if="scoreData.status !== 'unscorable' && scoreData.status !== 'not_applicable'" :type="scoreData.avg_score >= 0.7 ? 'success' : scoreData.avg_score >= 0.5 ? 'warning' : 'danger'" size="small">
                {{ (scoreData.avg_score * 100).toFixed(0) }}%
              </el-tag>
              <el-tag v-else type="info" size="small">{{ scoreData.status === 'unscorable' ? '不可评分' : '不适用' }}</el-tag>
            </div>
          </el-col>
        </el-row>
      </div>

      <div v-if="metrics.claim_summary?.hallucination_metrics" class="hallucination-summary">
        <div class="metric-label" style="margin-bottom: 8px">幻觉检测指标</div>
        <el-row :gutter="12">
          <el-col :span="5" v-for="item in hallucinationMetricItems" :key="item.key">
            <div class="score-dimension">
              <span class="score-name">{{ item.label }}</span>
              <el-tag v-if="item.value !== null" :type="item.value >= 0.8 ? 'success' : 'warning'" size="small">
                {{ (item.value * 100).toFixed(1) }}%
              </el-tag>
              <el-tag v-else type="info" size="small">暂无真值</el-tag>
            </div>
          </el-col>
        </el-row>
        <el-table
          v-if="metrics.claim_summary.claims?.length"
          :data="metrics.claim_summary.claims"
          size="small"
          stripe
          style="margin-top: 12px"
          max-height="260"
        >
          <el-table-column prop="claim_text" label="Claim" min-width="260" show-overflow-tooltip />
          <el-table-column prop="truth_label" label="真值" width="110" />
          <el-table-column prop="prediction_label" label="预测幻觉" width="110">
            <template #default="{ row }">{{ row.prediction_label === true ? '是' : row.prediction_label === false ? '否' : '-' }}</template>
          </el-table-column>
          <el-table-column prop="hallucination_type" label="类型" width="110" />
          <el-table-column prop="evidence_source" label="证据来源" min-width="160" show-overflow-tooltip />
        </el-table>
      </div>
    </el-card>

    <!-- Trial 列表 -->
    <el-card shadow="never">
      <template #header>
        <div class="card-header">
          <span>Trial 列表（共 {{ trials.length }} 条）</span>
          <el-button size="small" @click="loadTrials">刷新</el-button>
        </div>
      </template>

      <el-table :data="trials" v-loading="loadingTrials" stripe @row-click="openTrialDetail">
        <el-table-column prop="trial_id" label="Trial ID" width="260" show-overflow-tooltip />
        <el-table-column prop="case_id" label="Case ID" width="160" show-overflow-tooltip />
        <el-table-column prop="trial_index" label="#" width="50" />
        <el-table-column prop="status" label="状态" width="100">
          <template #default="{ row }">
            <el-tag :type="getTrialStatusType(row.status)" size="small">
              {{ getTrialStatusLabel(row.status) }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="latency_ms" label="耗时" width="90">
          <template #default="{ row }">
            {{ row.latency_ms ? `${row.latency_ms}ms` : '-' }}
          </template>
        </el-table-column>
        <el-table-column label="评分" width="100">
          <template #default="{ row }">
            <span v-if="row._scoreSummary">
              <el-tag :type="row._scoreSummary.avg >= 0.7 ? 'success' : row._scoreSummary.avg >= 0.5 ? 'warning' : 'danger'" size="small">
                {{ (row._scoreSummary.avg * 100).toFixed(0) }}%
              </el-tag>
            </span>
            <span v-else style="color: var(--el-text-color-placeholder)">-</span>
          </template>
        </el-table-column>
        <el-table-column label="复核" width="80">
          <template #default="{ row }">
            <el-tag v-if="row._reviewed" type="success" size="small">已复核</el-tag>
            <span v-else style="color: var(--el-text-color-placeholder)">-</span>
          </template>
        </el-table-column>
        <el-table-column prop="error_message" label="错误" min-width="160" show-overflow-tooltip>
          <template #default="{ row }">
            <span v-if="row.error_message" style="color: var(--el-color-danger)">{{ row.error_message }}</span>
            <span v-else>-</span>
          </template>
        </el-table-column>
        <el-table-column label="操作" fixed="right" width="140">
          <template #default="{ row }">
            <el-button type="primary" link size="small" @click.stop="openTrialDetail(row)">详情</el-button>
            <el-button type="primary" link size="small" @click.stop="viewTrialTrace(row.trial_id)">Trace</el-button>
          </template>
        </el-table-column>
      </el-table>
    </el-card>

    <!-- Trial 详情抽屉 (3.2) -->
    <el-drawer v-model="trialDetailVisible" title="Trial 详情" size="65%" direction="rtl">
      <div v-if="selectedTrial">
        <!-- 基本信息 -->
        <el-descriptions :column="3" border size="small" style="margin-bottom: 16px">
          <el-descriptions-item label="Trial ID">{{ selectedTrial.trial_id }}</el-descriptions-item>
          <el-descriptions-item label="Case ID">{{ selectedTrial.case_id }}</el-descriptions-item>
          <el-descriptions-item label="序号">#{{ selectedTrial.trial_index }}</el-descriptions-item>
          <el-descriptions-item label="状态">
            <el-tag :type="getTrialStatusType(selectedTrial.status)" size="small">{{ getTrialStatusLabel(selectedTrial.status) }}</el-tag>
          </el-descriptions-item>
          <el-descriptions-item label="耗时">{{ selectedTrial.latency_ms ? `${selectedTrial.latency_ms}ms` : '-' }}</el-descriptions-item>
          <el-descriptions-item label="成本">${{ (selectedTrial.cost_usd || 0).toFixed(4) }}</el-descriptions-item>
          <el-descriptions-item label="Token 用量" :span="3">
            <span v-if="selectedTrial.token_usage && Object.keys(selectedTrial.token_usage).length">
              <el-tag v-for="(val, key) in selectedTrial.token_usage" :key="key" size="small" style="margin-right: 4px">{{ key }}: {{ val }}</el-tag>
            </span>
            <span v-else>-</span>
          </el-descriptions-item>
        </el-descriptions>

        <!-- Final Output (核心改进) -->
        <div class="section-title">Final Output</div>
        <div v-if="selectedTrial.output_data" class="output-block">
          <div v-if="selectedTrial.output_data.content" class="final-output-content">
            {{ selectedTrial.output_data.content }}
          </div>
          <div v-else-if="selectedTrial.output_data.result" class="final-output-content">
            {{ selectedTrial.output_data.result }}
          </div>
          <el-collapse v-else>
            <el-collapse-item title="查看完整输出 JSON">
              <pre class="json-block">{{ JSON.stringify(selectedTrial.output_data, null, 2) }}</pre>
            </el-collapse-item>
          </el-collapse>
        </div>
        <div v-else class="empty-placeholder">无输出数据</div>

        <!-- 错误信息 -->
        <div v-if="selectedTrial.error_message" style="margin-top: 16px">
          <div class="section-title" style="color: var(--el-color-danger)">错误信息</div>
          <el-alert :title="selectedTrial.error_message" type="error" :closable="false" show-icon />
        </div>

        <!-- Skill 评测 -->
        <div style="margin-top: 16px" v-if="trialSkillEval">
          <div class="section-title">Skill 评测</div>
          <el-alert
            v-if="trialSkillEval.status === 'legacy_unverified'"
            title="旧 trial 无 Skill 评测数据，保留原始 trace"
            type="info"
            :closable="false"
            show-icon
          />
          <template v-else>
            <el-descriptions :column="3" border size="small" style="margin-top: 8px">
              <el-descriptions-item label="Route Selected">
                <el-tag :type="trialSkillEval.route_selected ? 'success' : 'info'" size="small">
                  {{ trialSkillEval.route_selected ? '是' : '否' }}
                </el-tag>
              </el-descriptions-item>
              <el-descriptions-item label="Skill Effective">
                <el-tag :type="trialSkillEval.skill_effective ? 'success' : 'info'" size="small">
                  {{ trialSkillEval.skill_effective ? '是' : '否' }}
                </el-tag>
              </el-descriptions-item>
              <el-descriptions-item label="Skill 事件数">{{ trialSkillEval.events?.length || 0 }}</el-descriptions-item>
            </el-descriptions>
            <el-table
              v-if="trialSkillEval.scores?.length"
              :data="trialSkillEval.scores"
              size="small"
              stripe
              style="margin-top: 12px"
            >
              <el-table-column prop="score_name" label="维度" width="150" />
              <el-table-column prop="score" label="分数" width="90">
                <template #default="{ row }">{{ (row.score * 100).toFixed(0) }}%</template>
              </el-table-column>
              <el-table-column prop="status" label="状态" width="120" />
              <el-table-column prop="reason" label="原因" min-width="220" show-overflow-tooltip />
            </el-table>
            <el-collapse v-if="trialSkillEval.skill_eval_snapshot" style="margin-top: 8px">
              <el-collapse-item title="Skill 评测配置">
                <pre class="json-block">{{ JSON.stringify(trialSkillEval.skill_eval_snapshot, null, 2) }}</pre>
              </el-collapse-item>
            </el-collapse>
          </template>
        </div>

        <!-- 输入数据 -->
        <div style="margin-top: 16px">
          <div class="section-title">输入数据</div>
          <pre class="json-block">{{ JSON.stringify(selectedTrial.input_data, null, 2) }}</pre>
        </div>

        <!-- 评分结果 -->
        <div style="margin-top: 16px" v-if="trialScores.length">
          <div class="section-title">评分结果</div>
          <el-table :data="trialScores" size="small" stripe>
            <el-table-column prop="score_name" label="维度" width="140" />
            <el-table-column prop="score" label="分数" width="80">
              <template #default="{ row }">{{ (row.score * 100).toFixed(0) }}%</template>
            </el-table-column>
            <el-table-column prop="status" label="状态" width="120">
              <template #default="{ row }">
                <el-tag :type="getScoreStatusType(row.status)" size="small">{{ row.status || (row.passed ? 'passed' : 'failed') }}</el-tag>
              </template>
            </el-table-column>
            <el-table-column prop="source" label="来源" width="100" />
            <el-table-column prop="reason" label="原因" min-width="200" show-overflow-tooltip />
            <el-table-column label="复核" width="80">
              <template #default="{ row }">
                <el-tag v-if="row.human_reviewed" type="success" size="small">已复核</el-tag>
              </template>
            </el-table-column>
          </el-table>
        </div>

        <!-- Trace 入口 -->
        <div style="margin-top: 16px">
          <el-button @click="viewTrialTrace(selectedTrial.trial_id)">
            <el-icon><List /></el-icon>
            查看 Trace
          </el-button>
        </div>

        <!-- 决策链与解释校验 -->
        <div style="margin-top: 16px">
          <div class="section-title">决策链与解释校验</div>
          <el-alert
            v-if="trialExplainability?.status === 'legacy_unverified' || trialExplainability?.status === 'unavailable'"
            :title="trialExplainability?.status === 'legacy_unverified' ? '旧 trial 无决策链，保留原始 trace' : '暂无决策链数据'"
            type="info"
            :closable="false"
            show-icon
          />
          <template v-else-if="trialExplainability">
            <el-table :data="trialExplainability.decision_chain || []" size="small" stripe style="margin-top: 8px">
              <el-table-column prop="scenario" label="场景" min-width="140" show-overflow-tooltip />
              <el-table-column prop="selected_option" label="选择" width="120" show-overflow-tooltip />
              <el-table-column label="候选" min-width="160" show-overflow-tooltip>
                <template #default="{ row }">{{ formatCandidates(row.candidates) }}</template>
              </el-table-column>
              <el-table-column label="依据" min-width="180" show-overflow-tooltip>
                <template #default="{ row }">{{ formatDecisionReason(row.selection_reason) }}</template>
              </el-table-column>
              <el-table-column prop="status" label="状态" width="110" />
              <el-table-column prop="risk_level" label="风险" width="80" />
            </el-table>
            <el-descriptions v-if="trialExplainability.validations?.length" :column="3" border size="small" style="margin-top: 12px">
              <el-descriptions-item v-for="item in trialExplainability.validations" :key="item.validation_id" :label="item.status" :span="1">
                {{ item.reason }}
              </el-descriptions-item>
            </el-descriptions>
            <el-table
              v-if="trialExplainability.explanations?.length"
              :data="trialExplainability.explanations"
              size="small"
              stripe
              style="margin-top: 12px"
            >
              <el-table-column prop="version" label="版本" width="90" />
              <el-table-column label="用户解释" min-width="260">
                <template #default="{ row }">{{ row.user?.text || '-' }}</template>
              </el-table-column>
              <el-table-column label="业务解释" min-width="260">
                <template #default="{ row }">{{ row.business?.text || '-' }}</template>
              </el-table-column>
            </el-table>
          </template>
        </div>
      </div>
    </el-drawer>

    <!-- Trace 查看抽屉 -->
    <el-drawer v-model="traceDrawerVisible" title="Trial Trace" size="60%" direction="rtl">
      <div v-if="traceLoading" v-loading="true" style="height: 200px"></div>
      <div v-else-if="traceEvents.length === 0" style="text-align: center; padding: 40px; color: var(--el-text-color-secondary)">
        暂无 trace 事件
      </div>
      <template v-else>
        <!-- 按类型分组展示 -->
        <div v-for="group in groupedTraceEvents" :key="group.type" style="margin-bottom: 16px">
          <div class="trace-group-title">
            <el-tag :type="getTraceEventTagType(group.type)" size="small">{{ getTraceGroupLabel(group.type) }}</el-tag>
            <span style="font-size: 12px; color: var(--el-text-color-secondary)">({{ group.events.length }})</span>
          </div>
          <el-timeline>
            <el-timeline-item
              v-for="event in group.events"
              :key="event.event_id"
              :timestamp="formatTime(event.timestamp)"
              :type="getTraceEventType(event.event_type)"
              placement="top"
            >
              <el-card shadow="never" class="trace-event-card">
                <div class="trace-event-header">
                  <span class="trace-sequence">#{{ event.sequence }}</span>
                </div>
                <pre class="trace-data">{{ JSON.stringify(event.data, null, 2) }}</pre>
              </el-card>
            </el-timeline-item>
          </el-timeline>
        </div>
      </template>
    </el-drawer>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, onUnmounted } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'
import { VideoPlay, Document, List } from '@element-plus/icons-vue'
import { evalApiClient as axios } from '@/api/evalClient'

const route = useRoute()
const router = useRouter()

const runId = computed(() => route.params.id as string)
const run = ref<any>({})
const trials = ref<any[]>([])
const loadingTrials = ref(false)
const metrics = ref<any>(null)
const hallucinationMetricItems = computed(() => {
  const data = metrics.value?.claim_summary?.hallucination_metrics || {}
  return [
    { key: 'precision', label: 'Precision', value: data.precision ?? null },
    { key: 'recall', label: 'Recall', value: data.recall ?? null },
    { key: 'f1', label: 'F1', value: data.f1 ?? null },
  ]
})

// Trial detail
const trialDetailVisible = ref(false)
const selectedTrial = ref<any>(null)
const trialScores = ref<any[]>([])
const trialExplainability = ref<any>(null)
const trialSkillEval = ref<any>(null)

// Trace
const traceDrawerVisible = ref(false)
const traceEvents = ref<any[]>([])
const traceLoading = ref(false)

// Auto-refresh
let refreshTimer: ReturnType<typeof setInterval> | null = null

const totalTrials = computed(() => {
  return (run.value.total_cases || 0) * (run.value.num_trials_per_case || 1)
})

const failureStageLabel = computed(() => {
  const labels: Record<string, string> = {
    snapshot_validation: '快照校验',
    case_validation: '用例校验',
    runtime: '运行阶段',
    scoring: '评分阶段',
    aggregation: '聚合阶段',
    storage: '存储阶段',
    none: '无'
  }
  return labels[run.value.failure_stage || 'runtime'] || run.value.failure_stage || 'runtime'
})

const progress = computed(() => {
  if (!totalTrials.value) return 0
  const completed = (run.value.completed_trials || 0) + (run.value.failed_trials || 0)
  return Math.round((completed / totalTrials.value) * 100)
})

const groupedTraceEvents = computed(() => {
  const groups: Record<string, any[]> = {}
  for (const event of traceEvents.value) {
    const type = event.event_type || 'other'
    if (!groups[type]) groups[type] = []
    groups[type].push(event)
  }
  return Object.entries(groups)
    .sort(([a], [b]) => a.localeCompare(b))
    .map(([type, events]) => ({ type, events }))
})

const loadRun = async () => {
  try {
    const res = await axios.get(`/api/eval/runs/${runId.value}`)
    run.value = res.data?.data || {}
  } catch (error) {
    ElMessage.error('加载运行详情失败')
  }
}

const loadMetrics = async () => {
  try {
    const res = await axios.get(`/api/eval/runs/${runId.value}/metrics`, { params: { k: 3 } })
    metrics.value = res.data?.data || null
  } catch (error) {
    console.warn('Failed to load metrics:', error)
  }
}

const loadTrials = async () => {
  loadingTrials.value = true
  try {
    const res = await axios.get(`/api/eval/runs/${runId.value}/trials`)
    const items = res.data?.data?.items || []

    // Load score summaries for each trial
    for (const trial of items) {
      try {
        const scoreRes = await axios.get(`/api/eval/trials/${trial.trial_id}/scores/summary`)
        const summary = scoreRes.data?.data || {}
        trial._scoreSummary = { avg: summary.average_score || 0 }
        trial._reviewed = (summary.passed_count || 0) > 0 // approximate
      } catch {
        trial._scoreSummary = null
        trial._reviewed = false
      }
    }

    trials.value = items
  } catch (error) {
    ElMessage.error('加载 trial 列表失败')
  } finally {
    loadingTrials.value = false
  }
}

const openTrialDetail = async (trial: any) => {
  selectedTrial.value = trial
  trialDetailVisible.value = true
  trialExplainability.value = null
  trialSkillEval.value = null

  // Load scores for this trial
  try {
    const res = await axios.get(`/api/eval/trials/${trial.trial_id}/scores`)
    trialScores.value = res.data?.data?.items || []
  } catch {
    trialScores.value = []
  }

  try {
    const res = await axios.get(`/api/eval/trials/${trial.trial_id}/explainability`)
    trialExplainability.value = res.data?.data || null
  } catch {
    trialExplainability.value = { status: 'unavailable' }
  }

  try {
    const res = await axios.get(`/api/eval/trials/${trial.trial_id}/skill-eval`)
    trialSkillEval.value = res.data?.data || { status: 'legacy_unverified' }
  } catch {
    trialSkillEval.value = { status: 'legacy_unverified' }
  }
}

const viewTrialTrace = async (trialId: string) => {
  traceDrawerVisible.value = true
  traceLoading.value = true
  traceEvents.value = []
  try {
    const res = await axios.get(`/api/eval/trials/${trialId}/trace`, { params: { limit: 200 } })
    traceEvents.value = res.data?.data?.items || []
  } catch (error) {
    ElMessage.error('加载 trace 失败')
  } finally {
    traceLoading.value = false
  }
}

const viewReport = () => {
  router.push(`/evaluation/runs/${runId.value}/report`)
}

const cancelRun = async () => {
  try {
    await ElMessageBox.confirm('确定要取消这个运行吗？', '确认取消', { type: 'warning' })
    await axios.post(`/api/eval/runs/${runId.value}/cancel`)
    ElMessage.success('已取消')
    await loadRun()
    await loadTrials()
  } catch {
    // user cancelled
  }
}

// Auto-refresh when running
const startAutoRefresh = () => {
  refreshTimer = setInterval(async () => {
    const status = run.value.status
    if (status === 'running' || status === 'pending') {
      await Promise.all([loadRun(), loadTrials()])
      if (run.value.status === 'completed' || run.value.status === 'failed') {
        await loadMetrics()
        stopAutoRefresh()
      }
    } else {
      stopAutoRefresh()
    }
  }, 5000)
}

const stopAutoRefresh = () => {
  if (refreshTimer) {
    clearInterval(refreshTimer)
    refreshTimer = null
  }
}

// Utility functions
const getStatusType = (status: string): 'primary' | 'success' | 'warning' | 'info' | 'danger' => {
  const map: Record<string, 'primary' | 'success' | 'warning' | 'info' | 'danger'> = { pending: 'info', running: 'warning', completed: 'success', failed: 'danger', cancelled: 'info' }
  return map[status] || 'info'
}

const getStatusLabel = (status: string) => {
  const map: Record<string, string> = { pending: '等待中', running: '运行中', completed: '已完成', failed: '失败', cancelled: '已取消' }
  return map[status] || status
}

const getTrialStatusType = (status: string): 'primary' | 'success' | 'warning' | 'info' | 'danger' => {
  const map: Record<string, 'primary' | 'success' | 'warning' | 'info' | 'danger'> = { pending: 'info', running: 'warning', completed: 'success', failed: 'danger', timeout: 'danger', cancelled: 'info' }
  return map[status] || 'info'
}

const getTrialStatusLabel = (status: string) => {
  const map: Record<string, string> = { pending: '等待中', running: '运行中', completed: '已完成', failed: '失败', timeout: '超时', cancelled: '已取消' }
  return map[status] || status
}

const getScoreStatusType = (status: string): 'primary' | 'success' | 'warning' | 'info' | 'danger' => {
  const map: Record<string, 'primary' | 'success' | 'warning' | 'info' | 'danger'> = {
    passed: 'success', failed: 'danger', skipped: 'info', not_configured: 'warning', error: 'danger', unscorable: 'info', not_applicable: 'info',
  }
  return map[status] || 'info'
}

const getTraceEventType = (eventType: string) => {
  if (eventType === 'error') return 'danger'
  if (eventType === 'llm_call' || eventType === 'tool_call') return 'primary'
  if (eventType === 'lifecycle') return 'info'
  if (eventType === 'streaming') return 'success'
  return 'primary'
}

const getTraceEventTagType = (eventType: string): 'primary' | 'success' | 'warning' | 'info' | 'danger' => {
  const map: Record<string, 'primary' | 'success' | 'warning' | 'info' | 'danger'> = {
    error: 'danger',
    llm_call: 'primary',
    tool_call: 'warning',
    decision: 'success',
    lifecycle: 'info',
    streaming: 'success',
    evidence: 'success',
    retrieval: 'success',
    citation: 'success',
    skill: 'warning',
    swarm: 'primary',
  }
  return map[eventType] || 'info'
}

const getTraceGroupLabel = (eventType: string) => {
  const map: Record<string, string> = {
    llm_call: '🤖 LLM 调用',
    tool_call: '🔧 Tool 调用',
    decision: '🧭 Decision',
    evidence: '📎 Evidence',
    retrieval: '🔍 Retrieval',
    citation: '📝 Citation',
    skill: '⚡ Skill',
    swarm: '🐝 Swarm',
    lifecycle: '♻️ Lifecycle',
    streaming: '📡 Streaming',
    error: '❌ Error',
  }
  return map[eventType] || eventType
}

const formatCandidates = (candidates: any[]) => {
  if (!Array.isArray(candidates) || candidates.length === 0) return '未提供候选'
  return candidates.map(item => item?.label || item?.option_id || String(item)).join('、')
}

const formatDecisionReason = (reason?: string) => {
  if (!reason) return '未提供依据'
  if (reason === 'candidates_unavailable') return '未提供候选'
  if (reason === 'reason_unavailable') return '未提供依据'
  return reason
}

const formatTime = (isoString: string) => {
  if (!isoString) return '-'
  return new Date(isoString).toLocaleString('zh-CN')
}

onMounted(async () => {
  await Promise.all([loadRun(), loadTrials(), loadMetrics()])
  if (run.value.status === 'running' || run.value.status === 'pending') {
    startAutoRefresh()
  }
})

onUnmounted(() => {
  stopAutoRefresh()
})
</script>

<style scoped>
.run-detail-page { padding: 24px; }

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

.header-actions { display: flex; align-items: center; gap: 12px; }

.run-id { margin: 0; font-size: 13px; color: var(--el-text-color-secondary); font-family: monospace; }

.info-card { height: 100px; }
.info-label { font-size: 12px; color: var(--el-text-color-secondary); margin-bottom: 8px; }
.info-value { font-size: 16px; font-weight: 600; color: var(--el-text-color-primary); }
.text-ellipsis { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }

.metric-item { text-align: center; padding: 8px 0; }
.metric-label { font-size: 12px; color: var(--el-text-color-secondary); margin-bottom: 4px; }
.metric-value { font-size: 20px; font-weight: 700; }
.text-success { color: var(--el-color-success); }
.text-danger { color: var(--el-color-danger); }

.score-dimension { display: flex; align-items: center; gap: 8px; padding: 4px 0; }
.score-name { font-size: 13px; color: var(--el-text-color-regular); }

.card-header { display: flex; justify-content: space-between; align-items: center; }

.section-title { font-size: 14px; font-weight: 600; margin-bottom: 8px; color: var(--el-text-color-primary); }

.final-output-content {
  padding: 16px;
  background: var(--el-fill-color-lighter);
  border-radius: 6px;
  font-size: 14px;
  line-height: 1.6;
  white-space: pre-wrap;
  word-break: break-word;
  max-height: 400px;
  overflow: auto;
}

.output-block { margin-top: 4px; }
.empty-placeholder { padding: 24px; text-align: center; color: var(--el-text-color-placeholder); }

.json-block {
  margin: 0; padding: 12px; background: var(--el-fill-color-lighter); border-radius: 4px;
  font-size: 13px; font-family: monospace; max-height: 300px; overflow: auto;
  white-space: pre-wrap; word-break: break-all;
}

.trace-group-title { display: flex; align-items: center; gap: 8px; margin-bottom: 8px; font-weight: 600; }
.trace-event-card { padding: 0; }
.trace-event-header { display: flex; align-items: center; gap: 8px; margin-bottom: 8px; }
.trace-sequence { font-size: 12px; color: var(--el-text-color-secondary); font-family: monospace; }
.trace-data {
  margin: 0; padding: 8px; background: var(--el-fill-color-lighter); border-radius: 4px;
  font-size: 12px; font-family: monospace; max-height: 300px; overflow: auto;
  white-space: pre-wrap; word-break: break-all;
}
</style>
