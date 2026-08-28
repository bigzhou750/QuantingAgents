<template>
  <div class="human-review-page">
    <div class="page-header">
      <h1 class="page-title">
        <el-icon><EditPen /></el-icon>
        人工复核
      </h1>
      <el-button @click="$router.push('/evaluation/dashboard')">返回概览</el-button>
    </div>

    <!-- 待复核列表 -->
    <el-card shadow="never">
      <template #header>
        <div class="card-header">
          <span>待复核评分（低置信度 / 低分数）</span>
          <el-button size="small" @click="loadPending">刷新</el-button>
        </div>
      </template>

      <el-table :data="pendingReviews" v-loading="loading" stripe>
        <el-table-column prop="score_id" label="Score ID" width="180" show-overflow-tooltip />
        <el-table-column prop="trial_id" label="Trial ID" width="240" show-overflow-tooltip />
        <el-table-column prop="score_name" label="评分维度" width="140" />
        <el-table-column prop="source" label="来源" width="120">
          <template #default="{ row }">
            <el-tag size="small">{{ row.source }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="score" label="原始分数" width="100">
          <template #default="{ row }">
            <span :style="{ color: row.score < 0.5 ? 'var(--el-color-danger)' : '' }">
              {{ (row.score * 100).toFixed(1) }}%
            </span>
          </template>
        </el-table-column>
        <el-table-column prop="confidence" label="置信度" width="100">
          <template #default="{ row }">
            {{ (row.confidence * 100).toFixed(1) }}%
          </template>
        </el-table-column>
        <el-table-column prop="reason" label="评分原因" min-width="200" show-overflow-tooltip />
        <el-table-column label="操作" fixed="right" width="100">
          <template #default="{ row }">
            <el-button type="primary" link size="small" @click="openReviewDialog(row)">
              复核
            </el-button>
          </template>
        </el-table-column>
      </el-table>

      <div v-if="!loading && pendingReviews.length === 0" style="text-align: center; padding: 40px; color: var(--el-text-color-secondary)">
        暂无待复核项 🎉
      </div>
    </el-card>

    <!-- 复核对话框 -->
    <el-dialog v-model="reviewDialogVisible" title="人工复核" width="600px">
      <div v-if="selectedScore">
        <el-descriptions :column="2" border style="margin-bottom: 16px">
          <el-descriptions-item label="Score ID">{{ selectedScore.score_id }}</el-descriptions-item>
          <el-descriptions-item label="Trial ID">{{ selectedScore.trial_id }}</el-descriptions-item>
          <el-descriptions-item label="评分维度">{{ selectedScore.score_name }}</el-descriptions-item>
          <el-descriptions-item label="来源">{{ selectedScore.source }}</el-descriptions-item>
          <el-descriptions-item label="原始分数">
            {{ (selectedScore.score * 100).toFixed(1) }}%
          </el-descriptions-item>
          <el-descriptions-item label="置信度">
            {{ (selectedScore.confidence * 100).toFixed(1) }}%
          </el-descriptions-item>
          <el-descriptions-item label="评分原因" :span="2">
            {{ selectedScore.reason }}
          </el-descriptions-item>
        </el-descriptions>

        <el-form label-width="100px">
          <el-form-item label="新分数">
            <el-slider v-model="reviewForm.newScore" :min="0" :max="1" :step="0.05" show-input />
          </el-form-item>
          <el-form-item label="复核意见">
            <el-input
              v-model="reviewForm.comment"
              type="textarea"
              :rows="3"
              placeholder="请输入复核意见（可选）"
            />
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
import { ref, onMounted } from 'vue'
import { ElMessage } from 'element-plus'
import { EditPen } from '@element-plus/icons-vue'
import axios from 'axios'

const pendingReviews = ref<any[]>([])
const loading = ref(false)

const reviewDialogVisible = ref(false)
const selectedScore = ref<any>(null)
const submitting = ref(false)
const reviewForm = ref({ newScore: 0.5, comment: '' })

const loadPending = async () => {
  loading.value = true
  try {
    const res = await axios.get('/api/eval/scores/pending-review', { params: { limit: 50 } })
    pendingReviews.value = res.data?.data?.items || []
  } catch (error) {
    ElMessage.error('加载待复核列表失败')
  } finally {
    loading.value = false
  }
}

const openReviewDialog = (score: any) => {
  selectedScore.value = score
  reviewForm.value = { newScore: score.score, comment: '' }
  reviewDialogVisible.value = true
}

const submitReview = async () => {
  if (!selectedScore.value) return
  submitting.value = true
  try {
    await axios.post('/api/eval/scores/human-review', {
      score_id: selectedScore.value.score_id,
      new_score: reviewForm.value.newScore,
      comment: reviewForm.value.comment,
    })
    ElMessage.success('复核已提交')
    reviewDialogVisible.value = false
    await loadPending()
  } catch (error: any) {
    ElMessage.error(error.response?.data?.detail || '提交失败')
  } finally {
    submitting.value = false
  }
}

onMounted(() => {
  loadPending()
})
</script>

<style scoped>
.human-review-page {
  padding: 24px;
}

.page-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 24px;
}

.page-title {
  font-size: 24px;
  font-weight: 600;
  display: flex;
  align-items: center;
  gap: 12px;
  margin: 0;
}

.card-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
}
</style>
