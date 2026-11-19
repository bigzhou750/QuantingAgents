<template>
  <div class="run-compare-page">
    <div class="page-header">
      <h1 class="page-title">
        <el-icon><DataAnalysis /></el-icon>
        运行对比
      </h1>
      <el-button @click="$router.push('/evaluation/runs')">返回列表</el-button>
    </div>

    <!-- Run 选择器 -->
    <el-card shadow="never" style="margin-bottom: 24px">
      <template #header><span>选择要对比的运行（2-4个）</span></template>
      <el-select
        v-model="selectedRunIds"
        multiple
        filterable
        placeholder="请选择评测运行"
        style="width: 100%"
        :max-collapse-tags="4"
        @change="onSelectionChange"
      >
        <el-option
          v-for="run in runs"
          :key="run.run_id"
          :label="`${run.run_id} (${run.dataset_version || '-'} · ${getStatusLabel(run.status)})`"
          :value="run.run_id"
          :disabled="selectedRunIds.length >= 4 && !selectedRunIds.includes(run.run_id)"
        />
      </el-select>
    </el-card>

    <!-- 对比表格 -->
    <el-card v-if="compareData" shadow="never" v-loading="comparing">
      <template #header><span>对比结果</span></template>
      <el-table :data="compareTableData" stripe border size="small">
        <el-table-column prop="metric" label="指标" width="160" fixed="left" />
        <el-table-column
          v-for="runId in selectedRunIds"
          :key="runId"
          :label="runId"
          min-width="160"
        >
          <template #default="{ row }">
            {{ row[runId] ?? '-' }}
          </template>
        </el-table-column>
      </el-table>
    </el-card>

    <el-empty v-else-if="!comparing && selectedRunIds.length < 2" description="请至少选择2个运行进行对比" />
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import { useRoute } from 'vue-router'
import { ElMessage } from 'element-plus'
import { DataAnalysis } from '@element-plus/icons-vue'
import { evalApiClient as axios } from '@/api/evalClient'

const route = useRoute()

const runs = ref<any[]>([])
const selectedRunIds = ref<string[]>([])
const comparing = ref(false)
const compareData = ref<any>(null)

const pct = (v: number | undefined) => v !== undefined ? `${(v * 100).toFixed(1)}%` : '-'

const compareTableData = computed(() => {
  if (!compareData.value?.runs) return []

  const runMap: Record<string, any> = {}
  for (const r of compareData.value.runs) {
    runMap[r.run_id] = r
  }

  const metricsList = [
    { key: 'dataset_version', label: '数据集版本' },
    { key: 'status', label: '状态' },
    { key: 'success_rate', label: '成功率', format: pct },
    { key: 'failure_rate', label: '失败率', format: pct },
    { key: 'pass_at_k', label: 'pass@k', format: pct },
    { key: 'pass_pow_k', label: 'pass^k', format: pct },
    { key: 'avg_latency_ms', label: '平均延迟(ms)', raw: true },
    { key: 'total_cost_usd', label: '总成本(USD)', raw: true },
  ]

  const rows = metricsList.map(m => {
    const row: any = { metric: m.label }
    for (const id of selectedRunIds.value) {
      const r = runMap[id]
      if (!r) { row[id] = '-'; continue }
      const val = r[m.key]
      if (m.format) row[id] = m.format(val)
      else if (m.raw) row[id] = val !== undefined ? (typeof val === 'number' ? val.toFixed?.(4) ?? val : val) : '-'
      else row[id] = val ?? '-'
    }
    return row
  })

  // Add score dimensions
  const allScoreNames = new Set<string>()
  for (const r of compareData.value.runs) {
    if (r.score_summary) {
      Object.keys(r.score_summary).forEach(n => allScoreNames.add(n))
    }
  }
  for (const name of allScoreNames) {
    const row: any = { metric: `评分-${name}` }
    for (const id of selectedRunIds.value) {
      const r = runMap[id]
      row[id] = r?.score_summary?.[name] !== undefined ? pct(r.score_summary[name]) : '-'
    }
    rows.push(row)
  }

  return rows
})

const loadRuns = async () => {
  try {
    const res = await axios.get('/api/eval/runs', { params: { limit: 50 } })
    runs.value = res.data?.data?.items || []
  } catch {
    ElMessage.error('加载运行列表失败')
  }
}

const onSelectionChange = async () => {
  if (selectedRunIds.value.length < 2) {
    compareData.value = null
    return
  }

  comparing.value = true
  try {
    const res = await axios.post('/api/eval/metrics/compare', { run_ids: selectedRunIds.value })
    compareData.value = res.data?.data || null
  } catch {
    ElMessage.error('对比数据加载失败')
  } finally {
    comparing.value = false
  }
}

const getStatusLabel = (status: string) => {
  const map: Record<string, string> = { pending: '等待中', running: '运行中', completed: '已完成', failed: '失败', cancelled: '已取消' }
  return map[status] || status
}

onMounted(async () => {
  await loadRuns()

  // Pre-select from URL query
  const idsParam = route.query.run_ids as string
  if (idsParam) {
    const ids = idsParam.split(',').filter(Boolean)
    selectedRunIds.value = ids
    if (ids.length >= 2) await onSelectionChange()
  }
})
</script>

<style scoped>
.run-compare-page { padding: 24px; }
.page-header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 24px; }
.page-title { font-size: 24px; font-weight: 600; display: flex; align-items: center; gap: 12px; margin: 0; }
</style>
