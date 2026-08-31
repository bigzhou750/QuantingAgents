<template>
  <div class="impact-analysis">
    <el-card shadow="never" class="header-card">
      <div class="page-header">
        <div>
          <h2 style="margin: 0 0 4px 0;">持仓新闻影响分析</h2>
          <span class="subtitle">基于当前持仓和近期新闻，展示影响方向和证据强度</span>
        </div>
        <el-button type="primary" @click="runAnalysis" :loading="loading">
          <el-icon><DataAnalysis /></el-icon>
          开始分析
        </el-button>
      </div>
    </el-card>

    <!-- 无持仓提示 -->
    <el-card v-if="analyzed && !result.has_holdings" class="no-holdings">
      <el-empty description="暂无持仓数据">
        <template #description>
          <p>{{ result.boundary_note }}</p>
          <el-button type="primary" plain @click="$router.push('/investment/profile')">
            去设置持仓
          </el-button>
        </template>
      </el-empty>
    </el-card>

    <!-- 分析结果 -->
    <template v-else-if="analyzed && result.has_holdings">
      <!-- 概览卡片 -->
      <el-row :gutter="16" style="margin-bottom: 16px;">
        <el-col :span="8">
          <el-card shadow="never" class="stat-card">
            <div class="stat-value">{{ result.holdings_count }}</div>
            <div class="stat-label">持仓数量</div>
          </el-card>
        </el-col>
        <el-col :span="8">
          <el-card shadow="never" class="stat-card">
            <div class="stat-value" :class="result.data_sufficient ? 'text-success' : 'text-warning'">
              {{ result.data_sufficient ? '充分' : '不足' }}
            </div>
            <div class="stat-label">数据覆盖</div>
          </el-card>
        </el-col>
        <el-col :span="8">
          <el-card shadow="never" class="stat-card">
            <div class="stat-value">{{ highImpactCount }}</div>
            <div class="stat-label">高影响持仓</div>
          </el-card>
        </el-col>
      </el-row>

      <!-- 影响详情表格 -->
      <el-card>
        <template #header>
          <span>受影响持仓详情</span>
        </template>
        <el-table :data="result.impacts" border stripe>
          <el-table-column prop="stock_code" label="代码" width="100" />
          <el-table-column prop="stock_name" label="名称" width="140" />
          <el-table-column label="影响等级" width="120">
            <template #default="{ row }">
              <el-tag :type="getImpactTagType(row.impact_level)" effect="dark">
                {{ translateImpactLevel(row.impact_level) }}
              </el-tag>
            </template>
          </el-table-column>
          <el-table-column label="新闻数量" width="100">
            <template #default="{ row }">
              {{ row.news_count }} 条
            </template>
          </el-table-column>
          <el-table-column label="证据说明" min-width="250">
            <template #default="{ row }">
              <span class="evidence-note">{{ row.evidence_note }}</span>
            </template>
          </el-table-column>
          <el-table-column label="最新新闻" width="160">
            <template #default="{ row }">
              {{ formatTime(row.latest_news_time) }}
            </template>
          </el-table-column>
          <el-table-column label="样本标题" min-width="200">
            <template #default="{ row }">
              <div v-for="(headline, idx) in row.sample_headlines" :key="idx" class="headline-item">
                {{ headline }}
              </div>
              <span v-if="!row.sample_headlines?.length" class="muted">暂无</span>
            </template>
          </el-table-column>
        </el-table>
      </el-card>

      <!-- 结论边界说明 -->
      <el-card style="margin-top: 16px;">
        <template #header>
          <span>结论边界说明</span>
        </template>
        <el-alert type="info" :closable="false" show-icon>
          <template #title>{{ result.boundary_note }}</template>
        </el-alert>
        <ul class="boundary-list">
          <li>影响等级基于新闻数量、重要性和情绪分布的规则匹配，不是预测模型。</li>
          <li>新闻覆盖不足的持仓，分析结论仅供参考，建议结合更长周期的观察。</li>
          <li>本分析不构成任何买入或卖出建议，仅作为研究参考。</li>
        </ul>
      </el-card>
    </template>

    <!-- 初始状态 -->
    <el-card v-else-if="!analyzed && !loading">
      <el-empty description='点击"开始分析"查看持仓新闻影响'>
        <template #description>
          <p class="muted">分析将基于你的投资画像中的当前持仓和最近 72 小时的新闻数据。</p>
        </template>
      </el-empty>
    </el-card>
  </div>
</template>

<script setup lang="ts">
import { ref, computed } from 'vue'
import { ElMessage } from 'element-plus'
import { DataAnalysis } from '@element-plus/icons-vue'
import { newsWatchApi } from '@/api/newsWatch'

const loading = ref(false)
const analyzed = ref(false)
const result = ref<any>({})

const highImpactCount = computed(() =>
  (result.value.impacts || []).filter((i: any) => i.impact_level === 'high').length
)

const runAnalysis = async () => {
  loading.value = true
  try {
    const res = await newsWatchApi.analyzeImpact({ hours_back: 72 })
    result.value = res.data || {}
    analyzed.value = true
  } catch {
    ElMessage.error('分析失败，请稍后重试')
  } finally {
    loading.value = false
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
  if (!iso) return '—'
  try {
    return new Date(iso).toLocaleString('zh-CN')
  } catch {
    return iso
  }
}
</script>

<style scoped>
.impact-analysis {
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

.stat-card {
  text-align: center;
}

.stat-value {
  font-size: 28px;
  font-weight: bold;
  color: #303133;
}

.stat-value.text-success { color: #67C23A; }
.stat-value.text-warning { color: #E6A23C; }

.stat-label {
  font-size: 13px;
  color: #909399;
  margin-top: 4px;
}

.evidence-note {
  font-size: 13px;
  color: #606266;
}

.headline-item {
  font-size: 12px;
  color: #606266;
  line-height: 1.6;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.boundary-list {
  margin: 12px 0 0 0;
  padding-left: 20px;
  font-size: 13px;
  color: #606266;
  line-height: 1.8;
}

.muted {
  color: #909399;
  font-size: 13px;
}
</style>
