<template>
  <div class="strategy-marketplace" v-loading="loading">
    <el-page-header title="策略广场" @back="$router.push('/investment/home')" />
    <p class="page-desc">浏览经过审核的策略模板，选择适合你的投资风格，查看详情后再加入我的策略。</p>

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
        <el-card shadow="hover" class="strategy-card" @click="goDetail(tpl)">
          <div class="card-tags">
            <el-tag v-for="tag in tpl.tags || []" :key="tag" size="small" type="info">{{ marketplaceTagLabel(tag) }}</el-tag>
          </div>
          <h3 class="card-title">{{ tpl.name }}</h3>
          <p class="card-oneliner">{{ tpl.one_liner || '-' }}</p>
          <div class="card-meta">
            <span v-if="tpl.audience" class="meta-item">适合：{{ tpl.audience }}</span>
            <span v-if="tpl.risk_boundary" class="meta-item risk">风险：{{ tpl.risk_boundary }}</span>
          </div>
          <div class="card-footer">
            <el-tag size="small" type="success">已上架</el-tag>
            <el-tag size="small" :type="dataStatusTag(tpl)">{{ marketplaceDataStatus(tpl) }}</el-tag>
            <span class="version">v{{ tpl.version }}</span>
          </div>
        </el-card>
      </el-col>
    </el-row>

    <el-empty v-if="!templates.length && !loading" description="暂无可用策略模板" />
  </div>
</template>

<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import { investmentApi } from '@/api/investment'
import { marketplaceDataStatus, marketplaceTagLabel } from '@/utils/marketplace'

const router = useRouter()
const loading = ref(false)
const templates = ref<any[]>([])
const filterTag = ref('')

const loadTemplates = async () => {
  loading.value = true
  try {
    const params: Record<string, unknown> = {}
    if (filterTag.value) params.tag = filterTag.value
    const res = await investmentApi.listMarketplaceTemplates(params)
    templates.value = res?.data?.items || []
  } catch (e) {
    console.error('Failed to load marketplace templates', e)
  } finally {
    loading.value = false
  }
}

const goDetail = (tpl: any) => {
  router.push({
    name: 'MarketplaceDetail',
    params: { templateId: tpl.template_id },
  })
}

const dataStatusTag = (tpl: any): 'success' | 'warning' | 'info' => {
  const status = marketplaceDataStatus(tpl)
  if (status === '数据已准备') return 'success'
  if (status === '数据不足') return 'warning'
  return 'info'
}

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
.meta-item { display: block; margin-bottom: 4px; line-height: 1.5; display: -webkit-box; -webkit-line-clamp: 2; -webkit-box-orient: vertical; overflow: hidden; }
.meta-item.risk { color: #e6a23c; }
.card-footer { display: flex; justify-content: space-between; align-items: center; gap: 8px; }
.version { font-size: 12px; color: #c0c4cc; white-space: nowrap; }
</style>
