<template>
  <div class="event-analysis">
    <div style="margin-bottom: 12px;">
      <el-button link @click="$router.push('/news-watch/workbench')">← 回到工作台</el-button>
    </div>

    <el-card>
      <template #header>
        <div class="card-header">
          <span>🔍 事件分析</span>
        </div>
      </template>

      <!-- 单条分析入口 -->
      <el-form :inline="true" style="margin-bottom: 16px;">
        <el-form-item label="新闻标题">
          <el-input v-model="analyzeForm.title" placeholder="输入新闻标题" style="width: 300px;" />
        </el-form-item>
        <el-form-item label="内容摘要">
          <el-input v-model="analyzeForm.content" type="textarea" :rows="2" placeholder="新闻内容（可选）" style="width: 400px;" />
        </el-form-item>
        <el-form-item>
          <el-button type="primary" :loading="analyzing" @click="runAnalysis">AI 分析</el-button>
        </el-form-item>
      </el-form>

      <!-- 分析结果 -->
      <template v-if="analysisResult">
        <el-divider content-position="left">分析结果</el-divider>

        <el-descriptions :column="2" border>
          <el-descriptions-item label="事件摘要" :span="2">{{ analysisResult.result?.event_summary }}</el-descriptions-item>
          <el-descriptions-item label="事件类型">{{ analysisResult.result?.event_type }}</el-descriptions-item>
          <el-descriptions-item label="影响方向">
            <el-tag :type="directionType(analysisResult.result?.impact_direction)">
              {{ directionLabel(analysisResult.result?.impact_direction) }}
            </el-tag>
          </el-descriptions-item>
          <el-descriptions-item label="影响强度">
            <el-rate :model-value="analysisResult.result?.impact_strength || 0" disabled :max="5" />
          </el-descriptions-item>
          <el-descriptions-item label="时间维度">{{ horizonLabel(analysisResult.result?.time_horizon) }}</el-descriptions-item>
          <el-descriptions-item label="证据强度">
            <el-tag :type="evidenceType(analysisResult.result?.evidence_strength)" size="small">
              {{ evidenceLabel(analysisResult.result?.evidence_strength) }}
            </el-tag>
          </el-descriptions-item>
          <el-descriptions-item label="市场确认">{{ analysisResult.result?.market_confirmation || '—' }}</el-descriptions-item>
          <el-descriptions-item label="受影响行业" :span="2">
            <el-tag v-for="ind in (analysisResult.result?.affected_industries || [])" :key="ind" size="small" style="margin: 2px;">{{ ind }}</el-tag>
            <span v-if="!analysisResult.result?.affected_industries?.length" class="muted">—</span>
          </el-descriptions-item>
          <el-descriptions-item label="关注指标" :span="2">
            <el-tag v-for="w in (analysisResult.result?.watch_indicators || [])" :key="w" size="small" type="warning" style="margin: 2px;">{{ w }}</el-tag>
            <span v-if="!analysisResult.result?.watch_indicators?.length" class="muted">—</span>
          </el-descriptions-item>
          <el-descriptions-item label="不确定因素" :span="2">
            <span v-for="(u, i) in (analysisResult.result?.uncertainties || [])" :key="i">{{ u }}{{ i < (analysisResult.result?.uncertainties?.length || 0) - 1 ? '；' : '' }}</span>
            <span v-if="!analysisResult.result?.uncertainties?.length" class="muted">—</span>
          </el-descriptions-item>
        </el-descriptions>

        <el-alert
          v-if="analysisResult.degraded"
          type="warning"
          :closable="false"
          show-icon
          style="margin-top: 12px;"
        >
          <template #title>规则降级分析：{{ analysisResult.failure_reason || 'AI分析失败' }}</template>
        </el-alert>

        <el-alert
          type="info"
          :closable="false"
          show-icon
          style="margin-top: 8px;"
        >
          <template #title>{{ analysisResult.result?.non_advisory_note || '本分析仅为研究参考，不构成投资建议' }}</template>
        </el-alert>
      </template>

      <el-empty v-else-if="!analyzing" description="输入新闻内容后点击 AI 分析" />
    </el-card>
  </div>
</template>

<script setup lang="ts">
import { ref } from 'vue'
import { ElMessage } from 'element-plus'
import { newsWatchApi } from '@/api/newsWatch'

const analyzing = ref(false)
const analyzeForm = ref({ title: '', content: '' })
const analysisResult = ref<any>(null)

const runAnalysis = async () => {
  if (!analyzeForm.value.title) {
    ElMessage.warning('请输入新闻标题')
    return
  }
  analyzing.value = true
  try {
    const res = await newsWatchApi.analyzeNews({
      title: analyzeForm.value.title,
      content: analyzeForm.value.content,
    })
    analysisResult.value = res.data
  } catch (e: any) {
    ElMessage.error(e.response?.data?.detail || '分析失败')
  } finally {
    analyzing.value = false
  }
}

const directionLabel = (d: string) => ({ positive: '正面', negative: '负面', neutral: '中性' }[d] || d || '—')
const directionType = (d: string): '' | 'success' | 'danger' | 'info' => ({ positive: 'success', negative: 'danger', neutral: 'info' }[d] as any || '')
const horizonLabel = (h: string) => ({ short: '短期', medium: '中期', long: '长期' }[h] || h || '—')
const evidenceLabel = (e: string) => ({ strong: '强', moderate: '中等', weak: '弱' }[e] || e || '—')
const evidenceType = (e: string): '' | 'success' | 'warning' | 'danger' => ({ strong: 'success', moderate: 'warning', weak: 'danger' }[e] as any || '')
</script>

<style scoped>
.event-analysis { padding: 20px; }
.card-header { display: flex; justify-content: space-between; align-items: center; }
.muted { color: #909399; font-size: 12px; }
</style>
