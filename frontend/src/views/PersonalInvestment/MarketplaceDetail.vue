<template>
  <div class="marketplace-detail" v-loading="loading">
    <el-page-header title="策略广场" @back="$router.push('/investment/marketplace')" />

    <el-alert
      v-if="errorMessage"
      :title="errorMessage"
      type="error"
      :closable="false"
      show-icon
      style="margin-top: 16px;"
    />

    <template v-else-if="template">
      <el-card shadow="never" class="detail-title-card">
        <div class="detail-title-row">
          <div>
            <h2>{{ template.name }}</h2>
            <p class="detail-oneliner">{{ template.one_liner || '-' }}</p>
          </div>
          <el-tag type="success" size="large">已上架</el-tag>
        </div>
        <div class="detail-tags">
          <el-tag v-for="tag in template.tags || []" :key="tag" size="small" type="info">
            {{ marketplaceTagLabel(tag) }}
          </el-tag>
          <span class="detail-version">版本 v{{ template.version }}</span>
        </div>
      </el-card>

      <el-card class="detail-section">
        <template #header><span>这个策略在找什么</span></template>
        <p>{{ template.description || '-' }}</p>
        <el-descriptions :column="2" border size="small" style="margin-top: 12px;">
          <el-descriptions-item label="适合人群">{{ template.audience || '-' }}</el-descriptions-item>
          <el-descriptions-item label="不适合人群">{{ template.not_for || '-' }}</el-descriptions-item>
          <el-descriptions-item label="适用市场">{{ template.applicable_markets?.join('、') || '-' }}</el-descriptions-item>
          <el-descriptions-item label="数据要求">{{ template.data_requirements || '-' }}</el-descriptions-item>
        </el-descriptions>
      </el-card>

      <el-card class="detail-section" v-if="ruleEntries.length">
        <template #header><span>为什么这些条件有意义</span></template>
        <el-table :data="ruleEntries" border stripe size="small">
          <el-table-column label="指标" width="180">
            <template #default="{ row }">{{ marketplaceCriteriaLabel(String(row.key)) }}</template>
          </el-table-column>
          <el-table-column prop="value" label="中文解释" />
        </el-table>
      </el-card>

      <el-card class="detail-section">
        <template #header><span>什么情况下容易表现不好</span></template>
        <el-alert :title="template.risk_boundary || '暂无明确风险边界'" type="warning" :closable="false" show-icon />
      </el-card>

      <el-card class="detail-section">
        <template #header><span>数据与模拟状态</span></template>
        <div class="detail-data-row">
          <el-tag :type="dataStatus === '数据已准备' ? 'success' : dataStatus === '数据不足' ? 'warning' : 'info'">
            {{ dataStatus }}
          </el-tag>
          <span class="detail-metric">{{ metricText }}</span>
        </div>
      </el-card>

      <div class="detail-actions">
        <el-button size="large" @click="$router.push('/investment/marketplace')">返回广场</el-button>
        <el-button type="primary" size="large" :loading="adopting" @click="handleAdopt">
          加入我的策略
        </el-button>
      </div>
    </template>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import { investmentApi } from '@/api/investment'
import {
  marketplaceCriteriaLabel,
  marketplaceDataStatus,
  marketplaceMetricText,
  marketplaceTagLabel,
} from '@/utils/marketplace'

const route = useRoute()
const router = useRouter()
const loading = ref(false)
const adopting = ref(false)
const errorMessage = ref('')
const template = ref<any>(null)

const ruleEntries = computed(() => {
  if (!template.value?.rule_explanation) return []
  return Object.entries(template.value.rule_explanation).map(([key, value]) => ({ key, value }))
})

const dataStatus = computed(() => marketplaceDataStatus(template.value))
const metricText = computed(() => marketplaceMetricText(template.value))

const loadDetail = async () => {
  const templateId = String(route.params.templateId || '').trim()
  if (!templateId) {
    errorMessage.value = '缺少策略模板 ID'
    return
  }

  loading.value = true
  try {
    const res = await investmentApi.getMarketplaceTemplate(templateId)
    template.value = res.data || null
  } catch (e: any) {
    errorMessage.value = e?.response?.data?.detail || e?.message || '加载策略详情失败'
  } finally {
    loading.value = false
  }
}

const handleAdopt = async () => {
  if (!template.value?.template_id) return
  adopting.value = true
  try {
    const res = await investmentApi.adoptTemplate(template.value.template_id)
    ElMessage.success(res?.message || '策略已加入你的策略列表')
    router.push('/investment/strategies')
  } catch (e: any) {
    ElMessage.error(e?.response?.data?.detail || e?.detail || '加入失败')
  } finally {
    adopting.value = false
  }
}

onMounted(loadDetail)
</script>

<style scoped>
.marketplace-detail {
  padding: 20px;
}
.detail-title-card {
  margin-top: 12px;
}
.detail-title-row {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  gap: 16px;
}
.detail-title-row h2 {
  margin: 0 0 6px;
}
.detail-oneliner {
  color: #606266;
  margin: 0;
}
.detail-tags {
  margin-top: 12px;
  display: flex;
  align-items: center;
  gap: 8px;
}
.detail-version {
  color: #909399;
  font-size: 12px;
}
.detail-section {
  margin-top: 16px;
}
.detail-section p {
  margin: 0;
  line-height: 1.7;
}
.detail-data-row {
  display: flex;
  align-items: center;
  gap: 12px;
}
.detail-metric {
  color: #606266;
  font-size: 13px;
}
.detail-actions {
  margin-top: 20px;
  display: flex;
  justify-content: flex-end;
  gap: 12px;
}
</style>
