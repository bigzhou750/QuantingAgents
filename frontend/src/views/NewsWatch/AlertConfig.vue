<template>
  <div class="alert-config">
    <el-card shadow="never" class="header-card">
      <div class="page-header">
        <div>
          <h2 style="margin: 0 0 4px 0;">告警配置与模拟投递</h2>
          <span class="subtitle">设置新闻影响告警阈值，查看模拟告警记录</span>
        </div>
      </div>
    </el-card>

    <!-- 告警阈值配置 -->
    <el-card style="margin-bottom: 16px;">
      <template #header>
        <span>告警阈值</span>
      </template>
      <el-form label-width="120px">
        <el-form-item label="触发等级">
          <el-radio-group v-model="threshold" @change="saveThreshold">
            <el-radio value="low">低等级及以上（低/中/高都告警）</el-radio>
            <el-radio value="medium">中等及以上（中/高告警）</el-radio>
            <el-radio value="high">仅高等级</el-radio>
          </el-radio-group>
        </el-form-item>
        <el-form-item>
          <el-alert type="info" :closable="false" show-icon>
            <template #title>
              告警基于持仓新闻影响的三档分级（低/中/高）。所有告警均为模拟投递，不会实际发送短信或微信消息。
            </template>
          </el-alert>
        </el-form-item>
      </el-form>
    </el-card>

    <!-- 手动触发模拟检测 -->
    <el-card style="margin-bottom: 16px;">
      <template #header>
        <div class="card-header">
          <span>模拟告警检测</span>
          <el-button type="primary" @click="simulateAlerts" :loading="simulating">
            立即检测
          </el-button>
        </div>
      </template>
      <p class="simulate-desc">
        点击"立即检测"会执行一次持仓影响分析，并根据当前阈值生成模拟告警记录。
        同一标的 24 小时内不会重复告警。
      </p>
      <el-alert
        v-if="simulateResult !== null"
        :type="simulateResult.generated_count > 0 ? 'warning' : 'success'"
        :closable="false"
        show-icon
        style="margin-top: 12px;"
      >
        <template #title>
          {{ simulateResult.note }}
          <span v-if="simulateResult.generated_count > 0">
            本次生成 {{ simulateResult.generated_count }} 条模拟告警。
          </span>
          <span v-else> 本次未触发新的告警。</span>
        </template>
      </el-alert>
    </el-card>

    <!-- 告警记录列表 -->
    <el-card>
      <template #header>
        <div class="card-header">
          <span>告警记录</span>
          <el-button link @click="loadAlerts">
            <el-icon><Refresh /></el-icon>
            刷新
          </el-button>
        </div>
      </template>

      <el-empty v-if="!alertsLoading && alerts.length === 0" description="暂无告警记录" />

      <el-table v-else :data="alerts" v-loading="alertsLoading" border stripe>
        <el-table-column label="状态" width="100">
          <template #default="{ row }">
            <el-tag type="info" size="small" effect="plain">
              {{ row.status === 'simulated' ? '模拟' : row.status }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="stock_code" label="代码" width="100" />
        <el-table-column prop="stock_name" label="名称" width="140" />
        <el-table-column label="影响等级" width="100">
          <template #default="{ row }">
            <el-tag :type="getImpactTagType(row.impact_level)" size="small">
              {{ translateImpactLevel(row.impact_level) }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column label="渠道" width="100">
          <template #default="{ row }">
            <span class="channel-label">{{ row.channel === 'simulated' ? '模拟投递' : row.channel }}</span>
          </template>
        </el-table-column>
        <el-table-column label="触发原因" min-width="200">
          <template #default="{ row }">
            <span class="trigger-reason">{{ row.trigger_reason }}</span>
          </template>
        </el-table-column>
        <el-table-column label="时间" width="170">
          <template #default="{ row }">
            {{ formatTime(row.created_at) }}
          </template>
        </el-table-column>
      </el-table>

      <el-alert
        type="info"
        :closable="false"
        show-icon
        style="margin-top: 12px;"
      >
        <template #title>
          以上所有记录均为模拟告警，用于验证触发逻辑和文案，未实际发送任何外部消息。
        </template>
      </el-alert>
    </el-card>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { ElMessage } from 'element-plus'
import { Refresh } from '@element-plus/icons-vue'
import axios from 'axios'

const threshold = ref('medium')
const simulating = ref(false)
const simulateResult = ref<any>(null)
const alerts = ref<any[]>([])
const alertsLoading = ref(false)

const loadConfig = async () => {
  try {
    const res = await axios.get('/api/news-watch/alerts/config')
    threshold.value = res.data?.data?.threshold || 'medium'
  } catch {
    // use default
  }
}

const saveThreshold = async (val: string | number | boolean | undefined) => {
  if (typeof val !== 'string') return
  try {
    await axios.put('/api/news-watch/alerts/config', { threshold: val })
    ElMessage.success('告警阈值已更新')
  } catch {
    ElMessage.error('保存失败')
  }
}

const simulateAlerts = async () => {
  simulating.value = true
  simulateResult.value = null
  try {
    const res = await axios.post('/api/news-watch/alerts/simulate', null, {
      params: { hours_back: 72 },
    })
    simulateResult.value = res.data?.data
    loadAlerts()
  } catch {
    ElMessage.error('模拟检测失败')
  } finally {
    simulating.value = false
  }
}

const loadAlerts = async () => {
  alertsLoading.value = true
  try {
    const res = await axios.get('/api/news-watch/alerts', { params: { limit: 100 } })
    alerts.value = res.data?.data?.records || []
  } catch {
    ElMessage.error('加载告警记录失败')
  } finally {
    alertsLoading.value = false
  }
}

const getImpactTagType = (level: string): 'success' | 'warning' | 'danger' | 'info' => {
  const map: Record<string, 'success' | 'warning' | 'danger' | 'info'> = {
    low: 'info',
    medium: 'warning',
    high: 'danger',
  }
  return map[level] || 'info'
}

const translateImpactLevel = (level: string) => {
  const map: Record<string, string> = { low: '低', medium: '中', high: '高' }
  return map[level] || level
}

const formatTime = (iso: string) => {
  if (!iso) return ''
  try {
    return new Date(iso).toLocaleString('zh-CN')
  } catch {
    return iso
  }
}

onMounted(() => {
  loadConfig()
  loadAlerts()
})
</script>

<style scoped>
.alert-config {
  padding: 20px;
}

.header-card {
  margin-bottom: 16px;
}

.page-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
}

.subtitle {
  font-size: 13px;
  color: #909399;
}

.card-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
}

.simulate-desc {
  font-size: 13px;
  color: #606266;
  margin: 0;
}

.channel-label {
  font-size: 13px;
  color: #909399;
}

.trigger-reason {
  font-size: 13px;
  color: #606266;
}
</style>
