<template>
  <div class="investment-home" v-loading="loading">
    <!-- 欢迎区域 -->
    <el-card class="welcome-card">
      <div class="welcome-header">
        <h2>👋 你好，{{ userName }}</h2>
        <p class="welcome-subtitle">这是你的个人投资助手工作台</p>
      </div>

      <!-- 主行动卡片 -->
      <div class="primary-action" v-if="primaryAction">
        <el-card shadow="hover" class="action-card" :class="'action-' + primaryAction.type">
          <div class="action-icon">{{ primaryAction.icon }}</div>
          <div class="action-content">
            <h3>{{ primaryAction.title }}</h3>
            <p>{{ primaryAction.description }}</p>
            <el-button type="primary" @click="handlePrimaryAction">{{ primaryAction.buttonText }}</el-button>
          </div>
        </el-card>
      </div>
    </el-card>

    <!-- 状态摘要网格 -->
    <el-row :gutter="16" style="margin-top: 16px;">
      <!-- 画像状态 -->
      <el-col :span="8">
        <el-card shadow="hover" class="status-card">
          <template #header>
            <div class="card-header">
              <span>📊 投资画像</span>
              <el-tag v-if="summary.profile?.exists" type="success" size="small">已完成</el-tag>
              <el-tag v-else type="warning" size="small">未设置</el-tag>
            </div>
          </template>
          <div v-if="summary.profile?.exists">
            <p><strong>风险偏好:</strong> {{ riskLabel(summary.profile.risk_preference) }}</p>
            <p><strong>交易风格:</strong> {{ styleLabel(summary.profile.trading_style) }}</p>
            <p v-if="summary.profile.target_markets?.length">
              <strong>关注市场:</strong> {{ summary.profile.target_markets.join('、') }}
            </p>
          </div>
          <div v-else class="empty-hint">
            <p>完成投资画像后，系统可以为你推荐合适的策略方向。</p>
            <el-button link type="primary" @click="$router.push('/investment/profile')">去设置画像 →</el-button>
          </div>
        </el-card>
      </el-col>

      <!-- 策略状态 -->
      <el-col :span="8">
        <el-card shadow="hover" class="status-card">
          <template #header>
            <div class="card-header">
              <span>🎯 我的策略</span>
              <el-tag v-if="summary.strategies?.active_count > 0" type="success" size="small">
                {{ summary.strategies.active_count }} 个启用
              </el-tag>
              <el-tag v-else type="info" size="small">暂无</el-tag>
            </div>
          </template>
          <div v-if="summary.strategies?.active_count > 0">
            <p v-for="s in (summary.strategies.recent || []).slice(0, 3)" :key="s.strategy_id">
              <el-link type="primary" @click="$router.push('/investment/strategies')">{{ s.name }}</el-link>
              <el-tag size="small" style="margin-left: 4px;">{{ s.status }}</el-tag>
            </p>
          </div>
          <div v-else class="empty-hint">
            <p>策略帮助你系统化地选股和跟踪标的。</p>
            <el-button link type="primary" @click="$router.push('/investment/strategies')">创建第一个策略 →</el-button>
          </div>
        </el-card>
      </el-col>

      <!-- 模拟持仓 -->
      <el-col :span="8">
        <el-card shadow="hover" class="status-card">
          <template #header>
            <div class="card-header">
              <span>💰 模拟持仓</span>
              <el-tag v-if="summary.simulation?.has_positions" type="success" size="small">有持仓</el-tag>
              <el-tag v-else type="info" size="small">空仓</el-tag>
            </div>
          </template>
          <div v-if="summary.simulation?.has_positions">
            <p><strong>持仓数:</strong> {{ summary.simulation.position_count }} 只</p>
            <p><strong>总权益:</strong> ¥{{ formatNumber(summary.simulation.total_equity) }}</p>
            <p v-if="summary.simulation.unrealized_pnl !== undefined">
              <strong>浮动盈亏:</strong>
              <span :style="{ color: summary.simulation.unrealized_pnl >= 0 ? '#67c23a' : '#f56c6c' }">
                {{ summary.simulation.unrealized_pnl >= 0 ? '+' : '' }}¥{{ formatNumber(summary.simulation.unrealized_pnl) }}
              </span>
            </p>
            <el-button link type="primary" @click="$router.push('/paper')">查看持仓详情 →</el-button>
          </div>
          <div v-else class="empty-hint">
            <p>用模拟交易练习投资，不涉及真实资金。</p>
            <el-button link type="primary" @click="$router.push('/paper')">开始模拟交易 →</el-button>
          </div>
        </el-card>
      </el-col>
    </el-row>

    <!-- 最近任务和观察 -->
    <el-row :gutter="16" style="margin-top: 16px;">
      <el-col :span="12">
        <el-card shadow="hover">
          <template #header>
            <div class="card-header">
              <span>📋 最近任务</span>
              <el-button link type="primary" size="small" @click="$router.push('/investment/strategies')">查看全部</el-button>
            </div>
          </template>
          <div v-if="summary.tasks?.recent?.length">
            <div v-for="t in summary.tasks.recent.slice(0, 5)" :key="t.task_id" class="task-item">
              <el-tag size="small" :type="taskStatusType(t.status)">{{ taskStatusLabel(t.status) }}</el-tag>
              <span class="task-type">{{ taskTypeLabel(t.task_type) }}</span>
              <span class="task-time">{{ formatDate(t.created_at) }}</span>
            </div>
          </div>
          <el-empty v-else description="暂无任务记录" :image-size="60" />
        </el-card>
      </el-col>

      <el-col :span="12">
        <el-card shadow="hover">
          <template #header>
            <div class="card-header">
              <span>📋 我的观察</span>
              <el-button link type="primary" size="small" @click="$router.push('/investment/observations')">查看全部</el-button>
            </div>
          </template>
          <!-- 待复盘提示 -->
          <el-alert
            v-if="summary.observations?.pending_review_count > 0"
            type="warning"
            :closable="false"
            show-icon
            style="margin-bottom: 12px;"
          >
            <template #title>
              有 <strong>{{ summary.observations.pending_review_count }}</strong> 条观察标的待复盘
              <el-button link type="warning" size="small" @click="$router.push('/investment/observations')">去复盘 →</el-button>
            </template>
          </el-alert>
          <div v-if="summary.observations?.count > 0">
            <p>正在观察 <strong>{{ summary.observations.count }}</strong> 只标的</p>
            <p v-if="summary.observations.latest_item">
              最近加入: {{ summary.observations.latest_item.stock_name || summary.observations.latest_item.stock_code }}
              <el-tag size="small" type="info">{{ sourceLabel(summary.observations.latest_item.source_type) }}</el-tag>
            </p>
          </div>
          <div v-else class="empty-hint">
            <p>从选股结果或手动添加观察标的，开始你的投资学习闭环。</p>
            <el-button link type="primary" @click="$router.push('/investment/observations')">添加观察 →</el-button>
          </div>
        </el-card>
      </el-col>
    </el-row>

    <!-- 数据状态提示 -->
    <el-card v-if="dataWarnings.length" style="margin-top: 16px;" shadow="never">
      <template #header><span>⚠️ 数据状态提醒</span></template>
      <el-alert v-for="(w, i) in dataWarnings" :key="i" :title="w" type="warning" :closable="false" show-icon style="margin-bottom: 8px;" />
    </el-card>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { ApiClient } from '@/api/request'

const router = useRouter()
const loading = ref(false)
const summary = ref<any>({})
const errors = ref<string[]>([])

const userName = computed(() => summary.value.user_name || '投资者')

const primaryAction = computed(() => {
  const s = summary.value
  if (!s.profile?.exists) {
    return {
      type: 'profile',
      icon: '📊',
      title: '第一步：完成投资画像',
      description: '告诉我们你的风险承受能力和投资偏好，系统才能给出适合你的建议。',
      buttonText: '开始设置画像',
    }
  }
  if (!s.strategies?.active_count) {
    return {
      type: 'strategy',
      icon: '🎯',
      title: '下一步：创建你的第一个策略',
      description: `基于你的${riskLabel(s.profile?.risk_preference)}偏好，系统推荐了适合的策略方向。`,
      buttonText: '浏览策略模板',
    }
  }
  if (!s.observations?.count) {
    return {
      type: 'observation',
      icon: '👁️',
      title: '下一步：关注一些标的',
      description: '选择你策略相关的股票或行业，系统会帮你持续追踪动态。',
      buttonText: '去关注标的',
    }
  }
  if (s.simulation?.has_positions) {
    return {
      type: 'review',
      icon: '📈',
      title: '待复盘：检查模拟持仓表现',
      description: `你有 ${s.simulation.position_count} 只模拟持仓，看看近期表现如何。`,
      buttonText: '查看持仓',
    }
  }
  return null
})

const dataWarnings = computed(() => {
  const w: string[] = []
  if (summary.value.errors) {
    for (const [module, err] of Object.entries(summary.value.errors as Record<string, string>)) {
      w.push(`${module} 数据加载失败: ${err}`)
    }
  }
  return w
})

const loadSummary = async () => {
  loading.value = true
  try {
    const res = await ApiClient.get('/api/investment/home-summary')
    summary.value = res?.data || {}
  } catch (e: any) {
    console.error('Failed to load home summary', e)
    errors.value.push(e?.message || '加载失败')
  } finally {
    loading.value = false
  }
}

const handlePrimaryAction = () => {
  const action = primaryAction.value
  if (!action) return
  switch (action.type) {
    case 'profile': router.push('/investment/profile'); break
    case 'strategy': router.push('/investment/strategies'); break
    case 'observation': router.push('/investment/observations'); break
    case 'review': router.push('/paper'); break
  }
}

// Labels
const riskLabel = (r: string) => ({ conservative: '稳健型', balanced: '平衡型', aggressive: '积极型' }[r] || r || '未知')
const styleLabel = (s: string) => ({ long_term: '长期持有', swing: '波段操作', day_trading: '日内交易' }[s] || s || '未知')
const taskTypeLabel = (t: string) => ({ strategy_screening: '选股', strategy_checkup: '体检' }[t] || t)
const taskStatusLabel = (s: string) => ({ pending: '等待中', running: '执行中', completed: '已完成', failed: '失败' }[s] || s)
const taskStatusType = (s: string) => ({ pending: 'info', running: '', completed: 'success', failed: 'danger' }[s] || '')
const formatDate = (d: string) => d ? new Date(d).toLocaleDateString('zh-CN') : '-'
const formatNumber = (n: number) => n != null ? n.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 }) : '0.00'
const sourceLabel = (type: string) => ({ screening: '策略选股', manual: '手动添加', favorites: '自选股导入', news: '新闻关注' }[type] || type || '')

onMounted(loadSummary)
</script>

<style scoped>
.welcome-card { margin-bottom: 0; }
.welcome-header h2 { margin: 0 0 4px 0; font-size: 22px; }
.welcome-subtitle { color: #909399; margin: 0; }
.primary-action { margin-top: 16px; }
.action-card { display: flex; align-items: center; gap: 16px; padding: 12px; cursor: pointer; transition: all 0.2s; }
.action-card:hover { transform: translateY(-2px); }
.action-icon { font-size: 40px; }
.action-content h3 { margin: 0 0 6px 0; font-size: 18px; }
.action-content p { margin: 0 0 10px 0; color: #606266; }
.status-card { height: 100%; }
.card-header { display: flex; justify-content: space-between; align-items: center; }
.empty-hint { color: #909399; font-size: 13px; }
.empty-hint p { margin: 0 0 8px 0; }
.task-item { display: flex; align-items: center; gap: 8px; padding: 6px 0; border-bottom: 1px solid #f0f0f0; }
.task-item:last-child { border-bottom: none; }
.task-type { font-size: 13px; flex: 1; }
.task-time { font-size: 12px; color: #c0c4cc; }
.muted { color: #c0c4cc; font-size: 12px; }
</style>
