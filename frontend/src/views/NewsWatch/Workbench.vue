<template>
  <div class="news-watch-workbench">
    <!-- 页面标题 -->
    <el-card shadow="never" class="header-card">
      <div class="page-header">
        <div>
          <h2 style="margin: 0 0 4px 0;">关注工作台</h2>
          <span class="subtitle">汇总你关注的股票和新闻，用于研究和观察</span>
        </div>
        <el-button type="primary" plain @click="refreshCollected">
          <el-icon><Refresh /></el-icon>
          刷新
        </el-button>
      </div>
    </el-card>

    <!-- 空状态引导 -->
    <el-card v-if="!loading && items.length === 0" class="empty-guide">
      <el-empty description="还没有收集任何关注对象">
        <template #description>
          <p>你可以从以下位置一键收集：</p>
          <ul class="guide-list">
            <li>📈 <strong>股票详情页</strong> — 点击"加入关注"</li>
            <li>⭐ <strong>自选股列表</strong> — 将已有自选加入关注工作台</li>
            <li>📰 <strong>新闻列表</strong> — 收集感兴趣的新闻条目</li>
          </ul>
          <p class="guide-note">收集只是帮你整理研究对象，不构成任何投资建议。</p>
        </template>
      </el-empty>
    </el-card>

    <!-- 收集记录列表 -->
    <el-card v-else>
      <template #header>
        <div class="card-header">
          <span>最近收集 ({{ items.length }})</span>
          <el-radio-group v-model="filterType" size="small" @change="refreshCollected">
            <el-radio-button value="">全部</el-radio-button>
            <el-radio-button value="stock">股票</el-radio-button>
            <el-radio-button value="news">新闻</el-radio-button>
          </el-radio-group>
        </div>
      </template>

      <el-table :data="items" v-loading="loading" border stripe>
        <el-table-column label="类型" width="80">
          <template #default="{ row }">
            <el-tag :type="row.item_type === 'stock' ? 'primary' : 'info'" size="small">
              {{ row.item_type === 'stock' ? '股票' : '新闻' }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column label="标的/标题" min-width="200">
          <template #default="{ row }">
            <template v-if="row.item_type === 'stock'">
              <strong>{{ row.symbol }}</strong>
              <span v-if="row.title" class="item-title">{{ row.title }}</span>
            </template>
            <template v-else>
              {{ row.title || row.news_id || '未命名新闻' }}
            </template>
          </template>
        </el-table-column>
        <el-table-column label="来源" width="140">
          <template #default="{ row }">
            <span class="source-label">{{ formatSource(row.source_page) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="收集时间" width="170">
          <template #default="{ row }">
            {{ formatTime(row.collected_at) }}
          </template>
        </el-table-column>
        <el-table-column label="操作" width="120" fixed="right">
          <template #default="{ row }">
            <el-button
              v-if="row.item_type === 'stock'"
              size="small"
              type="primary"
              link
              @click="goToDetail(row)"
            >
              查看详情
            </el-button>
            <el-button size="small" type="danger" link @click="removeItem(row)">
              移除
            </el-button>
          </template>
        </el-table-column>
      </el-table>
    </el-card>

    <!-- 相关新闻流 -->
    <el-card class="related-news-card">
      <template #header>
        <div class="card-header">
          <div class="card-header-left">
            <span>相关新闻流</span>
            <span class="source-label">{{ relatedNewsLabel }}</span>
          </div>
          <el-button size="small" type="primary" plain :disabled="relatedNews.length === 0" @click="analyzeBatchNews">
            批量分析
          </el-button>
        </div>
      </template>

      <el-empty v-if="!newsLoading && relatedNews.length === 0" description="暂无相关新闻" />
      <el-skeleton v-else-if="newsLoading" :rows="4" animated />
      <div v-else class="news-list">
        <div v-for="news in relatedNews" :key="news.id || news.url || news.title" class="news-item">
          <div class="news-main">
            <a v-if="news.url" :href="news.url" target="_blank" rel="noopener" class="news-title">
              {{ news.title || '未命名新闻' }}
            </a>
            <span v-else class="news-title">{{ news.title || '未命名新闻' }}</span>
            <div class="news-meta">
              <span>{{ news.symbol || '市场' }}</span>
              <span>{{ news.source || news.data_source || '未知来源' }}</span>
              <span>{{ formatTime(news.publish_time) }}</span>
            </div>
          </div>
          <div class="news-actions">
            <el-button size="small" link type="primary" @click="analyzeOne(news)">分析</el-button>
            <el-button size="small" link type="primary" @click="collectNews(news)">收集</el-button>
            <el-button size="small" link type="warning" @click="observeNews(news)">转观察</el-button>
            <el-button size="small" link type="info" @click="ignoreNews(news)">忽略</el-button>
          </div>
        </div>
      </div>
    </el-card>

    <!-- 来源覆盖与事件聚类 -->
    <el-card v-if="coverageInfo" class="coverage-card">
      <template #header><span>来源覆盖与事件聚类</span></template>
      <el-descriptions :column="3" border>
        <el-descriptions-item label="总条数">{{ coverageInfo.total_count || 0 }}</el-descriptions-item>
        <el-descriptions-item label="来源数量">{{ (coverageInfo.source_statuses || []).length }}</el-descriptions-item>
        <el-descriptions-item label="失败原因">{{ coverageInfo.failure_summary || '无' }}</el-descriptions-item>
      </el-descriptions>
      <div v-if="eventClusters.length" class="cluster-list">
        <div v-for="cluster in eventClusters" :key="cluster.cluster_id" class="cluster-item">
          <strong>{{ cluster.title || '未命名事件' }}</strong>
          <span>{{ cluster.count }} 条</span>
          <span v-if="cluster.symbols?.length">标的：{{ cluster.symbols.join('、') }}</span>
        </div>
      </div>
      <el-empty v-else-if="!eventClusters.length" description="暂无事件聚类" :image-size="48" />
    </el-card>

    <!-- 单条分析结果 -->
    <el-dialog v-model="analysisDialogVisible" title="新闻影响分析" width="640px">
      <template v-if="analysisResult">
        <el-alert
          v-if="analysisResult.degraded"
          type="warning"
          :closable="false"
          show-icon
          style="margin-bottom: 12px;"
        >
          <template #title>规则降级分析：{{ analysisResult.failure_reason || 'AI分析失败' }}</template>
        </el-alert>
        <el-descriptions :column="2" border>
          <el-descriptions-item label="事件摘要" :span="2">
            {{ analysisResult.result?.event_summary || '—' }}
          </el-descriptions-item>
          <el-descriptions-item label="影响方向">
            {{ analysisResult.result?.impact_direction || 'neutral' }}
          </el-descriptions-item>
          <el-descriptions-item label="证据强度">
            {{ analysisResult.result?.evidence_strength || 'weak' }}
          </el-descriptions-item>
          <el-descriptions-item label="影响路径" :span="2">
            {{ (analysisResult.result?.impact_paths || []).join('；') || '—' }}
          </el-descriptions-item>
          <el-descriptions-item label="观察指标" :span="2">
            {{ (analysisResult.result?.watch_indicators || []).join('；') || '—' }}
          </el-descriptions-item>
        </el-descriptions>
      </template>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { computed, ref, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'
import { Refresh } from '@element-plus/icons-vue'
import { newsWatchApi } from '@/api/newsWatch'

const router = useRouter()
const loading = ref(false)
const newsLoading = ref(false)
const items = ref<any[]>([])
const relatedNews = ref<any[]>([])
const filterType = ref('')
const coverageInfo = ref<any>(null)
const eventClusters = ref<any[]>([])
const analysisDialogVisible = ref(false)
const analysisResult = ref<any>(null)
const analysisLoading = ref(false)

const refreshCollected = async () => {
  loading.value = true
  try {
    const params: Record<string, any> = { limit: 100 }
    if (filterType.value) params.item_type = filterType.value
    const res = await newsWatchApi.listCollected(params)
    items.value = res.data?.items || []
    await loadRelatedNews()
  } catch {
    ElMessage.error('加载关注记录失败')
  } finally {
    loading.value = false
  }
}

const relatedNewsLabel = computed(() => {
  const symbols = getCollectedSymbols()
  if (symbols.length > 0) return `基于 ${symbols.slice(0, 3).join('、')} 的近期新闻`
  return '暂无关注对象，展示近期市场新闻'
})

const getCollectedSymbols = () => {
  return Array.from(new Set(
    items.value
      .filter((item) => item.item_type === 'stock' && item.symbol)
      .map((item) => item.symbol)
  ))
}

const loadRelatedNews = async () => {
  newsLoading.value = true
  try {
    const symbols = getCollectedSymbols()
    if (symbols.length === 0) {
      const res = await newsWatchApi.getLatestNews({ limit: 10, hours_back: 168 })
      const marketNews = res.data?.news || []
      if (marketNews.length > 0) {
        relatedNews.value = marketNews
        await loadCoverageAndClusters()
        return
      }

      const fallback = await newsWatchApi.getStockNews('000001', {
        days: 30,
        limit: 10,
        include_announcements: true,
      })
      relatedNews.value = (fallback.data?.items || []).map((item) => ({
        id: item.url || item.title,
        symbol: fallback.data?.symbol || fallback.data?.code || '000001',
        title: item.title,
        source: item.source,
        publish_time: item.time,
        url: item.url,
        data_source: fallback.data?.source,
      }))
      await loadCoverageAndClusters()
      return
    }

    const batches = await Promise.all(
      symbols.slice(0, 5).map((symbol) =>
        newsWatchApi.queryStockNews(symbol, { limit: 5, hours_back: 168 })
          .then((res) => res.data?.news || [])
          .catch(() => [])
      )
    )
    relatedNews.value = batches
      .flat()
      .sort((a, b) => new Date(b.publish_time || 0).getTime() - new Date(a.publish_time || 0).getTime())
      .slice(0, 20)
    await loadCoverageAndClusters(symbols[0])
  } finally {
    newsLoading.value = false
  }
}

const loadCoverageAndClusters = async (symbol?: string) => {
  try {
    const coverage = await newsWatchApi.sourceCoverage()
    coverageInfo.value = coverage.data || null
  } catch {
    coverageInfo.value = null
  }

  if (!symbol) {
    eventClusters.value = []
    return
  }
  try {
    const aggregated = await newsWatchApi.aggregatedNews(symbol)
    eventClusters.value = aggregated.data?.event_clusters || []
  } catch {
    eventClusters.value = []
  }
}

const collectNews = async (news: any) => {
  try {
    await newsWatchApi.collect({
      item_type: 'news',
      symbol: news.symbol,
      news_id: news.id || news._id || news.url || news.title,
      source_page: 'news_watch_workbench',
      title: news.title || '',
    })
    ElMessage.success('新闻已收集')
    refreshCollected()
  } catch (e: any) {
    ElMessage.error(e?.response?.data?.detail || '收集新闻失败')
  }
}

const analyzeOne = async (news: any) => {
  analysisLoading.value = true
  try {
    const res = await newsWatchApi.analyzeNews({
      news_id: news.id || news._id || news.url || news.title,
      title: news.title || '',
      content: news.content || news.summary || '',
      source: news.source || news.data_source || '',
      published_at: news.publish_time || news.published_at || '',
      symbol: news.symbol || '',
    })
    analysisResult.value = res.data || {}
    analysisDialogVisible.value = true
  } catch (e: any) {
    ElMessage.error(e?.response?.data?.detail || '分析失败')
  } finally {
    analysisLoading.value = false
  }
}

const analyzeBatchNews = async () => {
  const newsItems = relatedNews.value.slice(0, 10).map((news) => ({
    news_id: news.id || news._id || news.url || news.title,
    title: news.title || '',
    content: news.content || news.summary || '',
    source: news.source || news.data_source || '',
    published_at: news.publish_time || news.published_at || '',
    symbol: news.symbol || '',
  }))
  if (newsItems.length === 0) return
  try {
    const res = await newsWatchApi.analyzeBatch({
      news_items: newsItems,
      cluster_first: true,
    })
    ElMessage.success(`已聚合 ${res.data?.count ?? newsItems.length} 个事件并完成分析`)
  } catch (e: any) {
    ElMessage.error(e?.response?.data?.detail || '批量分析失败')
  }
}

const observeNews = async (news: any) => {
  try {
    await newsWatchApi.createObservationFromNews({
      stock_code: news.symbol || news.stock_code || '',
      stock_name: news.stock_name || '',
      news_event_id: news.id || news._id || news.url || news.title,
      user_notes: `来自新闻: ${news.title || ''}`,
    })
    ElMessage.success('已转观察任务')
  } catch (e: any) {
    ElMessage.error(e?.response?.data?.detail || '转观察失败')
  }
}

const ignoreNews = async (news: any) => {
  try {
    await newsWatchApi.ignoreNews({
      symbol: news.symbol,
      news_id: news.id || news._id || news.url || news.title,
      title: news.title || '',
    })
    relatedNews.value = relatedNews.value.filter(
      (item) => (item.id || item._id || item.url || item.title) !== (news.id || news._id || news.url || news.title)
    )
    ElMessage.success('已忽略')
  } catch (e: any) {
    ElMessage.error(e?.response?.data?.detail || '忽略失败')
  }
}

const removeItem = async (row: any) => {
  try {
    await ElMessageBox.confirm('确定要移除这条关注记录吗？', '确认', {
      type: 'warning',
    })
    await newsWatchApi.removeCollected(row._id)
    ElMessage.success('已移除')
    refreshCollected()
  } catch {
    // cancelled or error
  }
}

const goToDetail = (row: any) => {
  if (row.symbol) {
    router.push({ name: 'StockDetail', params: { code: row.symbol } })
  }
}

const formatSource = (page: string) => {
  const map: Record<string, string> = {
    stock_detail: '股票详情',
    favorites: '自选股',
    news_list: '新闻列表',
    screening_results: '选股结果',
  }
  return map[page] || page || '未知'
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
  refreshCollected()
})
</script>

<style scoped>
.news-watch-workbench {
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

.item-title {
  margin-left: 8px;
  color: #606266;
  font-size: 13px;
}

.source-label {
  font-size: 13px;
  color: #909399;
}

.empty-guide {
  text-align: left;
}

.related-news-card {
  margin-top: 16px;
}

.coverage-card {
  margin-top: 16px;
}

.card-header-left {
  display: flex;
  align-items: center;
  gap: 12px;
}

.news-list {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.news-item {
  display: flex;
  justify-content: space-between;
  gap: 12px;
  padding-bottom: 12px;
  border-bottom: 1px solid #ebeef5;
}

.news-item:last-child {
  border-bottom: 0;
  padding-bottom: 0;
}

.news-main {
  min-width: 0;
}

.news-actions {
  display: flex;
  align-items: center;
  flex-shrink: 0;
  gap: 4px;
}

.cluster-list {
  display: flex;
  flex-direction: column;
  gap: 8px;
  margin-top: 12px;
}

.cluster-item {
  display: flex;
  flex-wrap: wrap;
  gap: 12px;
  font-size: 13px;
  color: #606266;
}

.news-title {
  color: #303133;
  font-size: 14px;
  line-height: 1.5;
  text-decoration: none;
}

.news-title:hover {
  color: #409eff;
}

.news-meta {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  margin-top: 4px;
  color: #909399;
  font-size: 12px;
}

.guide-list {
  padding-left: 20px;
  line-height: 2;
  color: #606266;
}

.guide-note {
  margin-top: 12px;
  font-size: 12px;
  color: #909399;
}
</style>
