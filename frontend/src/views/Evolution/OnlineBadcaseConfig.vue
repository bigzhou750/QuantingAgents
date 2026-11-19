<template>
  <div class="online-badcase-config-page">
    <div class="page-header">
      <h1 class="page-title">线上 Bad Case 配置</h1>
      <p>查看当前生效配置、编辑发布草稿、回滚历史版本。</p>
    </div>

    <el-card shadow="never" class="config-card">
      <template #header>
        <span>当前配置</span>
      </template>
      <el-descriptions :column="3" border size="small">
        <el-descriptions-item label="总开关">{{ effective.enabled ? '开启' : '关闭' }}</el-descriptions-item>
        <el-descriptions-item label="Judge 软信号">{{ effective.enable_judge ? '开启' : '关闭' }}</el-descriptions-item>
        <el-descriptions-item label="配置来源">{{ effective.source || '-' }}</el-descriptions-item>
        <el-descriptions-item label="采样率">{{ formatRate(effective.soft_sample_rate) }}</el-descriptions-item>
        <el-descriptions-item label="确认置信度">{{ formatRate(effective.confidence_threshold) }}</el-descriptions-item>
        <el-descriptions-item label="内容截断">{{ effective.max_content_length || '-' }}</el-descriptions-item>
      </el-descriptions>
    </el-card>

    <el-card shadow="never" class="config-card">
      <template #header>
        <span>编辑与发布</span>
      </template>
      <el-form label-width="180px" style="max-width: 760px">
        <el-form-item label="线上自动发现">
          <el-switch v-model="form.enabled" />
        </el-form-item>
        <el-form-item label="LLM Judge 软信号">
          <el-switch v-model="form.enable_judge" />
        </el-form-item>
        <el-form-item label="软信号采样率">
          <el-slider v-model="form.soft_sample_rate" :min="0" :max="1" :step="0.05" show-input />
        </el-form-item>
        <el-form-item label="自动确认置信度">
          <el-slider v-model="form.confidence_threshold" :min="0" :max="1" :step="0.05" show-input />
        </el-form-item>
        <el-form-item label="Judge 低分阈值">
          <el-slider v-model="form.judge_threshold" :min="0" :max="1" :step="0.05" show-input />
        </el-form-item>
        <el-form-item label="证据低分阈值">
          <el-slider v-model="form.evidence_threshold" :min="0" :max="1" :step="0.05" show-input />
        </el-form-item>
        <el-form-item label="内容截断上限">
          <el-input-number v-model="form.max_content_length" :min="1000" :max="200000" :step="1000" />
        </el-form-item>
        <el-form-item label="变更原因">
          <el-input v-model="form.change_reason" type="textarea" :rows="2" />
        </el-form-item>
        <el-form-item>
          <el-button type="primary" :loading="saving" @click="createDraft">创建草稿</el-button>
        </el-form-item>
      </el-form>
    </el-card>

    <el-card shadow="never" class="config-card">
      <template #header>
        <span>历史与回滚</span>
      </template>
      <el-table :data="history" size="small" stripe v-loading="loading">
        <el-table-column prop="version" label="版本" width="70" />
        <el-table-column label="状态" width="100">
          <template #default="{ row }">
            <el-tag :type="row.status === 'published' ? 'success' : row.status === 'draft' ? 'warning' : 'info'" size="small">
              {{ row.status }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column label="总开关" width="90">
          <template #default="{ row }">{{ row.enabled ? '开启' : '关闭' }}</template>
        </el-table-column>
        <el-table-column prop="updated_by" label="更新人" width="140" />
        <el-table-column prop="change_reason" label="变更原因" min-width="200" show-overflow-tooltip />
        <el-table-column prop="updated_at" label="更新时间" min-width="170">
          <template #default="{ row }">{{ formatTime(row.updated_at) }}</template>
        </el-table-column>
        <el-table-column label="操作" width="150" fixed="right">
          <template #default="{ row }">
            <el-button v-if="row.status !== 'published'" type="primary" link size="small" @click="publish(row)">发布</el-button>
            <el-button v-if="row.status !== 'published'" type="warning" link size="small" @click="rollback(row)">回滚</el-button>
          </template>
        </el-table-column>
      </el-table>
    </el-card>
  </div>
</template>

<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { ElMessage } from 'element-plus'
import { evolutionApi } from '@/api/evolutionClient'

const loading = ref(false)
const saving = ref(false)
const effective = ref<any>({})
const history = ref<any[]>([])
const form = ref<any>({
  enabled: false,
  enable_judge: false,
  soft_sample_rate: 0.1,
  confidence_threshold: 0.8,
  judge_threshold: 0.6,
  evidence_threshold: 0.6,
  max_content_length: 5000,
  change_reason: ''
})

const loadData = async () => {
  loading.value = true
  try {
    const res = await evolutionApi.getOnlineBadcaseConfig()
    const data = res.data?.data || {}
    effective.value = data.effective || {}
    history.value = data.history || []
    form.value = {
      ...form.value,
      ...(effective.value || {}),
      change_reason: ''
    }
  } catch (error: any) {
    ElMessage.error(error?.response?.data?.detail || '加载配置失败')
  } finally {
    loading.value = false
  }
}

const createDraft = async () => {
  saving.value = true
  try {
    await evolutionApi.createOnlineBadcaseDraft(form.value)
    ElMessage.success('草稿已创建')
    await loadData()
  } catch (error: any) {
    ElMessage.error(error?.response?.data?.detail || '创建草稿失败')
  } finally {
    saving.value = false
  }
}

const publish = async (row: any) => {
  try {
    await evolutionApi.publishOnlineBadcaseConfig(row.config_id, { change_reason: form.value.change_reason || 'publish' })
    ElMessage.success('配置已发布')
    await loadData()
  } catch (error: any) {
    ElMessage.error(error?.response?.data?.detail || '发布失败')
  }
}

const rollback = async (row: any) => {
  try {
    await evolutionApi.rollbackOnlineBadcaseConfig(row.config_id, { change_reason: form.value.change_reason || 'rollback' })
    ElMessage.success('配置已回滚')
    await loadData()
  } catch (error: any) {
    ElMessage.error(error?.response?.data?.detail || '回滚失败')
  }
}

const formatRate = (value: any) => value === undefined ? '-' : `${Number(value).toFixed(2)}`
const formatTime = (value?: string) => value ? new Date(value).toLocaleString('zh-CN') : '-'

onMounted(loadData)
</script>

<style scoped>
.online-badcase-config-page { padding: 24px; }
.page-header { margin-bottom: 24px; }
.page-title { font-size: 24px; font-weight: 600; margin: 8px 0 4px; }
.page-header p { color: var(--el-text-color-secondary); font-size: 13px; margin: 0; }
.config-card { margin-bottom: 24px; }
</style>
