<template>
  <div class="observations-page">
    <!-- 返回入口 -->
    <div style="margin-bottom: 12px;">
      <el-button link @click="$router.push('/investment/home')">← 回到首页</el-button>
    </div>

    <!-- 页面标题 -->
    <el-card class="header-card">
      <div class="page-header">
        <h2>📋 我的观察</h2>
        <div class="header-actions">
          <el-tag v-if="pendingReviewCount > 0" type="warning" size="large" effect="dark">
            {{ pendingReviewCount }} 条待复盘
          </el-tag>
          <el-button type="primary" @click="showAddDialog = true">手动添加</el-button>
        </div>
      </div>
      <p class="wizard-muted">
        观察标的是选股结果与自选股之间的中间层，保留来源链路便于学习复盘。
      </p>
    </el-card>

    <!-- 筛选栏 -->
    <el-card style="margin-top: 16px;">
      <div class="filter-bar">
        <el-radio-group v-model="statusFilter" @change="loadObservations">
          <el-radio-button value="">观察中</el-radio-button>
          <el-radio-button value="reviewed">已复盘</el-radio-button>
          <el-radio-button value="removed">已移出</el-radio-button>
        </el-radio-group>
      </div>
    </el-card>

    <!-- 观察列表 -->
    <el-card v-loading="loading" style="margin-top: 16px;">
      <template #header>
        <span>观察标的列表（{{ total }}）</span>
      </template>

      <el-table :data="observations" border stripe empty-text="暂无观察标的">
        <el-table-column prop="stock_code" label="代码" width="100" />
        <el-table-column prop="stock_name" label="名称" width="120" />
        <el-table-column label="来源" width="120">
          <template #default="{ row }">
            <el-tag :type="sourceTagType(row.source_type)" size="small">
              {{ sourceLabel(row.source_type) }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column label="入选原因" min-width="200">
          <template #default="{ row }">
            <el-tag
              v-for="(reason, idx) in (row.match_reasons || []).slice(0, 3)"
              :key="idx"
              size="small"
              type="success"
              style="margin: 2px;"
            >
              {{ reason }}
            </el-tag>
            <span v-if="!row.match_reasons?.length" class="wizard-muted">—</span>
          </template>
        </el-table-column>
        <el-table-column label="用户备注" min-width="150">
          <template #default="{ row }">
            <span>{{ row.user_notes || '—' }}</span>
          </template>
        </el-table-column>
        <el-table-column label="状态" width="90">
          <template #default="{ row }">
            <el-tag :type="statusTagType(row.status)" size="small">
              {{ statusLabel(row.status) }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column label="加入时间" width="160">
          <template #default="{ row }">
            {{ formatTime(row.created_at) }}
          </template>
        </el-table-column>
        <el-table-column label="操作" width="280" fixed="right">
          <template #default="{ row }">
            <el-button
              v-if="row.status === 'active'"
              size="small"
              type="warning"
              @click="openReviewDialog(row)"
            >
              复盘
            </el-button>
            <el-button
              size="small"
              type="primary"
              link
              @click="goAnalysis(row)"
            >
              分析
            </el-button>
            <el-button
              size="small"
              type="primary"
              link
              @click="goNewsImpact(row)"
            >
              新闻
            </el-button>
            <el-button
              size="small"
              type="primary"
              link
              @click="goPaperTrade(row)"
            >
              模拟
            </el-button>
            <el-button
              v-if="row.status === 'active'"
              size="small"
              type="danger"
              link
              @click="removeObservation(row)"
            >
              移出
            </el-button>
          </template>
        </el-table-column>
      </el-table>
    </el-card>

    <!-- 手动添加对话框 -->
    <el-dialog v-model="showAddDialog" title="手动添加观察标的" width="480px">
      <el-form :model="addForm" label-width="80px">
        <el-form-item label="股票代码" required>
          <el-input v-model="addForm.stock_code" placeholder="如 000001" />
        </el-form-item>
        <el-form-item label="股票名称">
          <el-input v-model="addForm.stock_name" placeholder="可选" />
        </el-form-item>
        <el-form-item label="备注">
          <el-input v-model="addForm.user_notes" type="textarea" :rows="2" placeholder="为什么关注这只股票？" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="showAddDialog = false">取消</el-button>
        <el-button type="primary" :loading="addLoading" @click="handleAdd">添加</el-button>
      </template>
    </el-dialog>

    <!-- 复盘对话框 -->
    <el-dialog v-model="showReviewDialog" title="复盘备注" width="520px">
      <div v-if="reviewTarget" class="review-target-info">
        <el-descriptions :column="2" border size="small">
          <el-descriptions-item label="股票">{{ reviewTarget.stock_code }} {{ reviewTarget.stock_name }}</el-descriptions-item>
          <el-descriptions-item label="来源">{{ sourceLabel(reviewTarget.source_type) }}</el-descriptions-item>
          <el-descriptions-item label="入选原因" :span="2">
            {{ (reviewTarget.match_reasons || []).join('、') || '—' }}
          </el-descriptions-item>
        </el-descriptions>
      </div>
      <el-form style="margin-top: 16px;">
        <el-form-item label="复盘内容">
          <el-input
            v-model="reviewContent"
            type="textarea"
            :rows="4"
            placeholder="回顾你的判断是否正确，学到了什么？"
          />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="showReviewDialog = false">取消</el-button>
        <el-button type="primary" :loading="reviewLoading" @click="submitReview">保存复盘</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'
import { observationApi } from '@/api/observation'

const router = useRouter()

// 列表状态
const loading = ref(false)
const observations = ref<any[]>([])
const total = ref(0)
const statusFilter = ref('')
const pendingReviewCount = ref(0)

// 手动添加
const showAddDialog = ref(false)
const addLoading = ref(false)
const addForm = ref({ stock_code: '', stock_name: '', user_notes: '' })

// 复盘
const showReviewDialog = ref(false)
const reviewTarget = ref<any>(null)
const reviewContent = ref('')
const reviewLoading = ref(false)

// 格式化时间
const formatTime = (timeStr: string) => {
  if (!timeStr) return '未知'
  try {
    return new Date(timeStr).toLocaleString('zh-CN')
  } catch {
    return timeStr
  }
}

// 标签映射
const sourceLabel = (type: string) => {
  const map: Record<string, string> = {
    screening: '策略选股',
    manual: '手动添加',
    favorites: '自选股导入',
    news: '新闻关注',
  }
  return map[type] || type
}

const sourceTagType = (type: string): 'primary' | 'success' | 'warning' | 'info' => {
  const map: Record<string, 'primary' | 'success' | 'warning' | 'info'> = {
    screening: 'success',
    manual: 'primary',
    favorites: 'info',
    news: 'warning',
  }
  return map[type] || 'info'
}

const statusLabel = (status: string) => {
  const map: Record<string, string> = { active: '观察中', removed: '已移出', reviewed: '已复盘' }
  return map[status] || status
}

const statusTagType = (status: string): 'success' | 'warning' | 'info' => {
  const map: Record<string, 'success' | 'warning' | 'info'> = { active: 'success', removed: 'info', reviewed: 'warning' }
  return map[status] || 'info'
}

// 加载数据
const loadObservations = async () => {
  loading.value = true
  try {
    const params: Record<string, unknown> = { limit: 100 }
    if (statusFilter.value) {
      params.status = statusFilter.value
    }
    const res = await observationApi.list(params)
    observations.value = res.data?.items || []
    total.value = res.data?.total || 0
  } catch (e: any) {
    ElMessage.error(e.response?.data?.detail || '加载失败')
  } finally {
    loading.value = false
  }
}

const loadPendingReviews = async () => {
  try {
    const res = await observationApi.getReviewSummary()
    pendingReviewCount.value = res.data?.count || 0
  } catch {
    // 非关键，静默失败
  }
}

// 手动添加
const handleAdd = async () => {
  if (!addForm.value.stock_code) {
    ElMessage.warning('请输入股票代码')
    return
  }
  addLoading.value = true
  try {
    await observationApi.add({
      stock_code: addForm.value.stock_code,
      stock_name: addForm.value.stock_name,
      user_notes: addForm.value.user_notes,
      source_type: 'manual',
    })
    ElMessage.success('已添加到观察列表')
    showAddDialog.value = false
    addForm.value = { stock_code: '', stock_name: '', user_notes: '' }
    await loadObservations()
  } catch (e: any) {
    ElMessage.error(e.response?.data?.detail || '添加失败')
  } finally {
    addLoading.value = false
  }
}

// 移出观察
const removeObservation = async (row: any) => {
  try {
    await ElMessageBox.confirm(`确定将 ${row.stock_name || row.stock_code} 移出观察列表吗？`, '确认移出', {
      type: 'warning',
    })
    await observationApi.remove(row.observation_id)
    ElMessage.success('已移出观察')
    await loadObservations()
    await loadPendingReviews()
  } catch (e: any) {
    if (e !== 'cancel') {
      ElMessage.error(e.response?.data?.detail || '操作失败')
    }
  }
}

// 复盘
const openReviewDialog = (row: any) => {
  reviewTarget.value = row
  reviewContent.value = ''
  showReviewDialog.value = true
}

const submitReview = async () => {
  if (!reviewContent.value.trim()) {
    ElMessage.warning('请输入复盘内容')
    return
  }
  reviewLoading.value = true
  try {
    await observationApi.addReview(reviewTarget.value.observation_id, reviewContent.value)
    ElMessage.success('复盘备注已保存')
    showReviewDialog.value = false
    await loadObservations()
    await loadPendingReviews()
  } catch (e: any) {
    ElMessage.error(e.response?.data?.detail || '保存失败')
  } finally {
    reviewLoading.value = false
  }
}

// 跳转入口
const goAnalysis = (row: any) => {
  router.push({
    path: '/analysis/single',
    query: { stock: row.stock_code, observation_id: row.observation_id },
  })
}

const goNewsImpact = (row: any) => {
  router.push({
    path: '/news-watch/impact',
    query: { symbol: row.stock_code },
  })
}

const goPaperTrade = (row: any) => {
  const query: Record<string, string> = { code: row.stock_code }
  if (row.observation_id) query.observation_id = row.observation_id
  if (row.source_strategy_id) query.strategy_id = row.source_strategy_id
  router.push({ path: '/paper', query })
}

onMounted(() => {
  loadObservations()
  loadPendingReviews()
})
</script>

<style scoped>
.observations-page {
  padding: 20px;
}

.page-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
}

.page-header h2 {
  margin: 0;
}

.header-actions {
  display: flex;
  gap: 12px;
  align-items: center;
}

.wizard-muted {
  color: #909399;
  font-size: 13px;
  margin: 8px 0 0 0;
}

.filter-bar {
  display: flex;
  gap: 12px;
  align-items: center;
}

.review-target-info {
  margin-bottom: 12px;
}
</style>
