<template>
  <div class="post-release-observation-page">
    <div class="page-header">
      <h1 class="page-title">发布后观测</h1>
      <p>选择已发布回执，提交观测指标并查看后续动作候选。</p>
    </div>

    <el-card shadow="never" class="observe-card">
      <template #header>
        <span>提交观测</span>
      </template>
      <el-form label-width="180px" style="max-width: 720px">
        <el-form-item label="已发布回执">
          <el-select v-model="form.receipt_id" filterable placeholder="选择 receipt_id" style="width: 100%">
            <el-option
              v-for="receipt in receipts"
              :key="receipt.receipt_id"
              :label="receipt.receipt_id"
              :value="receipt.receipt_id"
            />
          </el-select>
        </el-form-item>
        <el-form-item label="成功率">
          <el-slider v-model="form.success_rate" :min="0" :max="1" :step="0.05" show-input />
        </el-form-item>
        <el-form-item label="安全分">
          <el-slider v-model="form.safety" :min="0" :max="1" :step="0.05" show-input />
        </el-form-item>
        <el-form-item label="证据质量">
          <el-slider v-model="form.evidence_quality" :min="0" :max="1" :step="0.05" show-input />
        </el-form-item>
        <el-form-item label="平均延迟 (ms)">
          <el-input-number v-model="form.latency_mean_ms" :min="0" :max="3600000" />
        </el-form-item>
        <el-form-item label="总成本 (USD)">
          <el-input-number v-model="form.cost_total_usd" :min="0" :max="100000" :step="0.1" />
        </el-form-item>
        <el-form-item>
          <el-button type="primary" :loading="submitting" @click="submitObservation">提交观测</el-button>
        </el-form-item>
      </el-form>

      <el-result
        v-if="result"
        :icon="result.rollback_suggestion ? 'warning' : 'success'"
        :title="result.rollback_suggestion ? '建议回滚' : '观测通过'"
        sub-title="请查看失败检查项和系统生成的后续动作。"
      >
        <template #extra>
          <div v-if="result.failures?.length" class="failure-list">
            <el-tag v-for="item in result.failures" :key="item.name" type="warning" size="small" style="margin-right: 6px">
              {{ item.name }}
            </el-tag>
          </div>
          <div v-if="result.rollback_suggestion" class="rollback-tip">
            回滚仍使用 Artifact 管理能力，本页不执行回滚。
          </div>
        </template>
      </el-result>
    </el-card>

    <el-card shadow="never" class="observe-card">
      <template #header>
        <span>后续动作</span>
      </template>
      <el-table :data="actions" size="small" stripe v-loading="loadingActions">
        <el-table-column prop="action_id" label="Action ID" min-width="220" show-overflow-tooltip />
        <el-table-column prop="action_type" label="类型" width="110" />
        <el-table-column prop="severity" label="严重级别" width="100" />
        <el-table-column prop="escalation_level" label="升级级别" width="100" />
        <el-table-column label="状态" width="100">
          <template #default="{ row }">
            <el-tag :type="row.status === 'pending' ? 'warning' : 'info'" size="small">{{ row.status || 'pending' }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="artifact_id" label="Artifact" min-width="180" show-overflow-tooltip />
        <el-table-column prop="receipt_id" label="回执" min-width="180" show-overflow-tooltip />
        <el-table-column prop="proposal_id" label="提案" min-width="180" show-overflow-tooltip />
        <el-table-column prop="created_at" label="时间" min-width="170">
          <template #default="{ row }">{{ formatTime(row.created_at) }}</template>
        </el-table-column>
      </el-table>
    </el-card>
  </div>
</template>

<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { ElMessage } from 'element-plus'
import { evolutionApi } from '@/api/evolutionClient'

const receipts = ref<any[]>([])
const actions = ref<any[]>([])
const result = ref<any>(null)
const submitting = ref(false)
const loadingActions = ref(false)
const form = ref<any>({
  receipt_id: '',
  success_rate: 0.8,
  safety: 0.8,
  evidence_quality: 0.6,
  latency_mean_ms: 30000,
  cost_total_usd: 5
})

const loadReceipts = async () => {
  try {
    const res = await evolutionApi.getReceipts()
    const payload = res.data?.data || res.data || {}
    receipts.value = payload?.items || (Array.isArray(payload) ? payload : [])
    if (receipts.value.length && !form.value.receipt_id) {
      form.value.receipt_id = String(receipts.value[0].receipt_id || receipts.value[0].id || '')
    }
  } catch (error: any) {
    ElMessage.error(error?.response?.data?.detail || '加载回执失败')
  }
}

const loadActions = async () => {
  loadingActions.value = true
  try {
    const res = await evolutionApi.getFollowUpActions()
    const payload = res.data?.data || res.data || {}
    actions.value = payload?.items || (Array.isArray(payload) ? payload : [])
  } catch (error: any) {
    ElMessage.error(error?.response?.data?.detail || '加载后续动作失败')
  } finally {
    loadingActions.value = false
  }
}

const submitObservation = async () => {
  if (!form.value.receipt_id) {
    ElMessage.warning('请选择已发布回执')
    return
  }
  submitting.value = true
  try {
    const payload = {
      receipt_id: form.value.receipt_id,
      metrics: {
        success_rate: form.value.success_rate,
        score_aggregation: {
          safety: { avg_score: form.value.safety },
          evidence_quality: { avg_score: form.value.evidence_quality }
        },
        latency: { mean_ms: form.value.latency_mean_ms },
        cost: { total_usd: form.value.cost_total_usd }
      }
    }
    const res = await evolutionApi.observePostRelease(payload)
    result.value = res.data?.data || {}
    ElMessage.success('观测已提交')
    await loadActions()
  } catch (error: any) {
    ElMessage.error(error?.response?.data?.detail || '提交观测失败')
  } finally {
    submitting.value = false
  }
}

const formatTime = (value?: string) => value ? new Date(value).toLocaleString('zh-CN') : '-'

onMounted(() => {
  void loadReceipts()
  void loadActions()
})
</script>
