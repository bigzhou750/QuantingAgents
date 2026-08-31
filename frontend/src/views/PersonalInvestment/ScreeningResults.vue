<template>
  <div class="screening-results">
    <!-- 返回入口 -->
    <div style="margin-bottom: 12px;">
      <el-button link @click="$router.push('/investment/home')">← 回到首页</el-button>
      <el-divider direction="vertical" />
      <el-button link @click="$router.push('/investment/strategies')">我的策略</el-button>
    </div>

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

        <el-alert type="info" :closable="false" show-icon class="non-advice-alert">
          <template #title>
            以下是基于策略规则匹配的候选研究方向，不是买入或卖出建议。请结合体检结果和自身判断再决定下一步。
          </template>
        </el-alert>

        <!-- 整体风险提示 -->
        <el-alert
          v-if="result.overall_risks?.length"
          type="warning"
          :closable="false"
          show-icon
          style="margin-top: 12px;"
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
          <el-table-column label="策略适配度" width="130">
            <template #default="{ row }">
              <el-progress
                :percentage="Math.round(row.score * 100)"
                :color="getScoreColor(row.score)"
                :stroke-width="8"
              />
            </template>
          </el-table-column>
          <el-table-column label="入选原因" min-width="220">
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
              <span v-if="!row.match_reasons?.length" class="wizard-muted">暂无具体命中说明</span>
            </template>
          </el-table-column>
          <el-table-column label="主要风险" min-width="220">
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
              <span v-if="!row.risk_warnings?.length" class="wizard-muted">暂无明确风险提示</span>
            </template>
          </el-table-column>
          <el-table-column label="与画像是否冲突" width="130">
            <template #default="{ row }">
              <el-tooltip v-if="row.conflict_with_profile" content="该标的可能与你的排除规则或风险偏好不符" placement="top">
                <el-tag type="danger" size="small">冲突</el-tag>
              </el-tooltip>
              <el-tag v-else type="success" size="small">无冲突</el-tag>
            </template>
          </el-table-column>
          <el-table-column label="下一步" width="180" fixed="right">
            <template #default="{ row }">
              <el-button size="small" @click="addToWatchlist(row)" :loading="watchlistLoading === row.stock_code">
                加入观察
              </el-button>
              <el-button size="small" type="primary" link @click="continueResearch(row)">
                继续研究
              </el-button>
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
import { useRoute, useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import { investmentApi } from '@/api/investment'
import { observationApi } from '@/api/observation'

const route = useRoute()
const router = useRouter()
const loading = ref(false)
const result = ref<any>(null)
const watchlistLoading = ref('')

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

// 加入观察（写入独立观察集合，保留来源链路）
const addToWatchlist = async (row: any) => {
  watchlistLoading.value = row.stock_code
  try {
    const taskId = route.params.taskId as string
    await observationApi.add({
      stock_code: row.stock_code,
      stock_name: row.stock_name,
      source_type: 'screening',
      source_task_id: taskId || undefined,
      match_reasons: row.match_reasons || [],
      risk_warnings: row.risk_warnings || [],
    })
    ElMessage.success(`${row.stock_name || row.stock_code} 已加入观察`)
  } catch (error: any) {
    ElMessage.error(error.response?.data?.detail || '加入观察失败')
  } finally {
    watchlistLoading.value = ''
  }
}

// 继续研究：跳转到自然语言研究工作台
const continueResearch = (row: any) => {
  router.push({ path: '/research-agent', query: { symbol: row.stock_code } })
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
      const response = await investmentApi.getTaskResult('screening', taskId)

      if (response.success && response.data && Object.keys(response.data).length > 0) {
        result.value = response.data
        break
      }

      // 检查任务状态
      const taskResponse = await investmentApi.getTask(taskId)
      const status = taskResponse.data?.status

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

.non-advice-alert {
  margin-bottom: 4px;
}

.wizard-muted {
  color: #909399;
  font-size: 12px;
}
</style>
