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
        label-width="140px"
        style="max-width: 640px"
      >
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
            每个用例重复运行的次数
          </span>
        </el-form-item>

        <el-form-item label="单 Trial 超时(秒)" prop="timeout_seconds">
          <el-input-number v-model="form.timeout_seconds" :min="30" :max="3600" :step="30" />
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
const selectedDatasetInfo = ref<{ caseCount: number; version: string } | null>(null)

const form = ref({
  dataset_id: '',
  dataset_version: '',
  num_trials: 1,
  timeout_seconds: 600,
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
      // 获取 case 数量
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
      const res = await axios.post('/api/eval/runs', {
        dataset_id: form.value.dataset_id,
        dataset_version: form.value.dataset_version,
        num_trials: form.value.num_trials,
        config: {
          timeout_seconds: form.value.timeout_seconds,
        },
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
  await loadDatasets()

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
