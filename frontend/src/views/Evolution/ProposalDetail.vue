<template>
  <div class="proposal-detail" v-loading="loading">
    <el-page-header
      :title="'提案详情: ' + (proposal?.proposal_id || proposalId)"
      @back="$router.push('/evolution/proposals')"
    >
      <template #content>
        <span class="page-header-subtitle">决策导向的变更生命周期视图</span>
      </template>
    </el-page-header>

    <el-alert
      v-if="loadError"
      type="error"
      :closable="false"
      :title="loadError"
      style="margin-top: 16px;"
    />

    <template v-if="proposal">
      <el-card class="section-card" shadow="never">
        <template #header>
          <div class="section-title">
            <span>概览</span>
            <el-tag :type="decisionSummary.statusTagType" size="small">{{ decisionSummary.statusLabel }}</el-tag>
          </div>
        </template>
        <el-alert
          :type="decisionSummary.releaseReady ? 'success' : proposal.forbidden_target ? 'error' : 'warning'"
          :closable="false"
          :title="decisionSummary.releaseReady ? decisionSummary.releaseStateLabel : proposal.forbidden_target ? '目标禁止修改' : decisionSummary.releaseStateLabel"
          :description="proposal.forbidden_target ? '此目标在禁止列表中，不可执行验证或发布。' : decisionSummary.releaseStateHint"
        />
        <el-descriptions :column="3" border style="margin-top: 16px;">
          <el-descriptions-item label="提案 ID">{{ proposal.proposal_id }}</el-descriptions-item>
          <el-descriptions-item label="目标 Artifact">{{ proposal.target_artifact_id }}</el-descriptions-item>
          <el-descriptions-item label="Artifact 类型">{{ decisionSummary.artifactTypeLabel }}</el-descriptions-item>
          <el-descriptions-item label="触发类型">{{ decisionSummary.triggerLabel }}</el-descriptions-item>
          <el-descriptions-item label="风险等级">
            <el-tag :type="decisionSummary.riskTagType" size="small">{{ decisionSummary.riskLabel }}</el-tag>
          </el-descriptions-item>
          <el-descriptions-item label="停止原因">{{ decisionSummary.stopReasonLabel }}</el-descriptions-item>
          <el-descriptions-item label="正式基线版本">{{ decisionSummary.baselineLabel }}</el-descriptions-item>
          <el-descriptions-item label="候选版本">{{ decisionSummary.candidateLabel }}</el-descriptions-item>
          <el-descriptions-item label="Overlay ID">{{ proposal.overlay_id || '尚未创建' }}</el-descriptions-item>
          <el-descriptions-item label="触发 Run" :span="2">
            <router-link
              v-if="proposal.trigger_run_id"
              :to="`/evaluation/runs/${proposal.trigger_run_id}`"
              class="link"
            >
              {{ proposal.trigger_run_id }}
            </router-link>
            <span v-else>-</span>
          </el-descriptions-item>
          <el-descriptions-item label="创建时间">{{ formatDate(proposal.created_at) }}</el-descriptions-item>
          <el-descriptions-item label="变更原因" :span="3">{{ proposal.reason || '—' }}</el-descriptions-item>
          <el-descriptions-item label="回滚策略" :span="3">{{ proposal.rollback_strategy || 'restore_previous_version' }}</el-descriptions-item>
        </el-descriptions>
      </el-card>

      <el-card class="section-card" shadow="never">
        <template #header>
          <div class="section-title">
            <span>变更</span>
            <span v-if="diffSummary.sections.length" class="section-meta">{{ diffSummary.sections.length }} 个影响区域</span>
          </div>
        </template>
        <template v-if="diffSummary.description || diffSummary.sections.length || diffSummary.parameters.length">
          <el-descriptions :column="1" border>
            <el-descriptions-item label="变更描述">{{ diffSummary.description || '—' }}</el-descriptions-item>
            <el-descriptions-item label="影响区域">
              <template v-if="diffSummary.sections.length">
                <el-tag
                  v-for="section in diffSummary.sections"
                  :key="section"
                  size="small"
                  class="tag-gap"
                >
                  {{ section }}
                </el-tag>
              </template>
              <span v-else>未声明具体影响区域</span>
            </el-descriptions-item>
            <el-descriptions-item v-if="diffSummary.parameters.length" label="关键参数">
              <div v-for="item in diffSummary.parameters" :key="item.key" class="parameter-line">
                <span class="parameter-key">{{ item.key }}</span>
                <el-tag size="small" type="info">{{ item.value }}</el-tag>
              </div>
            </el-descriptions-item>
          </el-descriptions>
          <el-collapse v-if="diffSummary.rawAvailable" style="margin-top: 12px;">
            <el-collapse-item title="查看原始 Diff JSON" name="diff">
              <pre class="raw-block">{{ JSON.stringify(proposal.diff, null, 2) }}</pre>
            </el-collapse-item>
          </el-collapse>
        </template>
        <el-empty v-else description="尚未生成候选变更内容" />

        <div v-if="proposal.sample_failure_ids?.length" class="samples-block">
          <span class="section-meta">关联失败样本（{{ proposal.sample_failure_ids.length }}）</span>
          <div>
            <el-tag
              v-for="id in proposal.sample_failure_ids.slice(0, 10)"
              :key="id"
              size="small"
              class="tag-gap"
              type="warning"
            >
              {{ id }}
            </el-tag>
            <span v-if="proposal.sample_failure_ids.length > 10" class="more-text">
              等 {{ proposal.sample_failure_ids.length }} 个
            </span>
          </div>
        </div>
      </el-card>

      <el-card class="section-card" shadow="never">
        <template #header>
          <div class="section-title">
            <span>验证</span>
            <el-button
              v-if="actionStates.canVerify"
              type="primary"
              text
              size="small"
              :loading="verifying"
              @click="startVerification"
            >
              <el-icon><VideoPlay /></el-icon>
              启动验证
            </el-button>
          </div>
        </template>
        <el-alert
          :type="verificationState.state === 'completed' && verification?.gate_result?.passed === true
            ? 'success'
            : verificationState.state === 'failed' || verification?.gate_result?.passed === false
              ? 'error'
              : 'info'"
          :closable="false"
          :title="verificationState.title"
          :description="verificationState.description"
        />
        <template v-if="verification">
          <el-descriptions :column="2" border style="margin-top: 16px;">
            <el-descriptions-item label="验证 ID">{{ verification.verification_id }}</el-descriptions-item>
            <el-descriptions-item label="状态">
              <el-tag size="small" :type="verificationStatusTagType(verification.status)">
                {{ verificationStatusLabel(verification.status) }}
              </el-tag>
            </el-descriptions-item>
            <el-descriptions-item label="基线 Run">
              <router-link :to="`/evaluation/runs/${verification.baseline_run_id}`" class="link">
                {{ verification.baseline_run_id }}
              </router-link>
            </el-descriptions-item>
            <el-descriptions-item label="候选 Run">
              <router-link
                v-if="verification.candidate_run_id"
                :to="`/evaluation/runs/${verification.candidate_run_id}`"
                class="link"
              >
                {{ verification.candidate_run_id }}
              </router-link>
              <span v-else>-</span>
            </el-descriptions-item>
            <el-descriptions-item label="清理状态">
              {{ verification.cleanup_status || '待清理' }}
            </el-descriptions-item>
            <el-descriptions-item label="Overlay">{{ verification.overlay_id || '—' }}</el-descriptions-item>
          </el-descriptions>
          <el-collapse v-if="metrics.length" v-model="expandedMetricGroups" class="metric-groups">
            <el-collapse-item v-for="group in metrics" :key="group.key" :name="group.key">
              <template #title>
                <div class="metric-group-title">
                  <span>{{ group.title }}</span>
                  <span class="section-meta">{{ group.rows.length }} 项</span>
                </div>
              </template>
              <el-table :data="group.rows" size="small" border>
                <el-table-column prop="label" label="指标" min-width="220" />
                <el-table-column prop="baseline" label="基线" min-width="150" />
                <el-table-column prop="candidate" label="候选" min-width="150" />
                <el-table-column prop="conclusion" label="对比结论" min-width="150" />
                <el-table-column label="状态" width="100" fixed="right">
                  <template #default="{ row }">
                    <el-tag size="small" :type="metricTagType(row.status)">
                      {{ row.status === 'pass' ? '通过' : row.status === 'fail' ? '未通过' : '记录' }}
                    </el-tag>
                  </template>
                </el-table-column>
              </el-table>
            </el-collapse-item>
          </el-collapse>
          <el-collapse v-if="comparisonRaw" style="margin-top: 12px;">
            <el-collapse-item title="查看原始对比结果 JSON" name="comparison">
              <pre class="raw-block">{{ comparisonRaw }}</pre>
            </el-collapse-item>
          </el-collapse>
        </template>
        <div v-else class="empty-actions">
          <span>{{ verificationState.description }}</span>
          <el-button size="small" text type="primary" @click="loadProposal">
            <el-icon><Refresh /></el-icon>
            刷新结果
          </el-button>
        </div>
      </el-card>

      <el-card class="section-card" shadow="never">
        <template #header>
          <div class="section-title">
            <span>审批 / 发布</span>
            <span class="section-meta">{{ auditState.title }}</span>
          </div>
        </template>
        <el-alert
          :type="auditState.state === 'available' ? 'success' : auditState.state === 'pending' ? 'warning' : 'info'"
          :closable="false"
          :title="auditState.title"
          :description="auditState.description"
        />
        <div v-if="releaseContent.available" class="release-content">
          <div class="release-content-heading">发布内容</div>
          <el-descriptions :column="3" border>
            <el-descriptions-item label="发布对象">{{ proposal.target_artifact_id }}</el-descriptions-item>
            <el-descriptions-item label="发布类型">{{ decisionSummary.artifactTypeLabel }}</el-descriptions-item>
            <el-descriptions-item label="候选版本">{{ decisionSummary.candidateLabel }}</el-descriptions-item>
            <el-descriptions-item label="内容摘要" :span="3">{{ releaseContent.summary }}</el-descriptions-item>
          </el-descriptions>
          <el-alert
            v-if="releaseContent.diffStatus !== 'complete'"
            type="warning"
            :closable="false"
            title="历史 diff 不完整"
            description="该提案没有保存可靠的 before/after 内容，不能从当前正式版本反推原内容；请重新生成候选后再发布。"
            style="margin-top: 12px;"
          />
          <div v-if="releaseContent.changes.length" class="release-changes">
            <div class="release-content-heading">逐段变更</div>
            <el-collapse>
              <el-collapse-item
                v-for="change in releaseContent.changes"
                :key="change.section"
                :name="change.section"
              >
                <template #title>
                  <span>{{ change.section }}</span>
                  <el-tag size="small" :type="change.operation === 'delete' ? 'danger' : change.operation === 'add' ? 'success' : 'warning'" class="operation-tag">
                    {{ change.operationLabel }}
                  </el-tag>
                </template>
                <el-descriptions :column="1" border size="small">
                  <el-descriptions-item label="原内容">
                    <pre class="content-preview">{{ change.before || '不存在（新增内容）' }}</pre>
                  </el-descriptions-item>
                  <el-descriptions-item label="候选内容">
                    <pre class="content-preview">{{ change.after || '已删除' }}</pre>
                  </el-descriptions-item>
                </el-descriptions>
              </el-collapse-item>
            </el-collapse>
          </div>
          <el-collapse style="margin-top: 12px;">
            <el-collapse-item title="查看本次实际发布内容" name="release-content">
              <pre class="raw-block">{{ releaseContent.raw }}</pre>
            </el-collapse-item>
          </el-collapse>
        </div>
        <el-timeline v-if="auditRecords.length" style="margin-top: 20px;">
          <el-timeline-item
            v-for="(record, index) in auditRecords"
            :key="record.request_id || record.timestamp || index"
            :timestamp="formatDate(record.timestamp)"
            placement="top"
            :type="actionTagType(record.action)"
          >
            <div class="audit-item">
              <div class="audit-line">
                <strong>{{ record.reviewer || '未知审批人' }}</strong>
                <span>{{ actionLabel(record.action) }}</span>
              </div>
              <p v-if="record.comment">{{ record.comment }}</p>
            </div>
          </el-timeline-item>
        </el-timeline>

        <div class="action-bar">
          <el-tooltip :disabled="actionStates.canVerify" :content="actionStates.verifyDisabledReason" placement="top">
            <span>
              <el-button
                type="primary"
                :disabled="!actionStates.canVerify"
                :loading="verifying"
                @click="startVerification"
              >
                <el-icon><VideoPlay /></el-icon>
                启动验证
              </el-button>
            </span>
          </el-tooltip>
          <el-tooltip :disabled="actionStates.canApprove" :content="actionStates.approveDisabledReason" placement="top">
            <span>
              <el-button type="success" :disabled="!actionStates.canApprove" @click="handleApprove">
                <el-icon><Check /></el-icon>
                批准
              </el-button>
            </span>
          </el-tooltip>
          <el-tooltip :disabled="actionStates.canReject" :content=" actionStates.canReject ? '' : '仅验证完成的提案可拒绝'" placement="top">
            <span>
              <el-button type="danger" plain :disabled="!actionStates.canReject" @click="handleReject">
                <el-icon><Close /></el-icon>
                拒绝
              </el-button>
            </span>
          </el-tooltip>
          <el-tooltip :disabled="actionStates.canPromote" :content="actionStates.promoteDisabledReason" placement="top">
            <span>
              <el-button type="primary" :disabled="!actionStates.canPromote" @click="handlePromote">
                <el-icon><Promotion /></el-icon>
                发布到正式版本
              </el-button>
            </span>
          </el-tooltip>
          <el-tooltip :disabled="actionStates.canStop" :content="actionStates.stopDisabledReason" placement="top">
            <span>
              <el-button type="warning" :disabled="!actionStates.canStop" @click="handleStop">
                <el-icon><SwitchButton /></el-icon>
                紧急停止
              </el-button>
            </span>
          </el-tooltip>
        </div>
      </el-card>
    </template>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import { useRoute } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'
import { Check, Close, Promotion, Refresh, SwitchButton, VideoPlay } from '@element-plus/icons-vue'
import { evolutionApi } from '@/api/evolutionClient'
import {
  actionLabel,
  buildDecisionSummary,
  buildDiffSummary,
  getActionStates,
  getAuditState,
  getVerificationState,
  summarizeComparison,
  verificationStatusLabel,
} from './proposalDetail'

const route = useRoute()
const loading = ref(false)
const verifying = ref(false)
const loadError = ref('')
const proposal = ref<Record<string, any> | null>(null)
const verification = ref<Record<string, any> | null>(null)
const auditRecords = ref<Record<string, any>[]>([])

const proposalId = computed(() => route.params.id as string)
const decisionSummary = computed(() => buildDecisionSummary(proposal.value ?? {}, verification.value))
const diffSummary = computed(() => buildDiffSummary(proposal.value?.diff))
const metrics = computed(() => summarizeComparison(verification.value?.comparison_result))
const expandedMetricGroups = ref<string[]>([])
const verificationState = computed(() => getVerificationState(verification.value, proposal.value))
const auditState = computed(() => getAuditState(auditRecords.value, proposal.value))
const actionStates = computed(() => getActionStates(proposal.value, verification.value))
const comparisonRaw = computed(() =>
  verification.value?.comparison_result
    ? JSON.stringify(verification.value.comparison_result, null, 2)
    : '',
)
const releaseContent = computed(() => {
  const diff = proposal.value?.diff || {}
  const structured = proposal.value?.structured_diff || {}
  const content = diff.candidate_snapshot?.content || diff.content || ''
  const raw = content || diff.candidate_snapshot || diff
  const changes = Array.isArray(structured.changes) ? structured.changes.map((change: Record<string, any>) => ({
    section: change.section || change.path || '未命名变更',
    operation: change.operation || 'update',
    operationLabel: ({ add: '新增', update: '修改', delete: '删除', unchanged: '未变化' } as Record<string, string>)[change.operation] || change.operation || '修改',
    before: typeof change.before === 'string' ? change.before : JSON.stringify(change.before, null, 2),
    after: typeof change.after === 'string' ? change.after : JSON.stringify(change.after, null, 2),
  })) : []
  return {
    available: Boolean(Object.keys(diff).length),
    diffStatus: structured.content_diff_status || proposal.value?.content_diff_status || 'legacy_incomplete',
    changes,
    summary: structured.change_description || content || diff.change_description || '候选内容以结构化变更描述为准。',
    raw: typeof raw === 'string' ? raw : JSON.stringify(raw, null, 2),
  }
})

const loadProposal = async () => {
  loading.value = true
  loadError.value = ''
  try {
    const res = await evolutionApi.getProposal(proposalId.value)
    proposal.value = res.data?.data
    const [verificationRes, auditRes] = await Promise.all([
      evolutionApi.getVerification(proposalId.value),
      evolutionApi.getAuditTrail(proposalId.value),
    ])
    const items = verificationRes.data?.data?.items || []
    verification.value = items.length ? items[0] : null
    expandedMetricGroups.value = metrics.value.map(group => group.key)
    auditRecords.value = auditRes.data?.data?.items || []
  } catch (error: any) {
    console.error('Failed to load proposal', error)
    loadError.value = error?.response?.data?.detail || '提案详情加载失败'
  } finally {
    loading.value = false
  }
}

const startVerification = async () => {
  verifying.value = true
  try {
    await evolutionApi.verifyProposal(proposalId.value)
    ElMessage.success('验证已启动')
    setTimeout(loadProposal, 3000)
  } catch (error: any) {
    ElMessage.error(error?.response?.data?.detail || '验证启动失败')
  } finally {
    verifying.value = false
  }
}

const handleApprove = async () => {
  try {
    const { value } = await ElMessageBox.prompt('审批意见（可选）', '批准提案', {
      confirmButtonText: '批准',
      cancelButtonText: '取消',
      inputPlaceholder: '审批意见',
    })
    await evolutionApi.approveProposal(proposalId.value, { comment: value || '' })
    ElMessage.success('已批准')
    await loadProposal()
  } catch {}
}

const handleReject = async () => {
  try {
    const { value } = await ElMessageBox.prompt('拒绝原因', '拒绝提案', {
      confirmButtonText: '拒绝',
      cancelButtonText: '取消',
      inputPlaceholder: '拒绝原因',
      type: 'warning',
    })
    await evolutionApi.rejectProposal(proposalId.value, { comment: value || '' })
    ElMessage.success('已拒绝')
    await loadProposal()
  } catch {}
}

const handlePromote = async () => {
  try {
    await ElMessageBox.confirm('确认将此候选发布为正式版本？', '发布确认', { type: 'warning' })
    await evolutionApi.promoteProposal(proposalId.value)
    ElMessage.success('已发布')
    await loadProposal()
  } catch {}
}

const handleStop = async () => {
  try {
    await ElMessageBox.confirm('确认紧急停止此提案？', '停止确认', { type: 'warning' })
    await evolutionApi.stopProposal(proposalId.value, { reason: 'manual' })
    ElMessage.success('已停止')
    await loadProposal()
  } catch {}
}

const verificationStatusTagType = (status?: string): any => ({
  completed: 'success',
  running: 'warning',
  pending: 'info',
  failed: 'danger',
  cancelled: 'info',
  cleanup_failed: 'danger',
}[status || ''] || 'info')

const actionTagType = (action?: string): any =>
  action === 'approve' ? 'success' : action === 'reject' ? 'danger' : 'primary'

const metricTagType = (status: string): any =>
  status === 'pass' ? 'success' : status === 'fail' ? 'danger' : 'info'

const formatDate = (value?: string) => (value ? new Date(value).toLocaleString('zh-CN') : '-')

onMounted(loadProposal)
</script>

<style scoped>
.link {
  color: #409eff;
  text-decoration: none;
}

.section-card {
  margin-top: 16px;
  border-radius: 8px;
}

.section-title {
  display: flex;
  align-items: center;
  gap: 10px;
  font-weight: 600;
}

.section-meta {
  color: #909399;
  font-size: 12px;
  font-weight: 400;
}

.page-header-subtitle {
  color: #909399;
  font-size: 13px;
}

.tag-gap {
  margin: 2px 6px 2px 0;
}

.parameter-line {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 4px;
}

.parameter-key {
  min-width: 120px;
  font-weight: 500;
}

.raw-block {
  margin: 0;
  padding: 12px;
  max-height: 360px;
  overflow: auto;
  border-radius: 4px;
  background: #f5f7fa;
  font-size: 12px;
}

.samples-block {
  margin-top: 16px;
  padding-top: 14px;
  border-top: 1px solid #ebeef5;
}

.more-text {
  margin-left: 8px;
  color: #909399;
  font-size: 12px;
}

.empty-actions {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-top: 16px;
  padding: 14px;
  border-radius: 4px;
  background: #f5f7fa;
  color: #606266;
}

.audit-item {
  padding: 10px 12px;
  border: 1px solid #ebeef5;
  border-radius: 6px;
  background: #fff;
}

.release-content {
  margin-top: 18px;
  padding-top: 16px;
  border-top: 1px solid #ebeef5;
}

.release-content-heading {
  margin-bottom: 10px;
  font-weight: 600;
}

.release-changes {
  margin-top: 16px;
}

.operation-tag {
  margin-left: 10px;
}

.content-preview {
  margin: 0;
  padding: 10px;
  max-height: 260px;
  overflow: auto;
  white-space: pre-wrap;
  word-break: break-word;
  background: #f5f7fa;
  font-size: 12px;
}

.metric-groups {
  margin-top: 16px;
}

.metric-group-title {
  display: flex;
  align-items: center;
  gap: 10px;
}

.audit-line {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 12px;
}

.audit-item p {
  margin: 8px 0 0;
  color: #606266;
  font-size: 13px;
}

.action-bar {
  display: flex;
  flex-wrap: wrap;
  gap: 10px;
  margin-top: 20px;
  padding-top: 16px;
  border-top: 1px solid #ebeef5;
}
</style>
