<template>
  <div class="run-create-page">
    <div class="page-header">
      <h1 class="page-title">
        <el-icon><VideoPlay /></el-icon>
        新建评测运行
      </h1>
      <el-button @click="$router.back()">返回</el-button>
    </div>

    <el-card shadow="never">
      <el-form
        ref="formRef"
        :model="form"
        :rules="rules"
        label-width="160px"
        style="max-width: 720px"
      >
        <!-- 基础配置 -->
        <el-divider content-position="left">基础配置</el-divider>

        <el-form-item label="选择数据集" prop="dataset_id">
          <el-select
            v-model="form.dataset_id"
            placeholder="请选择评测集"
            filterable
            style="width: 100%"
            @change="onDatasetChange"
          >
            <el-option
              v-for="ds in datasets"
              :key="ds.dataset_id"
              :label="`${ds.name} (v${ds.version})`"
              :value="ds.dataset_id"
            />
          </el-select>
        </el-form-item>

        <el-form-item label="数据集版本" prop="dataset_version">
          <el-input v-model="displayVersion" disabled placeholder="选择数据集后自动填充" />
        </el-form-item>

        <el-form-item label="Case 数量">
          <el-tag v-if="selectedDatasetInfo">{{ selectedDatasetInfo.caseCount }} 条用例</el-tag>
          <span v-else style="color: var(--el-text-color-placeholder)">请先选择数据集</span>
        </el-form-item>

        <el-form-item label="每 Case Trial 数" prop="num_trials">
          <el-input-number v-model="form.num_trials" :min="1" :max="10" />
          <span style="margin-left: 8px; color: var(--el-text-color-secondary); font-size: 12px">
            每个用例重复运行的次数，≥3 时可计算 pass@k / pass^k
          </span>
        </el-form-item>

        <el-form-item label="单 Trial 超时(秒)" prop="timeout_seconds">
          <el-input-number v-model="form.timeout_seconds" :min="30" :max="3600" :step="30" />
        </el-form-item>

        <!-- 评分器配置 (4.1) -->
        <el-divider content-position="left">评分器配置</el-divider>

        <el-form-item label="选择评分器">
          <el-checkbox-group v-model="form.scorer_names">
            <el-checkbox
              v-for="scorer in availableScorers"
              :key="scorer.name"
              :label="scorer.name"
              :disabled="scorer.status === 'not_configured'"
            >
              {{ scorer.name }}
              <el-tag v-if="scorer.status === 'not_configured'" size="small" type="info" style="margin-left: 4px">未安装</el-tag>
              <span style="font-size: 11px; color: var(--el-text-color-secondary); margin-left: 4px">({{ scorer.source }})</span>
            </el-checkbox>
          </el-checkbox-group>
          <div v-if="availableScorers.length === 0" style="color: var(--el-text-color-placeholder); font-size: 12px">
            加载评分器列表中...
          </div>
        </el-form-item>

        <!-- Judge 配置 (4.1) -->
        <el-divider content-position="left">Judge 配置</el-divider>

        <el-form-item label="Judge 模型">
          <el-input v-model="form.judge_model" placeholder="留空使用默认模型" />
          <div style="font-size: 12px; color: var(--el-text-color-secondary)">
            LLM-as-Judge 使用的模型名称
          </div>
        </el-form-item>

        <el-form-item label="Rubric 版本">
          <el-input v-model="form.rubric_version" placeholder="例如: 1.0.0" />
        </el-form-item>

        <el-form-item label="低置信度阈值">
          <el-slider v-model="form.low_confidence_threshold" :min="0" :max="1" :step="0.05" show-input />
          <div style="font-size: 12px; color: var(--el-text-color-secondary)">
            低于此阈值的评分将进入人工复核队列
          </div>
        </el-form-item>

        <el-form-item label="复核策略">
          <el-radio-group v-model="form.review_strategy">
            <el-radio value="auto">自动（仅低分和低置信度）</el-radio>
            <el-radio value="manual">全部人工复核</el-radio>
            <el-radio value="all">全量复核</el-radio>
          </el-radio-group>
        </el-form-item>

        <!-- 数据窗口 -->
        <el-divider content-position="left">数据窗口（可选）</el-divider>

        <el-form-item label="数据时间范围">
          <el-date-picker
            v-model="formDataWindow"
            type="datetimerange"
            range-separator="至"
            start-placeholder="开始时间"
            end-placeholder="结束时间"
            style="width: 100%"
          />
          <div style="font-size: 12px; color: var(--el-text-color-secondary)">
            用于固定行情、新闻等时变数据的查询窗口，确保可复现
          </div>
        </el-form-item>

        <el-form-item>
          <el-button type="primary" :loading="submitting" @click="submitForm">
            创建评测运行
          </el-button>
          <el-button @click="$router.back()">取消</el-button>
        </el-form-item>
      </el-form>
    </el-card>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted, computed } from 'vue'
import { useRouter, useRoute } from 'vue-router'
import { ElMessage } from 'element-plus'
import { VideoPlay } from '@element-plus/icons-vue'
import { evalApiClient as axios } from '@/api/evalClient'
import type { FormInstance, FormRules } from 'element-plus'

const router = useRouter()
const route = useRoute()

const formRef = ref<FormInstance>()
const submitting = ref(false)
const datasets = ref<any[]>([])
const availableScorers = ref<any[]>([])
const selectedDatasetInfo = ref<{ caseCount: number; version: string } | null>(null)
const formDataWindow = ref<[Date, Date] | null>(null)

const form = ref({
  dataset_id: '',
  dataset_version: '',
  num_trials: 1,
  timeout_seconds: 600,
  scorer_names: [] as string[],
  judge_model: '',
  rubric_version: '',
  low_confidence_threshold: 0.7,
  review_strategy: 'auto',
})

const rules: FormRules = {
  dataset_id: [{ required: true, message: '请选择评测集', trigger: 'change' }],
  num_trials: [{ required: true, message: '请输入 Trial 数', trigger: 'blur' }],
  timeout_seconds: [{ required: true, message: '请输入超时时间', trigger: 'blur' }],
}

const displayVersion = computed(() => {
  return form.value.dataset_version || ''
})

const loadDatasets = async () => {
  try {
    const res = await axios.get('/api/eval/datasets', { params: { limit: 100 } })
    datasets.value = res.data?.data?.items || []
  } catch (error) {
    ElMessage.error('加载数据集列表失败')
  }
}

const loadScorers = async () => {
  try {
    const res = await axios.get('/api/eval/scorers')
    availableScorers.value = res.data?.data?.items || []
    // 默认选中所有可用的评分器
    form.value.scorer_names = availableScorers.value
      .filter((s: any) => s.status !== 'not_configured')
      .map((s: any) => s.name)
  } catch (error) {
    console.warn('Failed to load scorers:', error)
  }
}

const onDatasetChange = async (datasetId: string) => {
  if (!datasetId) {
    selectedDatasetInfo.value = null
    form.value.dataset_version = ''
    return
  }
  try {
    const res = await axios.get(`/api/eval/datasets/${datasetId}`, {
      params: { include_cases: false },
    })
    const ds = res.data?.data
    if (ds) {
      form.value.dataset_version = ds.version || '1.0.0'
      const casesRes = await axios.get(`/api/eval/datasets/${datasetId}/cases`, {
        params: { limit: 1 },
      })
      const caseCount = casesRes.data?.data?.count || 0
      selectedDatasetInfo.value = { caseCount, version: ds.version }
    }
  } catch (error) {
    ElMessage.error('获取数据集详情失败')
  }
}

const submitForm = async () => {
  if (!formRef.value) return
  await formRef.value.validate(async (valid) => {
    if (!valid) return

    if (selectedDatasetInfo.value && selectedDatasetInfo.value.caseCount === 0) {
      ElMessage.warning('该数据集没有用例，请先添加用例')
      return
    }

    submitting.value = true
    try {
      // Build data_window from date range
      let dataWindow: any = undefined
      if (formDataWindow.value && formDataWindow.value.length === 2) {
        dataWindow = {
          start: formDataWindow.value[0].toISOString(),
          end: formDataWindow.value[1].toISOString(),
        }
      }

      const res = await axios.post('/api/eval/runs', {
        dataset_id: form.value.dataset_id,
        dataset_version: form.value.dataset_version,
        num_trials: form.value.num_trials,
        config: {
          timeout_seconds: form.value.timeout_seconds,
        },
        scorer_names: form.value.scorer_names.length > 0 ? form.value.scorer_names : undefined,
        judge_model: form.value.judge_model || undefined,
        rubric_version: form.value.rubric_version || undefined,
        low_confidence_threshold: form.value.low_confidence_threshold,
        review_strategy: form.value.review_strategy,
        data_window: dataWindow,
      })

      const runId = res.data?.data?.run_id
      ElMessage.success('评测运行创建成功')

      // 自动启动运行
      try {
        await axios.post(`/api/eval/runs/${runId}/start`)
        ElMessage.success('评测运行已启动')
      } catch (startErr) {
        ElMessage.warning('运行创建成功但启动失败，请手动启动')
      }

      router.push(`/evaluation/runs/${runId}`)
    } catch (error: any) {
      ElMessage.error(error.response?.data?.detail || '创建失败')
    } finally {
      submitting.value = false
    }
  })
}

onMounted(async () => {
  await Promise.all([loadDatasets(), loadScorers()])

  // 如果 URL 带了 dataset_id 参数，自动选中
  const presetDatasetId = route.query.dataset_id as string
  if (presetDatasetId) {
    form.value.dataset_id = presetDatasetId
    await onDatasetChange(presetDatasetId)
  }
})
</script>

<style scoped>
.run-create-page {
  padding: 24px;
}

.page-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 24px;
}

.page-title {
  font-size: 24px;
  font-weight: 600;
  display: flex;
  align-items: center;
  gap: 12px;
  margin: 0;
}
</style>
