<template>
  <div class="transactions-page">
    <!-- Header -->
    <div class="page-header">
      <h1 class="page-title">
        <el-icon><Document /></el-icon>
        交易明细
      </h1>
      <p class="page-description">查看所有充值、消费和赠送记录</p>
    </div>

    <!-- 摘要卡片 -->
    <el-row :gutter="20" class="summary-cards">
      <el-col :span="6">
        <el-card shadow="never" class="metric-card">
          <div class="metric-value primary">{{ billingStore.balanceDisplay }}</div>
          <div class="metric-label">当前余额</div>
        </el-card>
      </el-col>
      <el-col :span="6">
        <el-card shadow="never" class="metric-card">
          <div class="metric-value">¥{{ billingStore.totalRecharged.toFixed(2) }}</div>
          <div class="metric-label">累计充值</div>
        </el-card>
      </el-col>
      <el-col :span="6">
        <el-card shadow="never" class="metric-card">
          <div class="metric-value">¥{{ billingStore.totalConsumed.toFixed(3) }}</div>
          <div class="metric-label">累计消耗</div>
        </el-card>
      </el-col>
      <el-col :span="6">
        <el-card shadow="never" class="metric-card">
          <div class="metric-value">¥{{ billingStore.totalGifted.toFixed(2) }}</div>
          <div class="metric-label">累计赠送</div>
        </el-card>
      </el-col>
    </el-row>

    <!-- 筛选栏 -->
    <el-card shadow="never" class="filter-card">
      <el-row :gutter="16" align="middle">
        <el-col :span="6">
          <el-select v-model="filters.type" placeholder="交易类型" clearable @change="loadTransactions">
            <el-option label="全部" value="" />
            <el-option label="充值" value="recharge" />
            <el-option label="消费" value="consume" />
            <el-option label="赠送" value="gift" />
            <el-option label="预占" value="preoccupy" />
            <el-option label="结算退回" value="settle_refund" />
          </el-select>
        </el-col>
        <el-col :span="8">
          <el-date-picker
            v-model="dateRange"
            type="daterange"
            range-separator="至"
            start-placeholder="开始日期"
            end-placeholder="结束日期"
            value-format="YYYY-MM-DDTHH:mm:ss"
            @change="handleDateChange"
          />
        </el-col>
        <el-col :span="4">
          <el-button @click="loadTransactions" :icon="Refresh">刷新</el-button>
        </el-col>
        <el-col :span="6" style="text-align: right">
          <el-button type="primary" plain @click="handleExport" :loading="exporting">
            导出CSV
          </el-button>
        </el-col>
      </el-row>
    </el-card>

    <!-- 数据表格 -->
    <el-card shadow="never" class="table-card">
      <el-table
        :data="transactions"
        v-loading="loading"
        stripe
        :default-sort="{ prop: 'created_at', order: 'descending' }"
      >
        <el-table-column prop="txn_id" label="流水号" width="220" show-overflow-tooltip />
        <el-table-column prop="type" label="类型" width="100">
          <template #default="{ row }">
            <el-tag :type="getTypeTagType(row.type)" size="small">
              {{ getTypeLabel(row.type) }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="direction" label="方向" width="80">
          <template #default="{ row }">
            <span :class="row.direction === 'in' ? 'text-success' : 'text-danger'">
              {{ row.direction === 'in' ? '收入' : '支出' }}
            </span>
          </template>
        </el-table-column>
        <el-table-column prop="amount" label="金额(元)" width="120" sortable>
          <template #default="{ row }">
            <span :class="row.direction === 'in' ? 'text-success' : 'text-danger'">
              {{ row.direction === 'in' ? '+' : '-' }}{{ row.amount.toFixed(3) }}
            </span>
          </template>
        </el-table-column>
        <el-table-column prop="balance_after" label="余额(元)" width="120">
          <template #default="{ row }">
            {{ row.balance_after.toFixed(3) }}
          </template>
        </el-table-column>
        <el-table-column prop="status" label="状态" width="90">
          <template #default="{ row }">
            <el-tag :type="getStatusTagType(row.status)" size="small">
              {{ getStatusLabel(row.status) }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="metadata" label="详情" min-width="200" show-overflow-tooltip>
          <template #default="{ row }">
            <span v-if="row.metadata?.prompt_tokens">
              {{ row.metadata.prompt_tokens }}+{{ row.metadata.completion_tokens }} tokens
              ({{ row.metadata.model || '' }})
            </span>
            <span v-else-if="row.metadata?.reason">
              {{ row.metadata.reason }}
            </span>
            <span v-else>-</span>
          </template>
        </el-table-column>
        <el-table-column prop="created_at" label="时间" width="180" sortable>
          <template #default="{ row }">
            {{ formatTime(row.created_at) }}
          </template>
        </el-table-column>
      </el-table>

      <!-- 分页 -->
      <div class="pagination-wrapper">
        <el-pagination
          v-model:current-page="currentPage"
          v-model:page-size="pageSize"
          :total="total"
          :page-sizes="[20, 50, 100]"
          layout="total, sizes, prev, pager, next, jumper"
          @current-change="loadTransactions"
          @size-change="handleSizeChange"
        />
      </div>
    </el-card>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { ElMessage } from 'element-plus'
import { Document, Refresh } from '@element-plus/icons-vue'
import { useTokenBillingStore } from '@/stores/tokenBilling'
import { tokenBillingApi, type TransactionItem } from '@/api/tokenBilling'

const billingStore = useTokenBillingStore()

// 状态
const transactions = ref<TransactionItem[]>([])
const loading = ref(false)
const exporting = ref(false)
const total = ref(0)
const currentPage = ref(1)
const pageSize = ref(20)
const dateRange = ref<[string, string] | null>(null)

const filters = ref({
  type: '',
})

// 方法
async function loadTransactions() {
  loading.value = true
  try {
    const params: any = {
      page: currentPage.value,
      page_size: pageSize.value,
    }
    if (filters.value.type) params.type = filters.value.type
    if (dateRange.value) {
      params.start_date = dateRange.value[0]
      params.end_date = dateRange.value[1]
    }

    const res = await tokenBillingApi.getTransactions(params)
    if (res.success && res.data) {
      const data = res.data as any
      transactions.value = data.items || []
      total.value = data.total || 0
    }
  } catch (error: any) {
    ElMessage.error('加载交易明细失败')
  } finally {
    loading.value = false
  }
}

function handleDateChange() {
  currentPage.value = 1
  loadTransactions()
}

function handleSizeChange() {
  currentPage.value = 1
  loadTransactions()
}

async function handleExport() {
  exporting.value = true
  try {
    const params: any = {}
    if (filters.value.type) params.type = filters.value.type
    if (dateRange.value) {
      params.start_date = dateRange.value[0]
      params.end_date = dateRange.value[1]
    }
    await tokenBillingApi.exportTransactions(params)
    ElMessage.success('导出成功')
  } catch {
    ElMessage.error('导出失败')
  } finally {
    exporting.value = false
  }
}

// 格式化函数
function formatTime(isoStr: string): string {
  if (!isoStr) return '-'
  try {
    return new Date(isoStr).toLocaleString('zh-CN')
  } catch {
    return isoStr
  }
}

function getTypeLabel(type: string): string {
  const map: Record<string, string> = {
    recharge: '充值',
    consume: '消费',
    gift: '赠送',
    preoccupy: '预占',
    settle: '结算',
    settle_refund: '结算退回',
  }
  return map[type] || type
}

type TagType = 'success' | 'warning' | 'info' | 'danger' | undefined
function getTypeTagType(type: string): TagType {
  const map: Record<string, TagType> = {
    recharge: 'success',
    consume: 'danger',
    gift: 'warning',
    preoccupy: 'info',
    settle: undefined,
    settle_refund: 'success',
  }
  return map[type] ?? undefined
}

function getStatusLabel(status: string): string {
  const map: Record<string, string> = {
    success: '成功',
    pending: '处理中',
    frozen: '已冻结',
    rolled_back: '已回滚',
  }
  return map[status] || status
}

function getStatusTagType(status: string): TagType {
  const map: Record<string, TagType> = {
    success: 'success',
    pending: 'warning',
    frozen: 'info',
    rolled_back: 'danger',
  }
  return map[status] ?? undefined
}

onMounted(() => {
  billingStore.fetchAccount()
  loadTransactions()
})
</script>

<style lang="scss" scoped>
.transactions-page {
  padding: 20px;
  max-width: 1400px;
  margin: 0 auto;
}

.page-header {
  margin-bottom: 24px;

  .page-title {
    display: flex;
    align-items: center;
    gap: 8px;
    font-size: 24px;
    font-weight: 600;
    color: var(--el-text-color-primary);
    margin: 0 0 8px;
  }

  .page-description {
    color: var(--el-text-color-secondary);
    margin: 0;
  }
}

.summary-cards {
  margin-bottom: 20px;
}

.metric-card {
  text-align: center;
  padding: 8px 0;

  .metric-value {
    font-size: 28px;
    font-weight: 700;
    color: var(--el-text-color-primary);
    line-height: 1.4;

    &.primary {
      color: var(--el-color-primary);
    }
  }

  .metric-label {
    font-size: 14px;
    color: var(--el-text-color-secondary);
    margin-top: 4px;
  }
}

.filter-card {
  margin-bottom: 20px;
}

.table-card {
  margin-bottom: 20px;
}

.pagination-wrapper {
  display: flex;
  justify-content: flex-end;
  margin-top: 16px;
}

.text-success {
  color: var(--el-color-success);
}

.text-danger {
  color: var(--el-color-danger);
}
</style>
