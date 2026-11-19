<template>
  <div class="evolution-receipts">
    <el-page-header title="自进化回执" @back="$router.push('/evolution/proposals')" />

    <el-card style="margin-top: 16px;" v-loading="loading">
      <el-table :data="receipts" stripe>
        <el-table-column prop="receipt_id" label="回执 ID" width="160" />
        <el-table-column prop="proposal_id" label="提案 ID" width="160">
          <template #default="{ row }">
            <router-link v-if="row.proposal_id" :to="`/evolution/proposals/${row.proposal_id}`" class="link">
              {{ row.proposal_id }}
            </router-link>
            <span v-else>-</span>
          </template>
        </el-table-column>
        <el-table-column prop="final_action" label="最终动作" width="120">
          <template #default="{ row }">
            <el-tag size="small" :type="actionTagType(row.final_action)">{{ actionLabel(row.final_action) }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="promoted_version" label="发布版本" width="120" />
        <el-table-column prop="release_status" label="发布状态" width="110">
          <template #default="{ row }">
            <el-tag size="small" :type="releaseStatusTagType(row.release_status)">{{ releaseStatusLabel(row.release_status) }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="environment" label="环境" width="100">
          <template #default="{ row }">{{ row.environment || 'default' }}</template>
        </el-table-column>
        <el-table-column prop="before_version" label="切换前" width="100" />
        <el-table-column prop="after_version" label="切换后" width="100" />
        <el-table-column prop="stop_reason" label="停止原因" width="150">
          <template #default="{ row }">{{ row.stop_reason || '-' }}</template>
        </el-table-column>
        <el-table-column prop="created_at" label="创建时间" width="180">
          <template #default="{ row }">{{ formatDate(row.created_at) }}</template>
        </el-table-column>
        <el-table-column label="审批记录数" width="100">
          <template #default="{ row }">{{ row.approval_records?.length || 0 }}</template>
        </el-table-column>
        <el-table-column label="详情" width="80" fixed="right">
          <template #default="{ row }">
            <el-button link type="primary" size="small" @click="openDetail(row)">查看</el-button>
          </template>
        </el-table-column>
      </el-table>
      <el-empty v-if="!receipts.length && !loading" description="暂无回执记录" />
    </el-card>

    <el-dialog v-model="detailVisible" title="自进化回执详情" width="720px">
      <el-descriptions v-if="selectedReceipt" :column="2" border>
        <el-descriptions-item label="回执 ID">{{ selectedReceipt.receipt_id }}</el-descriptions-item>
        <el-descriptions-item label="Proposal">{{ selectedReceipt.proposal_id || '—' }}</el-descriptions-item>
        <el-descriptions-item label="基线版本">{{ selectedReceipt.baseline_artifact_version || '—' }}</el-descriptions-item>
        <el-descriptions-item label="候选版本">{{ selectedReceipt.candidate_version || selectedReceipt.promoted_version || '—' }}</el-descriptions-item>
        <el-descriptions-item label="Gate" :span="2">{{ selectedReceipt.gate_result?.passed === true ? '通过' : selectedReceipt.gate_result?.passed === false ? '失败' : '未记录' }}</el-descriptions-item>
        <el-descriptions-item label="Smoke Test" :span="2">{{ selectedReceipt.smoke_test_result?.passed === true ? '通过' : selectedReceipt.smoke_test_result?.passed === false ? '失败' : '未记录' }}</el-descriptions-item>
        <el-descriptions-item label="发布状态" :span="2">{{ releaseStatusLabel(selectedReceipt.release_status) }}</el-descriptions-item>
        <el-descriptions-item label="环境" :span="2">{{ selectedReceipt.environment || 'default' }}</el-descriptions-item>
        <el-descriptions-item label="切换前版本">{{ selectedReceipt.before_version || '—' }}</el-descriptions-item>
        <el-descriptions-item label="切换后版本">{{ selectedReceipt.after_version || selectedReceipt.promoted_version || '—' }}</el-descriptions-item>
        <el-descriptions-item label="停止原因" :span="2">{{ selectedReceipt.stop_reason || '—' }}</el-descriptions-item>
      </el-descriptions>
      <template v-if="selectedReceipt?.operation_records?.length">
        <el-divider />
        <h4 class="receipt-section-title">发布 / 回滚阶段记录</h4>
        <el-table :data="selectedReceipt.operation_records" size="small" border>
          <el-table-column prop="phase" label="阶段" min-width="180" />
          <el-table-column prop="status" label="状态" width="100">
            <template #default="{ row }">
              <el-tag size="small" :type="row.status === 'ok' ? 'success' : 'danger'">{{ row.status === 'ok' ? '成功' : row.status }}</el-tag>
            </template>
          </el-table-column>
          <el-table-column prop="error" label="错误信息" min-width="160">
            <template #default="{ row }">{{ row.error || '—' }}</template>
          </el-table-column>
        </el-table>
      </template>
      <pre v-if="selectedReceipt" class="receipt-json">{{ JSON.stringify(selectedReceipt, null, 2) }}</pre>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { evolutionApi } from '@/api/evolutionClient'

const loading = ref(false)
const receipts = ref<any[]>([])
const detailVisible = ref(false)
const selectedReceipt = ref<any>(null)

const loadReceipts = async () => {
  loading.value = true
  try {
    const res = await evolutionApi.getReceipts()
    receipts.value = res.data?.data?.items || []
  } catch (e) {
    console.error('Failed to load receipts', e)
  } finally {
    loading.value = false
  }
}

const actionTagType = (a: string): any => ({ promoted: 'success', rejected: 'danger', stopped: 'warning', rollback: 'info' }[a] || '')
const actionLabel = (a: string) => ({ promoted: '已发布', rejected: '已拒绝', stopped: '已停止', rollback: '已回滚' }[a] || a)
const releaseStatusLabel = (status: string) => ({ succeeded: '成功', compensated: '已补偿', failed: '失败' }[status] || '未记录')
const releaseStatusTagType = (status: string): any => ({ succeeded: 'success', compensated: 'warning', failed: 'danger' }[status] || 'info')
const formatDate = (d: string) => d ? new Date(d).toLocaleString('zh-CN') : '-'
const openDetail = (receipt: any) => {
  selectedReceipt.value = receipt
  detailVisible.value = true
}

onMounted(loadReceipts)
</script>

<style scoped>
.link { color: #409eff; text-decoration: none; }
.receipt-section-title { margin: 4px 0 10px; font-size: 14px; }
</style>
