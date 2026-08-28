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
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'
import { Refresh } from '@element-plus/icons-vue'
import axios from 'axios'

const router = useRouter()
const loading = ref(false)
const items = ref<any[]>([])
const filterType = ref('')

const refreshCollected = async () => {
  loading.value = true
  try {
    const params: Record<string, any> = { limit: 100 }
    if (filterType.value) params.item_type = filterType.value
    const res = await axios.get('/api/news-watch/collected', { params })
    items.value = res.data?.data?.items || []
  } catch {
    ElMessage.error('加载关注记录失败')
  } finally {
    loading.value = false
  }
}

const removeItem = async (row: any) => {
  try {
    await ElMessageBox.confirm('确定要移除这条关注记录吗？', '确认', {
      type: 'warning',
    })
    await axios.delete(`/api/news-watch/collected/${row._id}`)
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
