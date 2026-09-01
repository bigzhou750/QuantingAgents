<template>
  <div class="proposal-detail" v-loading="loading">
    <el-page-header @back="$router.push('/evolution/proposals')" :title="'提案详情: ' + proposal?.proposal_id" />

    <template v-if="proposal">
      <!-- 基本信息 -->
      <el-card style="margin-top: 16px;">
        <template #header><span>基本信息</span></template>
        <el-descriptions :column="3" border>
          <el-descriptions-item label="提案 ID">{{ proposal.proposal_id }}</el-descriptions-item>
          <el-descriptions-item label="状态">
            <el-tag :type="statusTagType(proposal.status)">{{ statusLabel(proposal.status) }}</el-tag>
          </el-descriptions-item>
          <el-descriptions-item label="风险等级">
            <el-tag :type="riskTagType(proposal.risk_level)">{{ proposal.risk_level }}</el-tag>
          </el-descriptions-item>
          <el-descriptions-item label="触发类型">{{ triggerTypeLabel(proposal.trigger_type) }}</el-descriptions-item>
          <el-descriptions-item label="目标 Artifact">{{ proposal.target_artifact_id }}</el-descriptions-item>
          <el-descriptions-item label="Artifact 类型">{{ proposal.target_artifact_type }}</el-descriptions-item>
          <el-descriptions-item label="触发 Run">
            <router-link v-if="proposal.trigger_run_id" :to="`/evaluation/runs/${proposal.trigger_run_id}`" class="link">
              {{ proposal.trigger_run_id }}
            </router-link>
            <span v-else>-</span>
          </el-descriptions-item>
          <el-descriptions-item label="创建时间">{{ formatDate(proposal.created_at) }}</el-descriptions-item>
          <el-descriptions-item label="回滚策略">{{ proposal.rollback_strategy }}</el-descriptions-item>
          <el-descriptions-item label="变更原因" :span="3">{{ proposal.reason }}</el-descriptions-item>
          <el-descriptions-item v-if="proposal.forbidden_target" label="⚠️ 禁止修改" :span="3">
            <el-alert type="error" :closable="false" title="此目标在禁止列表中，不可执行验证或发布" />
          </el-descriptions-item>
        </el-descriptions>
      </el-card>

      <!-- 候选 Diff -->
      <el-card style="margin-top: 16px;">
        <template #header><span>候选变更</span></template>
        <el-descriptions :column="1" border>
          <el-descriptions-item label="变更描述">{{ proposal.diff?.change_description || '-' }}</el-descriptions-item>
          <el-descriptions-item label="影响区域">
            <el-tag v-for="s in (proposal.diff?.sections_affected || [])" :key="s" size="small" style="margin-right: 4px;">{{ s }}</el-tag>
          </el-descriptions-item>
        </el-descriptions>
        <div v-if="proposal.diff" style="margin-top: 12px;">
          <strong>Diff 详情:</strong>
          <pre class="diff-block">{{ JSON.stringify(proposal.diff, null, 2) }}</pre>
        </div>
      </el-card>

      <!-- 关联样本 -->
      <el-card v-if="proposal.sample_failure_ids?.length" style="margin-top: 16px;">
        <template #header><span>关联失败样本 ({{ proposal.sample_failure_ids.length }})</span></template>
        <el-tag v-for="id in proposal.sample_failure_ids.slice(0, 10)" :key="id" size="small" style="margin: 2px 4px;">{{ id }}</el-tag>
        <span v-if="proposal.sample_failure_ids.length > 10" style="color: #909399; margin-left: 8px;">...等 {{ proposal.sample_failure_ids.length }} 个</span>
      </el-card>

      <!-- 验证结果 -->
      <el-card style="margin-top: 16px;">
        <template #header>
          <div style="display: flex; justify-content: space-between; align-items: center;">
            <span>验证结果</span>
            <el-button v-if="canVerify" type="primary" size="small" :loading="verifying" @click="startVerification">
              启动验证
            </el-button>
          </div>
        </template>
        <div v-if="verification" class="verification-result">
          <el-descriptions :column="2" border>
            <el-descriptions-item label="验证 ID">{{ verification.verification_id }}</el-descriptions-item>
            <el-descriptions-item label="状态">
              <el-tag :type="verification.status === 'completed' ? 'success' : 'danger'">{{ verification.status }}</el-tag>
            </el-descriptions-item>
            <el-descriptions-item label="基线 Run">
              <router-link :to="`/evaluation/runs/${verification.baseline_run_id}`" class="link">{{ verification.baseline_run_id }}</router-link>
            </el-descriptions-item>
            <el-descriptions-item label="候选 Run">
              <router-link v-if="verification.candidate_run_id" :to="`/evaluation/runs/${verification.candidate_run_id}`" class="link">{{ verification.candidate_run_id }}</router-link>
              <span v-else>-</span>
            </el-descriptions-item>
          </el-descriptions>
          <div v-if="verification.comparison_result && !verification.comparison_result.error" style="margin-top: 12px;">
            <h4>指标对比</h4>
            <pre class="diff-block">{{ JSON.stringify(verification.comparison_result, null, 2) }}</pre>
          </div>
          <el-alert v-if="verification.comparison_result?.error" type="error" :title="verification.comparison_result.error" :closable="false" />
        </div>
        <el-empty v-else description="暂无验证记录" />
      </el-card>

      <!-- 审批审计 -->
      <el-card style="margin-top: 16px;">
        <template #header><span>审批记录</span></template>
        <el-timeline v-if="auditRecords.length">
          <el-timeline-item v-for="(r, i) in auditRecords" :key="i" :timestamp="formatDate(r.timestamp)" placement="top"
            :type="r.action === 'approve' ? 'success' : r.action === 'reject' ? 'danger' : 'primary'">
            <el-card shadow="never">
              <strong>{{ r.reviewer }}</strong> - {{ actionLabel(r.action) }}
              <p v-if="r.comment" style="margin-top: 4px; color: #606266;">{{ r.comment }}</p>
            </el-card>
          </el-timeline-item>
        </el-timeline>
        <el-empty v-else description="暂无审批记录" />

        <!-- 操作按钮 -->
        <div v-if="canApprove" style="margin-top: 16px; display: flex; gap: 8px;">
          <el-button type="success" @click="handleApprove">✓ 批准</el-button>
          <el-button type="danger" @click="handleReject">✗ 拒绝</el-button>
        </div>
        <div v-if="canPromote" style="margin-top: 16px;">
          <el-button type="primary" @click="handlePromote">🚀 发布到正式版本</el-button>
        </div>
        <div v-if="canStop" style="margin-top: 16px;">
          <el-button type="warning" @click="handleStop">⏹ 紧急停止</el-button>
        </div>
      </el-card>
    </template>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import { useRoute } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'
import { evolutionApi } from '@/api/evolutionClient'

const route = useRoute()
const loading = ref(false)
const verifying = ref(false)
const proposal = ref<any>(null)
const verification = ref<any>(null)
const auditRecords = ref<any[]>([])

const proposalId = computed(() => route.params.id as string)

const canVerify = computed(() =>
  proposal.value && ['pending_verify', 'draft'].includes(proposal.value.status) && !proposal.value.forbidden_target
)
const canApprove = computed(() =>
  proposal.value && ['verified'].includes(proposal.value.status)
)
const canPromote = computed(() =>
  proposal.value && proposal.value.status === 'approved'
)
const canStop = computed(() =>
  proposal.value && !['promoted', 'stopped', 'rejected'].includes(proposal.value.status)
)

const loadProposal = async () => {
  loading.value = true
  try {
    const res = await evolutionApi.getProposal(proposalId.value)
    proposal.value = res.data?.data
    // 加载验证和审计
    const [vRes, aRes] = await Promise.all([
      evolutionApi.getVerification(proposalId.value),
      evolutionApi.getAuditTrail(proposalId.value),
    ])
    const items = vRes.data?.data?.items || []
    verification.value = items.length ? items[0] : null
    auditRecords.value = aRes.data?.data?.items || []
  } catch (e) {
    console.error('Failed to load proposal', e)
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
  } catch (e: any) {
    ElMessage.error(e?.response?.data?.detail || '验证启动失败')
  } finally {
    verifying.value = false
  }
}

const handleApprove = async () => {
  try {
    const { value } = await ElMessageBox.prompt('审批意见（可选）', '批准提案', { confirmButtonText: '批准', cancelButtonText: '取消', inputPlaceholder: '审批意见' })
    await evolutionApi.approveProposal(proposalId.value, { comment: value || '' })
    ElMessage.success('已批准')
    loadProposal()
  } catch {}
}

const handleReject = async () => {
  try {
    const { value } = await ElMessageBox.prompt('拒绝原因', '拒绝提案', { confirmButtonText: '拒绝', cancelButtonText: '取消', inputPlaceholder: '拒绝原因', type: 'warning' })
    await evolutionApi.rejectProposal(proposalId.value, { comment: value || '' })
    ElMessage.success('已拒绝')
    loadProposal()
  } catch {}
}

const handlePromote = async () => {
  try {
    await ElMessageBox.confirm('确认将此候选发布为正式版本？', '发布确认', { type: 'warning' })
    await evolutionApi.promoteProposal(proposalId.value)
    ElMessage.success('已发布')
    loadProposal()
  } catch {}
}

const handleStop = async () => {
  try {
    await ElMessageBox.confirm('确认紧急停止此提案？', '停止确认', { type: 'warning' })
    await evolutionApi.stopProposal(proposalId.value, { reason: 'manual' })
    ElMessage.success('已停止')
    loadProposal()
  } catch {}
}

// Labels & helpers
const statusLabel = (s: string) => ({ draft: '草稿', pending_verify: '待验证', verifying: '验证中', verified: '已验证', approved: '已批准', rejected: '已拒绝', promoted: '已发布', stopped: '已停止' }[s] || s)
const statusTagType = (s: string): any => ({ draft: 'info', pending_verify: 'warning', verified: '', approved: 'success', rejected: 'danger', promoted: 'success', stopped: 'danger' }[s] || '')
const riskTagType = (r: string): any => ({ low: 'success', medium: 'warning', high: 'danger', critical: 'danger' }[r] || 'info')
const triggerTypeLabel = (t: string) => ({ run_completed: '运行完成', regression: '趋势回退', bad_case_threshold: 'Bad Case 阈值', scheduled: '定时触发' }[t] || t)
const actionLabel = (a: string) => ({ approve: '批准', reject: '拒绝', comment: '评论' }[a] || a)
const formatDate = (d: string) => d ? new Date(d).toLocaleString('zh-CN') : '-'

onMounted(loadProposal)
</script>

<style scoped>
.link { color: #409eff; text-decoration: none; }
.diff-block { background: #f5f7fa; padding: 12px; border-radius: 4px; font-size: 12px; overflow-x: auto; max-height: 400px; }
</style>
