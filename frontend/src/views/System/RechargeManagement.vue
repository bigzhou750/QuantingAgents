<template>
  <div class="recharge-management">
    <div class="page-header">
      <h1 class="page-title">
        <el-icon><Wallet /></el-icon>
        充值记录
      </h1>
      <p class="page-description">查询用户充值、赠送和管理员充值记录</p>
    </div>

    <el-card class="filter-panel" shadow="never">
      <el-form :inline="true" @submit.prevent="search">
        <el-form-item label="关键字">
          <el-input
            v-model="keyword"
            placeholder="用户名 / 邮箱 / 用户ID / 流水号 / 订单号"
            clearable
            style="width: 280px"
            @keyup.enter="search"
          >
            <template #prefix>
              <el-icon><Search /></el-icon>
            </template>
          </el-input>
        </el-form-item>

        <el-form-item label="类型">
          <el-select v-model="typeFilter" clearable placeholder="全部类型" style="width: 150px">
            <el-option label="全部类型" value="" />
            <el-option label="充值" value="recharge" />
            <el-option label="赠送" value="gift" />
            <el-option label="管理员充值" value="admin_recharge" />
            <el-option label="消费" value="consume" />
            <el-option label="预占" value="preoccupy" />
            <el-option label="结算退回" value="settle_refund" />
          </el-select>
        </el-form-item>

        <el-form-item label="时间">
          <el-date-picker
            v-model="dateRange"
            type="datetimerange"
            range-separator="至"
            start-placeholder="开始时间"
            end-placeholder="结束时间"
            value-format="YYYY-MM-DDTHH:mm:ss"
            style="width: 360px"
          />
        </el-form-item>

        <el-form-item>
          <el-button type="primary" @click="search">
            <el-icon><Search /></el-icon>
            查询
          </el-button>
          <el-button @click="resetFilter">
            <el-icon><Refresh /></el-icon>
            重置
          </el-button>
        </el-form-item>
      </el-form>
    </el-card>

    <el-card class="table-card" shadow="never">
      <template #header>
        <div class="table-header">
          <h3>充值记录</h3>
          <el-button size="small" @click="loadRecords">
            <el-icon><Refresh /></el-icon>
            刷新
          </el-button>
        </div>
      </template>

      <el-table v-loading="loading" :data="records" style="width: 100%">
        <el-table-column label="用户" min-width="220">
          <template #default="{ row }">
            <div class="user-cell">
              <div class="user-name">{{ row.metadata?.username || '未知' }}</div>
              <div class="user-meta">{{ row.metadata?.email || row.user_id }}</div>
            </div>
          </template>
        </el-table-column>

        <el-table-column label="类型" width="120">
          <template #default="{ row }">
            <el-tag :type="getTypeTagType(row.type)" size="small">
              {{ getTypeLabel(row.type) }}
            </el-tag>
          </template>
        </el-table-column>

        <el-table-column label="方向" width="80">
          <template #default="{ row }">
            <span :class="row.direction === 'in' ? 'text-success' : 'text-danger'">
              {{ row.direction === 'in' ? '收入' : '支出' }}
            </span>
          </template>
        </el-table-column>

        <el-table-column prop="amount" label="金额(元)" width="120">
          <template #default="{ row }">
            {{ row.direction === 'in' ? '+' : '-' }}{{ row.amount.toFixed(3) }}
          </template>
        </el-table-column>

        <el-table-column prop="balance_after" label="余额(元)" width="120">
          <template #default="{ row }">
            {{ row.balance_after.toFixed(3) }}
          </template>
        </el-table-column>

        <el-table-column label="操作人" width="140">
          <template #default="{ row }">
            {{ row.metadata?.operator_username || '未知' }}
          </template>
        </el-table-column>

        <el-table-column label="来源/备注" min-width="220" show-overflow-tooltip>
          <template #default="{ row }">
            <div v-if="row.metadata?.reason">{{ row.metadata.reason }}</div>
            <div v-else-if="row.metadata?.source">{{ row.metadata.source }}</div>
            <span v-else>-</span>
          </template>
        </el-table-column>

        <el-table-column label="关联订单" width="180" show-overflow-tooltip>
          <template #default="{ row }">
            {{ row.order_id || '-' }}
          </template>
        </el-table-column>

        <el-table-column prop="txn_id" label="流水号" width="210" show-overflow-tooltip />

        <el-table-column prop="created_at" label="时间" width="180">
          <template #default="{ row }">
            {{ formatTime(row.created_at) }}
          </template>
        </el-table-column>
      </el-table>

      <el-empty
        v-if="!loading && records.length === 0"
        description="暂无符合条件的充值记录"
        :image-size="160"
      />

      <el-pagination
        v-if="total > 0"
        v-model:current-page="currentPage"
        v-model:page-size="pageSize"
        :total="total"
        :page-sizes="[20, 50, 100]"
        layout="total, sizes, prev, pager, next, jumper"
        style="margin-top: 16px; text-align: right"
        @size-change="handleSizeChange"
        @current-change="loadRecords"
      />
    </el-card>
  </div>
</template>

<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { ElMessage } from 'element-plus'
import { Search, Refresh, Wallet } from '@element-plus/icons-vue'
import { tokenBillingApi, type AdminTransactionItem } from '@/api/tokenBilling'

const records = ref<AdminTransactionItem[]>([])
const loading = ref(false)
const total = ref(0)
const currentPage = ref(1)
const pageSize = ref(20)
const keyword = ref('')
const typeFilter = ref('')
const dateRange = ref<[string, string] | null>(null)

async function loadRecords() {
  loading.value = true
  try {
    const params: Record<string, any> = {
      page: currentPage.value,
      page_size: pageSize.value,
    }
    if (keyword.value.trim()) params.keyword = keyword.value.trim()
    if (typeFilter.value) params.type = typeFilter.value
    if (dateRange.value) {
      params.start_date = dateRange.value[0]
      params.end_date = dateRange.value[1]
    }
    const res = await tokenBillingApi.adminGetTransactions(params)
    if (res.success && res.data) {
      records.value = res.data.items || []
      total.value = res.data.total || 0
    }
  } catch (error) {
    ElMessage.error('加载充值记录失败')
    console.error('加载充值记录失败:', error)
  } finally {
    loading.value = false
  }
}

function search() {
  currentPage.value = 1
  loadRecords()
}

function resetFilter() {
  keyword.value = ''
  typeFilter.value = ''
  dateRange.value = null
  currentPage.value = 1
  loadRecords()
}

function handleSizeChange() {
  currentPage.value = 1
  loadRecords()
}

function formatTime(isoStr: string): string {
  if (!isoStr) return '-'
  try {
    return new Date(isoStr).toLocaleString('zh-CN', { hour12: false })
  } catch {
    return isoStr
  }
}

function getTypeLabel(type: string): string {
  const map: Record<string, string> = {
    recharge: '充值',
    consume: '消费',
    gift: '赠送',
    admin_recharge: '管理员充值',
    preoccupy: '预占',
    settle: '结算',
    settle_refund: '结算退回',
  }
  return map[type] || type
}

type TagType = 'primary' | 'success' | 'warning' | 'info' | 'danger' | undefined
function getTypeTagType(type: string): TagType {
  const map: Record<string, TagType> = {
    recharge: 'success',
    consume: 'danger',
    gift: 'warning',
    admin_recharge: 'primary',
    preoccupy: 'info',
    settle: undefined,
    settle_refund: 'success',
  }
  return map[type] ?? undefined
}

onMounted(loadRecords)
</script>

<style lang="scss" scoped>
.recharge-management {
  padding: 24px;
}

.page-header {
  margin-bottom: 20px;
}

.page-title {
  display: flex;
  align-items: center;
  gap: 8px;
  margin: 0 0 6px;
  font-size: 22px;
  font-weight: 600;
}

.page-description {
  margin: 0;
  color: #667085;
  font-size: 14px;
}

.filter-panel,
.table-card {
  margin-bottom: 20px;
}

.table-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
}

.table-header h3 {
  margin: 0;
  font-size: 16px;
}

.user-cell {
  display: flex;
  flex-direction: column;
}

.user-name {
  font-weight: 600;
}

.user-meta {
  color: #98a2b3;
  font-size: 12px;
}

.text-success {
  color: var(--el-color-success);
}

.text-danger {
  color: var(--el-color-danger);
}
</style>
