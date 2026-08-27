<template>
  <div class="checkup-results">
    <el-card v-if="loading" v-loading="true" />

    <template v-else-if="result">
      <!-- 适配度概览 -->
      <el-card class="fitness-card">
        <template #header>
          <div class="card-header">
            <span>策略体检报告</span>
            <el-tag :type="(getFitnessType(result.fitness_level) as any)" size="large">
              适配度：{{ translateFitnessLevel(result.fitness_level) }}
            </el-tag>
          </div>
        </template>

        <div class="fitness-summary">
          <h4>综合评估</h4>
          <p>{{ result.fitness_summary }}</p>
        </div>

        <el-divider />

        <!-- 数据充分性 -->
        <div class="data-status">
          <el-icon :size="20" :color="result.data_sufficient ? '#67C23A' : '#E6A23C'">
            <component :is="result.data_sufficient ? 'CircleCheck' : 'Warning'" />
          </el-icon>
          <span>
            数据状态：{{ result.data_sufficient ? '充分' : '不足' }}
          </span>
          <span v-if="result.data_quality_note" class="note">
            （{{ result.data_quality_note }}）
          </span>
        </div>
      </el-card>

      <!-- 关键指标 -->
      <el-card style="margin-top: 16px;" v-if="result.key_metrics?.length">
        <template #header>
          <span>关键指标</span>
        </template>

        <el-row :gutter="16">
          <el-col :span="8" v-for="(metric, idx) in result.key_metrics" :key="idx">
            <div class="metric-card">
              <div class="metric-name">{{ metric.name }}</div>
              <div class="metric-value">
                {{ metric.value }}
                <span class="unit">{{ metric.unit }}</span>
              </div>
              <div class="metric-desc">{{ metric.description }}</div>
            </div>
          </el-col>
        </el-row>
      </el-card>

      <!-- 风险提示 -->
      <el-card style="margin-top: 16px;" v-if="result.risk_warnings?.length">
        <template #header>
          <span>风险提示</span>
        </template>

        <el-alert
          v-for="(warning, idx) in result.risk_warnings"
          :key="idx"
          type="warning"
          :closable="false"
          show-icon
          style="margin-bottom: 8px;"
        >
          {{ warning }}
        </el-alert>
      </el-card>

      <!-- 近期表现 -->
      <el-card style="margin-top: 16px;" v-if="result.recent_performance">
        <template #header>
          <span>近期表现参考</span>
        </template>

        <el-descriptions :column="2" border>
          <el-descriptions-item label="市场阶段">
            {{ translateMarketPhase(result.recent_performance.market_phase) }}
          </el-descriptions-item>
          <el-descriptions-item label="严格条件数">
            {{ result.recent_performance.strict_conditions_count || 0 }} 项
          </el-descriptions-item>
        </el-descriptions>
      </el-card>

      <!-- 合规声明 -->
      <el-alert
        type="info"
        :closable="false"
        show-icon
        style="margin-top: 16px;"
      >
        <template #title>
          免责声明：以上分析仅基于历史数据和规则匹配，不构成任何投资建议。投资有风险，决策需谨慎。
        </template>
      </el-alert>
    </template>

    <el-empty v-else description="暂无结果，请先执行体检任务" />
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { useRoute } from 'vue-router'
import { ElMessage } from 'element-plus'
// Icons used in template
import axios from 'axios'

const route = useRoute()
const loading = ref(false)
const result = ref<any>(null)

// 获取适配度标签类型
const getFitnessType = (level: string) => {
  const map: Record<string, string> = {
    high: 'success',
    medium: 'warning',
    low: 'danger',
  }
  return map[level] || 'info'
}

// 翻译适配度等级
const translateFitnessLevel = (level: string) => {
  const map: Record<string, string> = {
    high: '高',
    medium: '中等',
    low: '低',
  }
  return map[level] || level
}

// 翻译市场阶段
const translateMarketPhase = (phase: string) => {
  const map: Record<string, string> = {
    bullish: '上升趋势',
    bearish: '下行趋势',
    sideways: '震荡整理',
    unknown: '数据不足',
  }
  return map[phase] || phase
}

// 加载结果
const loadResult = async () => {
  const taskId = route.params.taskId as string
  if (!taskId) return

  loading.value = true
  try {
    // 轮询等待结果
    let attempts = 0
    const maxAttempts = 30

    while (attempts < maxAttempts) {
      const response = await axios.get(`/api/investment/checkup-tasks/${taskId}/result`)

      if (response.data.success && response.data.data && Object.keys(response.data.data).length > 0) {
        result.value = response.data.data
        break
      }

      // 检查任务状态
      const taskResponse = await axios.get(`/api/investment/tasks/${taskId}`)
      const status = taskResponse.data.data?.status

      if (status === 'failed') {
        ElMessage.error('体检任务执行失败')
        break
      }

      if (status === 'data_insufficient') {
        // 数据不足也是有效结果
        const resultResponse = await axios.get(`/api/investment/checkup-tasks/${taskId}/result`)
        if (resultResponse.data.data) {
          result.value = resultResponse.data.data
        }
        break
      }

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
.checkup-results {
  padding: 20px;
}

.fitness-card .card-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
}

.fitness-summary h4 {
  margin: 0 0 12px 0;
  color: #303133;
}

.fitness-summary p {
  margin: 0;
  line-height: 1.8;
  color: #606266;
  white-space: pre-wrap;
}

.data-status {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 14px;
  color: #606266;
}

.data-status .note {
  color: #909399;
  font-size: 13px;
}

.metric-card {
  background: #f5f7fa;
  border-radius: 8px;
  padding: 16px;
  text-align: center;
  margin-bottom: 16px;
}

.metric-name {
  font-size: 13px;
  color: #909399;
  margin-bottom: 8px;
}

.metric-value {
  font-size: 28px;
  font-weight: bold;
  color: #303133;
}

.metric-value .unit {
  font-size: 14px;
  font-weight: normal;
  color: #909399;
  margin-left: 4px;
}

.metric-desc {
  font-size: 12px;
  color: #909399;
  margin-top: 8px;
}
</style>
