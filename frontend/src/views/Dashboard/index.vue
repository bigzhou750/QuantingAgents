<template>
  <div class="dashboard">
    <!-- 欢迎区 -->
    <div class="welcome-section">
      <div class="welcome-content">
        <div class="welcome-greeting">
          <span class="greeting-text">早安，{{ userName }}</span>
          <span class="version-tag">v1.0.1</span>
        </div>
        <h1 class="welcome-title">开启今日投资分析</h1>
        <p class="welcome-subtitle">多智能体协作，辅助你更全面地看市场</p>
      </div>
      <div class="welcome-actions">
        <el-button type="primary" size="large" @click="quickAnalysis">
          <el-icon><TrendCharts /></el-icon>
          快速分析
        </el-button>
        <el-button size="large" @click="goToScreening">
          <el-icon><Search /></el-icon>
          股票筛选
        </el-button>
      </div>
    </div>

    <!-- 数据概览 -->
    <div class="stats-overview">
      <div class="stat-item">
        <div class="stat-icon blue">
          <el-icon><Document /></el-icon>
        </div>
        <div class="stat-info">
          <div class="stat-value">{{ userStats.totalAnalyses }}</div>
          <div class="stat-label">总分析数</div>
        </div>
      </div>
      <div class="stat-item">
        <div class="stat-icon green">
          <el-icon><CircleCheck /></el-icon>
        </div>
        <div class="stat-info">
          <div class="stat-value">{{ userStats.successfulAnalyses }}</div>
          <div class="stat-label">已完成</div>
        </div>
      </div>
      <div class="stat-item">
        <div class="stat-icon orange">
          <el-icon><Timer /></el-icon>
        </div>
        <div class="stat-info">
          <div class="stat-value">{{ concurrentRunning }}</div>
          <div class="stat-label">进行中</div>
        </div>
      </div>
      <div class="stat-item">
        <div class="stat-icon purple">
          <el-icon><Star /></el-icon>
        </div>
        <div class="stat-info">
          <div class="stat-value">{{ favoriteStocks.length }}</div>
          <div class="stat-label">自选股</div>
        </div>
      </div>
    </div>

    <!-- 主内容区 -->
    <el-row :gutter="24" class="main-content">
      <!-- 左侧：快速操作 + 最近分析 + 市场快讯 -->
      <el-col :lg="16" :md="24" :sm="24">
        <!-- 快速操作 -->
        <el-card class="quick-actions-card" shadow="never">
          <template #header>
            <span class="section-title">快速操作</span>
          </template>
          <div class="quick-actions">
            <div class="action-item" @click="goToSingleAnalysis">
              <div class="action-icon blue">
                <el-icon><Document /></el-icon>
              </div>
              <div class="action-content">
                <h3>单股分析</h3>
                <p>深度分析单只股票</p>
              </div>
              <el-icon class="action-arrow"><ArrowRight /></el-icon>
            </div>

            <div class="action-item" @click="goToBatchAnalysis">
              <div class="action-icon green">
                <el-icon><Files /></el-icon>
              </div>
              <div class="action-content">
                <h3>批量分析</h3>
                <p>同时分析多只股票</p>
              </div>
              <el-icon class="action-arrow"><ArrowRight /></el-icon>
            </div>

            <div class="action-item" @click="goToScreening">
              <div class="action-icon orange">
                <el-icon><Search /></el-icon>
              </div>
              <div class="action-content">
                <h3>选股器</h3>
                <p>多维度筛选优质股票</p>
              </div>
              <el-icon class="action-arrow"><ArrowRight /></el-icon>
            </div>

            <div class="action-item" @click="goToQueue">
              <div class="action-icon purple">
                <el-icon><List /></el-icon>
              </div>
              <div class="action-content">
                <h3>分析任务</h3>
                <p>查看和管理任务列表</p>
              </div>
              <el-icon class="action-arrow"><ArrowRight /></el-icon>
            </div>
          </div>
        </el-card>

        <!-- 最近分析 -->
        <el-card class="recent-analyses-card" shadow="never" style="margin-top: 24px;">
          <template #header>
            <div class="card-header">
              <span class="section-title">最近分析</span>
              <el-button link type="primary" size="small" @click="goToHistory">
                查看全部 <el-icon><ArrowRight /></el-icon>
              </el-button>
            </div>
          </template>
          <el-table :data="recentAnalyses" style="width: 100%" class="recent-table">
            <el-table-column prop="stock_code" label="股票代码" width="110" />
            <el-table-column prop="stock_name" label="股票名称" width="130" />
            <el-table-column prop="status" label="状态" width="90">
              <template #default="{ row }">
                <el-tag :type="getStatusType(row.status)" effect="light" round size="small">
                  {{ getStatusText(row.status) }}
                </el-tag>
              </template>
            </el-table-column>
            <el-table-column prop="start_time" label="创建时间" width="160">
              <template #default="{ row }">
                {{ formatTime(row.start_time) }}
              </template>
            </el-table-column>
            <el-table-column label="操作" min-width="120">
              <template #default="{ row }">
                <el-button link type="primary" size="small" @click="viewAnalysis(row)">查看</el-button>
                <el-button
                  v-if="row.status === 'completed'"
                  link
                  type="primary"
                  size="small"
                  @click="downloadReport(row)"
                >下载</el-button>
              </template>
            </el-table-column>
          </el-table>
        </el-card>

        <!-- 市场快讯 -->
        <el-card class="market-news-card" shadow="never" style="margin-top: 24px;">
          <template #header>
            <span class="section-title">市场快讯</span>
          </template>
          <div v-if="marketNews.length > 0" class="news-list">
            <div
              v-for="news in marketNews.slice(0, 5)"
              :key="news.id"
              class="news-item"
              @click="openNewsUrl(news.url)"
            >
              <div class="news-title">{{ news.title }}</div>
              <div class="news-meta">
                <span class="news-source">{{ news.source }}</span>
                <span class="news-time">{{ formatTime(news.time) }}</span>
              </div>
            </div>
          </div>
          <div v-else class="empty-state">
            <el-icon class="empty-icon"><InfoFilled /></el-icon>
            <p>暂无市场快讯</p>
          </div>
        </el-card>
      </el-col>

      <!-- 右侧：自选股和模拟交易 -->
      <el-col :lg="8" :md="24" :sm="24">
        <!-- 我的自选股 -->
        <el-card class="favorites-card" shadow="never">
          <template #header>
            <div class="card-header">
              <span class="section-title">自选股</span>
              <el-button link type="primary" size="small" @click="goToFavorites">
                查看全部 <el-icon><ArrowRight /></el-icon>
              </el-button>
            </div>
          </template>

          <div v-if="favoriteStocks.length === 0" class="empty-favorites">
            <el-empty description="暂无自选股" :image-size="60">
              <el-button type="primary" size="small" @click="goToFavorites">添加自选股</el-button>
            </el-empty>
          </div>

          <div v-else class="favorites-list">
            <div
              v-for="stock in favoriteStocks.slice(0, 5)"
              :key="stock.stock_code"
              class="favorite-item"
              @click="viewStockDetail(stock)"
            >
              <div class="stock-info">
                <div class="stock-code">{{ stock.stock_code }}</div>
                <div class="stock-name">{{ stock.stock_name }}</div>
              </div>
              <div class="stock-price">
                <div class="current-price">{{ formatPrice(stock.current_price) }}</div>
                <div class="change-percent" :class="getPriceChangeClass(stock.change_percent)">
                  {{ stock.change_percent > 0 ? '+' : '' }}{{ Number(stock.change_percent).toFixed(2) }}%
                </div>
              </div>
            </div>
          </div>
        </el-card>

        <!-- 模拟交易账户 -->
        <el-card class="paper-trading-card" shadow="never" style="margin-top: 24px;">
          <template #header>
            <div class="card-header">
              <span class="section-title">模拟账户</span>
              <el-button link type="primary" size="small" @click="goToPaperTrading">
                详情 <el-icon><ArrowRight /></el-icon>
              </el-button>
            </div>
          </template>

          <div v-if="paperAccount" class="paper-account-info">
            <div class="account-summary">
              <div class="summary-label">总资产</div>
              <div class="summary-value primary">¥{{ formatMoney(getCurrencyAmount(paperAccount.equity, 'CNY')) }}</div>
            </div>
            <div class="account-row">
              <div class="account-row-item">
                <span class="row-label">现金</span>
                <span class="row-value">¥{{ formatMoney(getCurrencyAmount(paperAccount.cash, 'CNY')) }}</span>
              </div>
              <div class="account-row-item">
                <span class="row-label">持仓</span>
                <span class="row-value">¥{{ formatMoney(getCurrencyAmount(paperAccount.positions_value, 'CNY')) }}</span>
              </div>
            </div>
          </div>

          <div v-else class="empty-state">
            <el-icon class="empty-icon"><InfoFilled /></el-icon>
            <p>暂无账户信息</p>
            <el-button type="primary" size="small" @click="goToPaperTrading">查看模拟交易</el-button>
          </div>
        </el-card>
      </el-col>
    </el-row>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { useAuthStore } from '@/stores/auth'
import {
  TrendCharts,
  Search,
  Document,
  Files,
  List,
  ArrowRight,
  InfoFilled,
  CircleCheck,
  Timer,
  Star
} from '@element-plus/icons-vue'
import { ElMessage } from 'element-plus'
import type { AnalysisTask, AnalysisStatus } from '@/types/analysis'
import { favoritesApi } from '@/api/favorites'
import { analysisApi } from '@/api/analysis'
import { newsApi } from '@/api/news'
import { paperApi, type PaperAccountSummary } from '@/api/paper'

const router = useRouter()
const authStore = useAuthStore()

const userName = computed(() => authStore.user?.username || '投资者')

const userStats = ref({
  totalAnalyses: 0,
  successfulAnalyses: 0,
  concurrentRunning: 0
})

const recentAnalyses = ref<AnalysisTask[]>([])
const favoriteStocks = ref<any[]>([])
const marketNews = ref<any[]>([])
const paperAccount = ref<PaperAccountSummary | null>(null)

const concurrentRunning = computed(() => recentAnalyses.value.filter((x: any) => ['processing', 'running', 'pending', 'queued'].includes(x.status)).length)

const getCurrencyAmount = (
  amount: number | { CNY: number; HKD: number; USD: number } | undefined,
  currency: 'CNY' | 'HKD' | 'USD',
  fallback = 0
): number => {
  if (typeof amount === 'number') return amount
  return amount?.[currency] ?? fallback
}

const quickAnalysis = () => { router.push('/analysis/single') }
const goToSingleAnalysis = () => { router.push('/analysis/single') }
const goToBatchAnalysis = () => { router.push('/analysis/batch') }
const goToScreening = () => { router.push('/screening') }
const goToQueue = () => { router.push('/tasks') }
const goToHistory = () => { router.push('/tasks?tab=completed') }

const viewAnalysis = (analysis: AnalysisTask) => {
  const status = (analysis as any)?.status
  if (status === 'completed') {
    router.push({ name: 'ReportDetail', params: { id: analysis.task_id } })
  } else {
    router.push('/tasks?tab=running')
  }
}

const downloadReport = async (analysis: AnalysisTask) => {
  try {
    const reportId = analysis.task_id
    const res = await fetch(`/api/reports/${reportId}/download?format=markdown`, {
      headers: { 'Authorization': `Bearer ${authStore.token}` }
    })
    if (!res.ok) {
      ElMessage.error('下载失败，报告可能尚未生成')
      return
    }
    const blob = await res.blob()
    const url = window.URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    const code = (analysis as any).stock_code || (analysis as any).stock_symbol || 'stock'
    const dateStr = (analysis as any).analysis_date || (analysis as any).start_time || ''
    a.download = `${code}_分析报告_${String(dateStr).slice(0,10)}.md`
    document.body.appendChild(a)
    a.click()
    window.URL.revokeObjectURL(url)
    document.body.removeChild(a)
    ElMessage.success('报告已开始下载')
  } catch (err) {
    ElMessage.error('下载失败，请稍后重试')
  }
}

const openNewsUrl = (url?: string) => {
  if (url) window.open(url, '_blank')
  else ElMessage.info('该新闻暂无详情链接')
}

const getStatusType = (status: string | AnalysisStatus): 'success' | 'info' | 'warning' | 'danger' => {
  const statusMap: Record<string, 'success' | 'info' | 'warning' | 'danger'> = {
    pending: 'info', processing: 'warning', running: 'warning', completed: 'success', failed: 'danger', cancelled: 'info'
  }
  return statusMap[status] || 'info'
}

const getStatusText = (status: string | AnalysisStatus) => {
  const statusMap: Record<string, string> = {
    pending: '等待中', processing: '处理中', running: '处理中', completed: '已完成', failed: '失败', cancelled: '已取消'
  }
  return statusMap[status] || String(status)
}

import { formatDateTime } from '@/utils/datetime'
const formatTime = (time: string) => formatDateTime(time)

const goToFavorites = () => { router.push('/favorites') }
const viewStockDetail = (stock: any) => { router.push(`/analysis/single?stock_code=${stock.stock_code}`) }
const getPriceChangeClass = (changePercent: number) => {
  if (changePercent > 0) return 'price-up'
  if (changePercent < 0) return 'price-down'
  return 'price-neutral'
}

const formatPrice = (price?: number) => {
  if (price === undefined || price === null) return '-'
  return Number(price).toFixed(2)
}

const loadFavoriteStocks = async () => {
  try {
    const response = await favoritesApi.list()
    if (response.success && response.data) {
      favoriteStocks.value = response.data.map((item: any) => ({
        stock_code: item.stock_code,
        stock_name: item.stock_name,
        current_price: item.current_price || 0,
        change_percent: item.change_percent || 0
      }))
    }
  } catch (error) {
    console.error('加载自选股失败:', error)
  }
}

const loadRecentAnalyses = async () => {
  try {
    const res = await analysisApi.getTaskList({ limit: 10, offset: 0, status: undefined })
    const body: any = (res as any)?.data?.data || (res as any)?.data || res || {}
    const tasks = body.tasks || []
    recentAnalyses.value = tasks
    userStats.value.totalAnalyses = body.total ?? tasks.length
    userStats.value.successfulAnalyses = tasks.filter((item: any) => item.status === 'completed').length
    userStats.value.concurrentRunning = tasks.filter((item: any) => ['processing', 'running', 'pending', 'queued'].includes(item.status)).length
  } catch (error) {
    console.error('加载最近分析失败:', error)
    recentAnalyses.value = []
  }
}

const loadMarketNews = async () => {
  try {
    let response = await newsApi.getLatestNews(undefined, 10, 24)
    if (response.success && response.data && response.data.news.length === 0) {
      response = await newsApi.getLatestNews(undefined, 10, 24 * 365)
    }
    if (response.success && response.data) {
      marketNews.value = response.data.news.map((item: any) => ({
        id: item.id || item.title,
        title: item.title,
        time: item.publish_time,
        url: item.url,
        source: item.source
      }))
    }
  } catch (error) {
    console.error('加载市场快讯失败:', error)
    marketNews.value = []
  }
}

const loadPaperAccount = async () => {
  try {
    const response = await paperApi.getAccount()
    if (response.success && response.data) {
      paperAccount.value = response.data.account
    }
  } catch (error) {
    console.error('加载模拟交易账户失败:', error)
    paperAccount.value = null
  }
}

const goToPaperTrading = () => { router.push('/paper') }

const formatMoney = (value: number) => {
  return value.toFixed(2).replace(/\B(?=(\d{3})+(?!\d))/g, ',')
}

onMounted(async () => {
  await loadFavoriteStocks()
  await loadRecentAnalyses()
  await loadMarketNews()
  await loadPaperAccount()
})
</script>

<style lang="scss" scoped>
.dashboard {
  .welcome-section {
    background: var(--zt-gradient-hero);
    border-radius: 20px;
    padding: 36px 40px;
    color: white;
    margin-bottom: 24px;
    display: flex;
    justify-content: space-between;
    align-items: center;
    box-shadow: 0 10px 25px -5px rgba(14, 165, 233, 0.3);

    .welcome-content {
      .welcome-greeting {
        display: flex;
        align-items: center;
        gap: 12px;
        margin-bottom: 10px;

        .greeting-text {
          font-size: 14px;
          opacity: 0.95;
          font-weight: 500;
        }

        .version-tag {
          background: rgba(255, 255, 255, 0.18);
          padding: 2px 10px;
          border-radius: 20px;
          font-size: 12px;
          font-weight: 500;
        }
      }

      .welcome-title {
        font-size: 28px;
        font-weight: 700;
        margin: 0 0 8px 0;
        color: #fff;
      }

      .welcome-subtitle {
        font-size: 15px;
        opacity: 0.9;
        margin: 0;
      }
    }

    .welcome-actions {
      display: flex;
      gap: 12px;

      .el-button {
        border-radius: 10px;

        &:not(.el-button--primary) {
          background: rgba(255, 255, 255, 0.15);
          border: 1px solid rgba(255, 255, 255, 0.25);
          color: #fff;

          &:hover {
            background: rgba(255, 255, 255, 0.25);
          }
        }
      }
    }
  }

  .stats-overview {
    display: grid;
    grid-template-columns: repeat(4, 1fr);
    gap: 16px;
    margin-bottom: 24px;

    @media (max-width: 992px) {
      grid-template-columns: repeat(2, 1fr);
    }

    @media (max-width: 576px) {
      grid-template-columns: 1fr;
    }

    .stat-item {
      background: var(--el-bg-color);
      border: 1px solid var(--el-border-color-light);
      border-radius: 16px;
      padding: 18px 20px;
      display: flex;
      align-items: center;
      gap: 14px;
      transition: transform 0.2s ease, box-shadow 0.2s ease;

      &:hover {
        transform: translateY(-2px);
        box-shadow: 0 10px 15px -3px rgba(15, 23, 42, 0.06);
      }

      .stat-icon {
        width: 44px;
        height: 44px;
        border-radius: 12px;
        display: flex;
        align-items: center;
        justify-content: center;
        font-size: 22px;

        &.blue { background: #DBEAFE; color: #1E40AF; }
        &.green { background: #D1FAE5; color: #047857; }
        &.orange { background: #FEF3C7; color: #B45309; }
        &.purple { background: #E0E7FF; color: #4338CA; }
      }

      .stat-info {
        .stat-value {
          font-size: 22px;
          font-weight: 700;
          color: var(--el-text-color-primary);
          line-height: 1.2;
        }

        .stat-label {
          font-size: 13px;
          color: var(--el-text-color-secondary);
          margin-top: 2px;
        }
      }
    }
  }

  .section-title {
    font-size: 16px;
    font-weight: 600;
    color: var(--el-text-color-primary);
  }

  .quick-actions-card {
    :deep(.el-card__header) {
      padding: 18px 20px;
    }

    .quick-actions {
      display: grid;
      grid-template-columns: repeat(2, 1fr);
      gap: 16px;

      @media (max-width: 576px) {
        grid-template-columns: 1fr;
      }

      .action-item {
        display: flex;
        align-items: center;
        gap: 14px;
        padding: 18px;
        border: 1px solid var(--el-border-color-lighter);
        border-radius: 14px;
        cursor: pointer;
        transition: all 0.2s ease;

        &:hover {
          border-color: var(--el-color-primary-light-5);
          background: var(--el-color-primary-light-9);
          transform: translateY(-2px);
          box-shadow: 0 4px 12px rgba(14, 165, 233, 0.1);

          .action-arrow {
            transform: translateX(4px);
            color: var(--el-color-primary);
          }
        }

        .action-icon {
          width: 44px;
          height: 44px;
          border-radius: 12px;
          display: flex;
          align-items: center;
          justify-content: center;
          font-size: 20px;
          flex-shrink: 0;

          &.blue { background: #E0F2FE; color: #0EA5E9; }
          &.green { background: #D1FAE5; color: #10B981; }
          &.orange { background: #FEF3C7; color: #F59E0B; }
          &.purple { background: #EDE9FE; color: #8B5CF6; }
        }

        .action-content {
          flex: 1;

          h3 {
            margin: 0 0 4px 0;
            font-size: 15px;
            font-weight: 600;
            color: var(--el-text-color-primary);
          }

          p {
            margin: 0;
            font-size: 13px;
            color: var(--el-text-color-secondary);
          }
        }

        .action-arrow {
          color: var(--el-text-color-placeholder);
          transition: all 0.2s ease;
        }
      }
    }
  }

  .recent-analyses-card {
    :deep(.el-card__header) {
      padding: 18px 20px;
    }

    .card-header {
      display: flex;
      justify-content: space-between;
      align-items: center;
    }

    .recent-table {
      border-radius: 10px;
      overflow: hidden;
    }
  }

  .market-news-card {
    :deep(.el-card__header) {
      padding: 18px 20px;
    }

    .news-list {
      .news-item {
        padding: 14px 0;
        cursor: pointer;
        border-bottom: 1px solid var(--el-border-color-lighter);
        transition: background-color 0.2s ease;

        &:last-child {
          border-bottom: none;
        }

        &:hover {
          background-color: var(--el-fill-color-lighter);
          margin: 0 -20px;
          padding: 14px 20px;
          border-radius: 10px;
        }

        .news-title {
          font-size: 14px;
          color: var(--el-text-color-primary);
          margin-bottom: 6px;
          line-height: 1.5;
          font-weight: 500;
        }

        .news-meta {
          display: flex;
          gap: 10px;
          font-size: 12px;
          color: var(--el-text-color-placeholder);

          .news-source {
            color: var(--el-color-primary);
            font-weight: 500;
          }
        }
      }
    }

    .empty-state {
      text-align: center;
      padding: 30px 0;

      .empty-icon {
        font-size: 40px;
        color: var(--el-text-color-placeholder);
        margin-bottom: 10px;
      }

      p {
        color: var(--el-text-color-secondary);
        margin: 0;
      }
    }
  }

  .favorites-card {
    :deep(.el-card__header) {
      padding: 18px 20px;
    }

    .card-header {
      display: flex;
      justify-content: space-between;
      align-items: center;
    }

    .empty-favorites {
      text-align: center;
      padding: 20px 0;
    }

    .favorites-list {
      .favorite-item {
        display: flex;
        justify-content: space-between;
        align-items: center;
        padding: 12px 0;
        border-bottom: 1px solid var(--el-border-color-lighter);
        cursor: pointer;
        transition: background-color 0.2s ease;

        &:hover {
          background-color: var(--el-fill-color-lighter);
          margin: 0 -20px;
          padding: 12px 20px;
          border-radius: 10px;
        }

        &:last-child {
          border-bottom: none;
        }

        .stock-info {
          .stock-code {
            font-weight: 600;
            font-size: 14px;
            color: var(--el-text-color-primary);
          }

          .stock-name {
            font-size: 12px;
            color: var(--el-text-color-secondary);
            margin-top: 2px;
          }
        }

        .stock-price {
          text-align: right;

          .current-price {
            font-weight: 600;
            font-size: 14px;
            color: var(--el-text-color-primary);
          }

          .change-percent {
            font-size: 12px;
            margin-top: 2px;
            font-weight: 500;

            &.price-up { color: #EF4444; }
            &.price-down { color: #10B981; }
            &.price-neutral { color: var(--el-text-color-secondary); }
          }
        }
      }
    }
  }

  .paper-trading-card {
    :deep(.el-card__header) {
      padding: 18px 20px;
    }

    .card-header {
      display: flex;
      justify-content: space-between;
      align-items: center;
    }

    .paper-account-info {
      .account-summary {
        text-align: center;
        padding: 16px 0 20px;
        border-bottom: 1px solid var(--el-border-color-lighter);
        margin-bottom: 16px;

        .summary-label {
          font-size: 13px;
          color: var(--el-text-color-secondary);
          margin-bottom: 6px;
        }

        .summary-value {
          font-size: 26px;
          font-weight: 700;
          color: var(--el-text-color-primary);

          &.primary {
            color: var(--el-color-primary);
          }
        }
      }

      .account-row {
        display: flex;
        justify-content: space-between;
        gap: 12px;

        .account-row-item {
          flex: 1;
          text-align: center;
          padding: 10px;
          background: var(--el-fill-color-lighter);
          border-radius: 10px;

          .row-label {
            display: block;
            font-size: 12px;
            color: var(--el-text-color-secondary);
            margin-bottom: 4px;
          }

          .row-value {
            font-size: 14px;
            font-weight: 600;
            color: var(--el-text-color-primary);
          }
        }
      }
    }

    .empty-state {
      text-align: center;
      padding: 20px 0;

      .empty-icon {
        font-size: 40px;
        color: var(--el-text-color-placeholder);
        margin-bottom: 10px;
      }

      p {
        color: var(--el-text-color-secondary);
        margin-bottom: 16px;
      }
    }
  }
}

// 响应式设计
@media (max-width: 768px) {
  .dashboard {
    .welcome-section {
      flex-direction: column;
      text-align: center;
      gap: 24px;
      padding: 28px 24px;

      .welcome-actions {
        justify-content: center;
      }
    }
  }
}
</style>
