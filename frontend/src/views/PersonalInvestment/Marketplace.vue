<template>
  <div class="strategy-marketplace" v-loading="loading">
    <el-page-header title="策略广场" @back="$router.push('/investment/home')" />
    <p class="page-desc">浏览经过审核的策略模板，选择适合你的投资风格，一键加入我的策略。</p>

    <!-- 筛选 -->
    <el-card style="margin-bottom: 16px;">
      <el-form :inline="true">
        <el-form-item label="标签">
          <el-select v-model="filterTag" placeholder="全部" clearable @change="loadTemplates">
            <el-option label="价值投资" value="value" />
            <el-option label="成长投资" value="growth" />
            <el-option label="红利投资" value="dividend" />
            <el-option label="趋势跟踪" value="momentum" />
            <el-option label="均衡" value="balanced" />
            <el-option label="稳健型" value="conservative" />
          </el-select>
        </el-form-item>
        <el-form-item>
          <el-button type="primary" @click="loadTemplates">刷新</el-button>
        </el-form-item>
      </el-form>
    </el-card>

    <!-- 策略卡片网格 -->
    <el-row :gutter="16">
      <el-col :span="8" v-for="tpl in templates" :key="tpl.template_id" style="margin-bottom: 16px;">
        <el-card shadow="hover" class="strategy-card" @click="openDetail(tpl)">
          <div class="card-tags">
            <el-tag v-for="tag in tpl.tags" :key="tag" size="small" type="info">{{ tagLabel(tag) }}</el-tag>
          </div>
          <h3 class="card-title">{{ tpl.name }}</h3>
          <p class="card-oneliner">{{ tpl.one_liner }}</p>
          <div class="card-meta">
            <span v-if="tpl.audience" class="meta-item">👤 {{ tpl.audience?.substring(0, 30) }}{{ (tpl.audience?.length || 0) > 30 ? '...' : '' }}</span>
            <span v-if="tpl.risk_boundary" class="meta-item risk">⚠️ {{ tpl.risk_boundary?.substring(0, 25) }}{{ (tpl.risk_boundary?.length || 0) > 25 ? '...' : '' }}</span>
          </div>
          <div class="card-footer">
            <el-tag size="small" type="success">已上架</el-tag>
            <span class="version">v{{ tpl.version }}</span>
          </div>
        </el-card>
      </el-col>
    </el-row>

    <el-empty v-if="!templates.length && !loading" description="暂无可用策略模板" />

    <!-- 策略详情弹窗 -->
    <el-dialog v-model="detailVisible" :title="selectedTemplate?.name" width="700px" top="5vh">
      <template v-if="selectedTemplate">
        <el-descriptions :column="1" border>
          <el-descriptions-item label="一句话说明">{{ selectedTemplate.one_liner }}</el-descriptions-item>
          <el-descriptions-item label="详细描述">{{ selectedTemplate.description }}</el-descriptions-item>
          <el-descriptions-item label="适合人群">
            <span style="color: #67c23a;">✅ {{ selectedTemplate.audience || '-' }}</span>
          </el-descriptions-item>
          <el-descriptions-item label="不适合人群">
            <span style="color: #f56c6c;">❌ {{ selectedTemplate.not_for || '-' }}</span>
          </el-descriptions-item>
          <el-descriptions-item label="风险边界">
            <el-alert type="warning" :closable="false" :title="selectedTemplate.risk_boundary || '暂无'" />
          </el-descriptions-item>
          <el-descriptions-item label="数据要求">{{ selectedTemplate.data_requirements || '-' }}</el-descriptions-item>
          <el-descriptions-item label="适用市场">{{ selectedTemplate.applicable_markets?.join('、') }}</el-descriptions-item>
          <el-descriptions-item label="版本">{{ selectedTemplate.version }}</el-descriptions-item>
        </el-descriptions>

        <!-- 规则拆解 -->
        <div v-if="Object.keys(selectedTemplate.rule_explanation || {}).length" style="margin-top: 16px;">
          <h4>📖 规则拆解与指标解释</h4>
          <el-table :data="ruleEntries" stripe size="small">
            <el-table-column prop="key" label="指标" width="150" />
            <el-table-column prop="value" label="解释" />
          </el-table>
        </div>

        <!-- 筛选条件预览 -->
        <div v-if="Object.keys(selectedTemplate.screening_criteria || {}).length" style="margin-top: 16px;">
          <h4>🔍 筛选条件</h4>
          <el-tag v-for="(val, key) in selectedTemplate.screening_criteria" :key="key" size="small" style="margin: 2px 4px;">
            {{ criteriaLabel(String(key)) }}: {{ val }}
          </el-tag>
        </div>

        <!-- 操作按钮 -->
        <div style="margin-top: 20px; text-align: right;">
          <el-button @click="detailVisible = false">关闭</el-button>
          <el-button type="primary" :loading="adopting" @click="handleAdopt">➕ 加入我的策略</el-button>
        </div>
      </template>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import { ApiClient } from '@/api/request'

const router = useRouter()
const loading = ref(false)
const adopting = ref(false)
const templates = ref<any[]>([])
const filterTag = ref('')
const detailVisible = ref(false)
const selectedTemplate = ref<any>(null)

const ruleEntries = computed(() => {
  if (!selectedTemplate.value?.rule_explanation) return []
  return Object.entries(selectedTemplate.value.rule_explanation).map(([key, value]) => ({ key, value }))
})

const loadTemplates = async () => {
  loading.value = true
  try {
    const params: Record<string, any> = {}
    if (filterTag.value) params.tag = filterTag.value
    const res = await ApiClient.get('/api/investment/marketplace', params)
    templates.value = res?.data?.items || []
  } catch (e) {
    console.error('Failed to load marketplace templates', e)
  } finally {
    loading.value = false
  }
}

const openDetail = (tpl: any) => {
  selectedTemplate.value = tpl
  detailVisible.value = true
}

const handleAdopt = async () => {
  if (!selectedTemplate.value) return
  adopting.value = true
  try {
    const res = await ApiClient.post(`/api/investment/marketplace/${selectedTemplate.value.template_id}/adopt`)
    ElMessage.success(res?.message || '策略已加入你的策略列表')
    detailVisible.value = false
    router.push('/investment/strategies')
  } catch (e: any) {
    ElMessage.error(e?.response?.data?.detail || e?.detail || '加入失败')
  } finally {
    adopting.value = false
  }
}

const tagLabel = (t: string) => ({
  value: '价值', growth: '成长', dividend: '红利',
  momentum: '趋势', balanced: '均衡', conservative: '稳健',
}[t] || t)

const criteriaLabel = (k: string) => ({
  pe_max: '市盈率上限', roe_min: 'ROE下限', dividend_yield_min: '股息率下限',
  rsi_min: 'RSI下限', rsi_max: 'RSI上限', ma_trend: '均线趋势',
  market_cap_min: '市值下限',
}[k] || k)

onMounted(loadTemplates)
</script>

<style scoped>
.page-desc { color: #909399; margin: 8px 0 16px; }
.strategy-card { cursor: pointer; transition: all 0.2s; height: 100%; }
.strategy-card:hover { transform: translateY(-3px); box-shadow: 0 4px 12px rgba(0,0,0,0.1); }
.card-tags { margin-bottom: 8px; }
.card-tags .el-tag { margin-right: 4px; }
.card-title { margin: 0 0 8px; font-size: 16px; }
.card-oneliner { color: #606266; font-size: 13px; margin: 0 0 12px; line-height: 1.5; min-height: 40px; }
.card-meta { font-size: 12px; color: #909399; margin-bottom: 8px; }
.meta-item { display: block; margin-bottom: 2px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.meta-item.risk { color: #e6a23c; }
.card-footer { display: flex; justify-content: space-between; align-items: center; }
.version { font-size: 12px; color: #c0c4cc; }
</style>
