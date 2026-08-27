<template>
  <div class="screening-results">
    <el-card v-if="loading" v-loading="true" />

    <template v-else-if="result">
      <!-- 结果概览 -->
      <el-card class="summary-card">
        <template #header>
          <div class="card-header">
            <span>选股结果</span>
            <el-tag type="success">共 {{ result.total_candidates }} 只候选标的</el-tag>
          </div>
        </template>

        <!-- 整体风险提示 -->
        <el-alert
          v-if="result.overall_risks?.length"
          type="warning"
          :closable="false"
          show-icon
        >
          <template #title>
            <div class="risk-alert">
              <strong>风险提示：</strong>
              <ul>
                <li v-for="(risk, idx) in result.overall_risks" :key="idx">{{ risk }}</li>
              </ul>
            </div>
          </template>
        </el-alert>

        <div class="data-info">
          <span>数据时间：{{ formatTime(result.data_as_of) }}</span>
          <el-tag v-if="result.terminology_compliant" type="success" size="small">
            已合规检查
          </el-tag>
        </div>
      </el-card>

      <!-- 候选列表 -->
      <el-card style="margin-top: 16px;">
        <template #header>
          <span>候选标的列表</span>
        </template>

        <el-table :data="result.candidates" border stripe>
          <el-table-column prop="stock_code" label="代码" width="100" />
          <el-table-column prop="stock_name" label="名称" width="120" />
          <el-table-column label="评分" width="100">
            <template #default="{ row }">
              <el-progress
                :percentage="Math.round(row.score * 100)"
                :color="getScoreColor(row.score)"
                :stroke-width="8"
              />
            </template>
          </el-table-column>
          <el-table-column label="命中原因" min-width="250">
            <template #default="{ row }">
              <el-tag
                v-for="(reason, idx) in row.match_reasons"
                :key="idx"
                size="small"
                type="success"
                style="margin: 2px;"
              >
                {{ reason }}
              </el-tag>
            </template>
          </el-table-column>
          <el-table-column label="风险警告" min-width="250">
            <template #default="{ row }">
              <el-tag
                v-for="(warning, idx) in row.risk_warnings"
                :key="idx"
                size="small"
                type="warning"
                style="margin: 2px;"
              >
                {{ warning }}
              </el-tag>
            </template>
          </el-table-column>
          <el-table-column label="画像冲突" width="100">
            <template #default="{ row }">
              <el-tag v-if="row.conflict_with_profile" type="danger" size="small">
                是
              </el-tag>
              <el-tag v-else type="success" size="small">否</el-tag>
            </template>
          </el-table-column>
        </el-table>
      </el-card>
    </template>

    <el-empty v-else description="暂无结果，请先执行选股任务" />
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { useRoute } from 'vue-router'
import { ElMessage } from 'element-plus'
import axios from 'axios'

const route = useRoute()
const loading = ref(false)
const result = ref<any>(null)

// 格式化时间
const formatTime = (timeStr: string) => {
  if (!timeStr) return '未知'
  try {
    const date = new Date(timeStr)
    return date.toLocaleString('zh-CN')
  } catch {
    return timeStr
  }
}

// 获取评分颜色
const getScoreColor = (score: number) => {
  if (score >= 0.7) return '#67C23A'
  if (score >= 0.4) return '#E6A23C'
  return '#F56C6C'
}

// 加载结果
const loadResult = async () => {
  const taskId = route.params.taskId as string
  if (!taskId) return

  loading.value = true
  try {
    // 轮询等待结果
    let attempts = 0
    const maxAttempts = 30 // 最多等待 30 秒

    while (attempts < maxAttempts) {
      const response = await axios.get(`/api/investment/screening-tasks/${taskId}/result`)

      if (response.data.success && response.data.data && Object.keys(response.data.data).length > 0) {
        result.value = response.data.data
        break
      }

      // 检查任务状态
      const taskResponse = await axios.get(`/api/investment/tasks/${taskId}`)
      const status = taskResponse.data.data?.status

      if (status === 'failed') {
        ElMessage.error('选股任务执行失败')
        break
      }

      if (status === 'completed' && !result.value) {
        // 任务完成但无结果
        break
      }

      // 等待 1 秒后重试
      await new Promise(resolve => setTimeout(resolve, 1000))
      attempts++
    }

    if (!result.value && attempts >= maxAttempts) {
      ElMessage.warning('等待超时，请稍后刷新查看结果')
    }
  } catch (error: any) {
    ElMessage.error(error.response?.data?.detail || '加载结果失败')
  } finally {
    loading.value = false
  }
}

onMounted(() => {
  loadResult()
})
</script>

<style scoped>
.screening-results {
  padding: 20px;
}

.summary-card .card-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
}

.risk-alert ul {
  margin: 8px 0 0 0;
  padding-left: 20px;
}

.risk-alert li {
  margin: 4px 0;
}

.data-info {
  margin-top: 12px;
  display: flex;
  gap: 12px;
  align-items: center;
  font-size: 13px;
  color: #909399;
}
</style>
