<template>
  <div class="evolution-proposals">
    <!-- 统计卡片 -->
    <el-row :gutter="16" style="margin-bottom: 20px;">
      <el-col :span="6">
        <el-card shadow="hover">
          <template #header><span>总提案数</span></template>
          <div class="stat-value">{{ stats.total || 0 }}</div>
        </el-card>
      </el-col>
      <el-col :span="6">
        <el-card shadow="hover">
          <template #header><span>待验证</span></template>
          <div class="stat-value warning">{{ stats.by_status?.pending_verify || 0 }}</div>
        </el-card>
      </el-col>
      <el-col :span="6">
        <el-card shadow="hover">
          <template #header><span>已批准</span></template>
          <div class="stat-value success">{{ stats.by_status?.approved || 0 }}</div>
        </el-card>
      </el-col>
      <el-col :span="6">
        <el-card shadow="hover">
          <template #header><span>已发布</span></template>
          <div class="stat-value primary">{{ stats.by_status?.promoted || 0 }}</div>
        </el-card>
      </el-col>
    </el-row>

    <div class="page-actions">
      <el-button type="primary" plain @click="openGovernanceConfig">治理配置</el-button>
    </div>

    <!-- 筛选 -->
    <el-card style="margin-bottom: 16px;">
      <el-form :inline="true">
        <el-form-item label="状态">
          <el-select v-model="filters.status" placeholder="全部" clearable @change="loadProposals">
            <el-option label="草稿" value="draft" />
            <el-option label="待验证" value="pending_verify" />
            <el-option label="验证中" value="verifying" />
            <el-option label="已验证" value="verified" />
            <el-option label="已批准" value="approved" />
            <el-option label="已拒绝" value="rejected" />
            <el-option label="已发布" value="promoted" />
            <el-option label="已停止" value="stopped" />
          </el-select>
        </el-form-item>
        <el-form-item label="Artifact 类型">
          <el-select v-model="filters.artifact_type" placeholder="全部" clearable @change="loadProposals">
            <el-option label="Skill" value="skill" />
            <el-option label="Prompt" value="prompt" />
            <el-option label="Policy" value="policy" />
            <el-option label="Rubric" value="rubric" />
            <el-option label="Case" value="case" />
          </el-select>
        </el-form-item>
        <el-form-item>
          <el-button type="primary" @click="loadProposals">刷新</el-button>
        </el-form-item>
      </el-form>
    </el-card>

    <!-- 列表 -->
    <el-card>
      <el-table :data="proposals" v-loading="loading" stripe style="width: 100%;">
        <el-table-column prop="proposal_id" label="提案 ID" width="160">
          <template #default="{ row }">
            <router-link :to="`/evolution/proposals/${row.proposal_id}`" class="link">
              {{ row.proposal_id }}
            </router-link>
          </template>
        </el-table-column>
        <el-table-column prop="trigger_type" label="触发类型" width="140">
          <template #default="{ row }">
            <el-tag size="small">{{ triggerTypeLabel(row.trigger_type) }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="target_artifact_id" label="目标 Artifact" min-width="180" />
        <el-table-column prop="target_artifact_type" label="类型" width="100">
          <template #default="{ row }">
            <el-tag size="small" type="info">{{ row.target_artifact_type }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="risk_level" label="风险" width="90">
          <template #default="{ row }">
            <el-tag size="small" :type="riskTagType(row.risk_level)">{{ row.risk_level }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="status" label="状态" width="120">
          <template #default="{ row }">
            <el-tag size="small" :type="statusTagType(row.status)">{{ statusLabel(row.status) }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="created_at" label="创建时间" width="180">
          <template #default="{ row }">{{ formatDate(row.created_at) }}</template>
        </el-table-column>
        <el-table-column label="操作" width="100" fixed="right">
          <template #default="{ row }">
            <el-button link type="primary" size="small" @click="$router.push(`/evolution/proposals/${row.proposal_id}`)">
              详情
            </el-button>
          </template>
        </el-table-column>
      </el-table>
    </el-card>

    <el-dialog v-model="governanceDialogVisible" title="自进化治理配置" width="620px">
      <el-form :model="governanceConfig" label-width="150px">
        <el-form-item label="自动化模式">
          <el-select v-model="governanceConfig.automation_mode">
            <el-option label="手动" value="manual" />
            <el-option label="半自动" value="semi-auto" />
            <el-option label="自动" value="auto" />
          </el-select>
        </el-form-item>
        <el-form-item label="趋势回退阈值"><el-input-number v-model="governanceConfig.trigger_regression_threshold" :min="0" :max="1" :step="0.01" /></el-form-item>
        <el-form-item label="Bad Case 阈值"><el-input-number v-model="governanceConfig.trigger_bad_case_count" :min="1" /></el-form-item>
        <el-form-item label="每日验证次数"><el-input-number v-model="governanceConfig.budget_max_runs_per_day" :min="1" /></el-form-item>
        <el-form-item label="每日成本预算"><el-input-number v-model="governanceConfig.daily_cost_budget_usd" :min="0" :precision="4" /></el-form-item>
        <el-form-item label="变更字符预算"><el-input-number v-model="governanceConfig.change_budget_chars" :min="100" /></el-form-item>
        <el-form-item label="相同问题冷却(分钟)"><el-input-number v-model="governanceConfig.cooldown_minutes" :min="0" /></el-form-item>
        <el-form-item label="定时触发 Cron"><el-input v-model="governanceConfig.schedule_cron" placeholder="留空表示关闭" /></el-form-item>
        <el-form-item label="人工审批门禁"><el-switch v-model="governanceConfig.human_gate" /></el-form-item>
        <el-form-item label="必须通过 Smoke Test"><el-switch v-model="governanceConfig.require_smoke_test" /></el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="governanceDialogVisible = false">取消</el-button>
        <el-button type="primary" :loading="governanceSaving" @click="saveGovernanceConfig">保存</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { ElMessage } from 'element-plus'
import { evolutionApi } from '@/api/evolutionClient'

const loading = ref(false)
const proposals = ref<any[]>([])
const stats = ref<any>({})
const filters = ref({ status: '', artifact_type: '' })
const governanceDialogVisible = ref(false)
const governanceSaving = ref(false)
const governanceConfig = ref({
  automation_mode: 'manual',
  trigger_regression_threshold: 0.05,
  trigger_bad_case_count: 10,
  budget_max_runs_per_day: 5,
  human_gate: true,
  schedule_cron: '',
  cooldown_minutes: 60,
  change_budget_chars: 20000,
  daily_cost_budget_usd: 10,
  require_smoke_test: true,
})

const loadProposals = async () => {
  loading.value = true
  try {
    const params: Record<string, any> = {}
    if (filters.value.status) params.status = filters.value.status
    if (filters.value.artifact_type) params.artifact_type = filters.value.artifact_type
    const res = await evolutionApi.getProposals(params)
    proposals.value = res.data?.data?.items || []
    stats.value = { total: res.data?.data?.total || 0, by_status: res.data?.data?.stats || {} }
  } catch (e) {
    console.error('Failed to load proposals', e)
  } finally {
    loading.value = false
  }
}

const triggerTypeLabel = (t: string) => ({
  run_completed: '运行完成', regression: '趋势回退',
  bad_case_threshold: 'Bad Case 阈值', scheduled: '定时触发',
}[t] || t)

const statusLabel = (s: string) => ({
  draft: '草稿', pending_verify: '待验证', verifying: '验证中',
  verified: '已验证', approved: '已批准', rejected: '已拒绝',
  promoted: '已发布', rollback: '已回滚', stopped: '已停止',
}[s] || s)

const statusTagType = (s: string): any => ({
  draft: 'info', pending_verify: 'warning', verifying: '',
  verified: '', approved: 'success', rejected: 'danger',
  promoted: 'success', rollback: 'warning', stopped: 'danger',
}[s] || '')

const riskTagType = (r: string): any => ({
  low: 'success', medium: 'warning', high: 'danger', critical: 'danger',
}[r] || 'info')

const formatDate = (d: string) => d ? new Date(d).toLocaleString('zh-CN') : '-'

const openGovernanceConfig = async () => {
  try {
    const res = await evolutionApi.getConfig()
    const data = res.data?.data || {}
    governanceConfig.value = {
      ...governanceConfig.value,
      ...data,
      ...(data.governance || {}),
    }
    governanceDialogVisible.value = true
  } catch {
    ElMessage.error('加载治理配置失败')
  }
}

const saveGovernanceConfig = async () => {
  governanceSaving.value = true
  try {
    await evolutionApi.updateConfig(governanceConfig.value)
    ElMessage.success('治理配置已保存')
    governanceDialogVisible.value = false
  } catch {
    ElMessage.error('保存治理配置失败')
  } finally {
    governanceSaving.value = false
  }
}

onMounted(loadProposals)
</script>

<style scoped>
.stat-value { font-size: 28px; font-weight: bold; text-align: center; }
.stat-value.warning { color: #e6a23c; }
.stat-value.success { color: #67c23a; }
.stat-value.primary { color: #409eff; }
.link { color: #409eff; text-decoration: none; }
</style>
