<template>
  <div class="evolution-artifacts">
    <el-page-header title="Artifact 注册表" @back="$router.push('/evolution/proposals')" />

    <!-- 筛选 -->
    <el-card style="margin-top: 16px; margin-bottom: 16px;">
      <el-form :inline="true">
        <el-form-item label="类型">
          <el-select v-model="filterType" placeholder="全部" clearable @change="loadArtifacts">
            <el-option label="Skill" value="skill" />
            <el-option label="Prompt" value="prompt" />
            <el-option label="Policy" value="policy" />
            <el-option label="Rubric" value="rubric" />
            <el-option label="Case" value="case" />
          </el-select>
        </el-form-item>
        <el-form-item>
          <el-button type="primary" @click="loadArtifacts">刷新</el-button>
        </el-form-item>
      </el-form>
    </el-card>

    <!-- Artifact 列表 -->
    <el-card v-loading="loading">
      <el-table :data="artifacts" stripe>
        <el-table-column prop="artifact_id" label="Artifact ID" min-width="200" />
        <el-table-column prop="name" label="名称" width="180" />
        <el-table-column prop="artifact_type" label="类型" width="100">
          <template #default="{ row }">
            <el-tag size="small">{{ row.artifact_type }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="current_version" label="当前版本" width="120" />
        <el-table-column prop="environments.default" label="默认环境" width="110">
          <template #default="{ row }">{{ row.environments?.default || row.current_version || '-' }}</template>
        </el-table-column>
        <el-table-column prop="owner" label="负责人" width="120" />
        <el-table-column prop="rollback_strategy" label="回滚策略" width="150" />
        <el-table-column label="操作" width="120" fixed="right">
          <template #default="{ row }">
            <el-button link type="primary" size="small" @click="showVersions(row)">版本历史</el-button>
          </template>
        </el-table-column>
      </el-table>
      <el-empty v-if="!artifacts.length && !loading" description="暂无已注册的 Artifact" />
    </el-card>

    <!-- 版本历史弹窗 -->
    <el-dialog v-model="versionDialogVisible" :title="'版本历史: ' + selectedArtifact?.artifact_id" width="820px">
      <el-table :data="versions" v-loading="versionsLoading" stripe>
        <el-table-column prop="version" label="版本" width="100" />
        <el-table-column prop="status" label="状态" width="120">
          <template #default="{ row }">
            <el-tag size="small" :type="versionStatusTagType(row.status)">{{ versionStatusLabel(row.status) }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="environment" label="环境" width="90" />
        <el-table-column prop="published_environments" label="已发布环境" min-width="130">
          <template #default="{ row }">
            <el-tag v-for="env in (row.published_environments || [])" :key="env" size="small" class="tag-gap">{{ env }}</el-tag>
            <span v-if="!row.published_environments?.length">-</span>
          </template>
        </el-table-column>
        <el-table-column prop="owner" label="创建者" width="120" />
        <el-table-column prop="created_at" label="创建时间" width="180">
          <template #default="{ row }">{{ formatDate(row.created_at) }}</template>
        </el-table-column>
        <el-table-column label="操作" width="100">
          <template #default="{ row }">
            <el-button v-if="row.status !== 'active'" link type="warning" size="small" @click="handleRollback(row.version)">
              回滚到此版本
            </el-button>
          </template>
        </el-table-column>
      </el-table>
      <template v-if="releaseReceipts.length">
        <el-divider />
        <h4 class="receipt-title">发布 / 回滚回执</h4>
        <el-table :data="releaseReceipts" size="small" stripe>
          <el-table-column prop="receipt_id" label="回执 ID" width="150" />
          <el-table-column prop="release_status" label="发布状态" width="110">
            <template #default="{ row }">
              <el-tag size="small" :type="releaseStatusTagType(row.release_status)">{{ releaseStatusLabel(row.release_status) }}</el-tag>
            </template>
          </el-table-column>
          <el-table-column prop="before_version" label="切换前" width="100" />
          <el-table-column prop="after_version" label="切换后" width="100" />
          <el-table-column prop="environment" label="环境" width="100" />
        </el-table>
      </template>
      <el-empty v-if="!versions.length && !versionsLoading" description="暂无版本记录" />
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { evolutionApi } from '@/api/evolutionClient'

const loading = ref(false)
const artifacts = ref<any[]>([])
const filterType = ref('')
const versionDialogVisible = ref(false)
const versionsLoading = ref(false)
const versions = ref<any[]>([])
const releaseReceipts = ref<any[]>([])
const selectedArtifact = ref<any>(null)

const versionStatusLabel = (status: string) => ({
  pending: '待生效',
  active: '生效中',
  failed: '失败',
  superseded: '已替代',
  rolled_back: '已回滚',
}[status] || status)

const versionStatusTagType = (status: string): any => ({
  pending: 'warning',
  active: 'success',
  failed: 'danger',
  superseded: 'info',
  rolled_back: 'warning',
}[status] || 'info')

const releaseStatusLabel = (status: string) => ({
  succeeded: '成功',
  compensated: '已补偿',
  failed: '失败',
}[status] || '未记录')

const releaseStatusTagType = (status: string): any => ({
  succeeded: 'success',
  compensated: 'warning',
  failed: 'danger',
}[status] || 'info')

const loadArtifacts = async () => {
  loading.value = true
  try {
    const params: Record<string, any> = {}
    if (filterType.value) params.artifact_type = filterType.value
    const res = await evolutionApi.getArtifacts(params)
    artifacts.value = res.data?.data?.items || []
  } catch (e) {
    console.error('Failed to load artifacts', e)
  } finally {
    loading.value = false
  }
}

const showVersions = async (artifact: any) => {
  selectedArtifact.value = artifact
  versionDialogVisible.value = true
  versionsLoading.value = true
  try {
    const [versionsRes, historyRes] = await Promise.all([
      evolutionApi.getArtifactVersions(artifact.artifact_id),
      evolutionApi.getArtifactReleaseHistory(artifact.artifact_id),
    ])
    versions.value = versionsRes.data?.data?.items || []
    releaseReceipts.value = historyRes.data?.data?.receipts || []
  } catch (e) {
    console.error('Failed to load versions', e)
  } finally {
    versionsLoading.value = false
  }
}

const handleRollback = async (targetVersion: string) => {
  try {
    await ElMessageBox.confirm(`确认将 ${selectedArtifact.value.artifact_id} 回滚到版本 ${targetVersion}？`, '回滚确认', { type: 'warning' })
    await evolutionApi.rollbackArtifact(selectedArtifact.value.artifact_id, { target_version: targetVersion, reason: 'Manual rollback from UI' })
    ElMessage.success('回滚成功')
    showVersions(selectedArtifact.value)
    loadArtifacts()
  } catch {}
}

const formatDate = (d: string) => d ? new Date(d).toLocaleString('zh-CN') : '-'

onMounted(loadArtifacts)
</script>

<style scoped>
.tag-gap {
  margin-right: 4px;
}

.receipt-title {
  margin: 4px 0 10px;
  font-size: 14px;
}
</style>
