<template>
  <div class="task-center">
    <!-- 页头 -->
    <div class="hero-header">
      <div class="hero-icon">
        <el-icon><List /></el-icon>
      </div>
      <div class="hero-content">
        <h1 class="hero-title">分析任务</h1>
        <p class="hero-desc">统一查看并管理分析任务：进行中 / 已完成 / 失败</p>
      </div>
    </div>

    <!-- 标签页 -->
    <div class="tabs-bar">
      <div
        v-for="tab in tabs"
        :key="tab.name"
        class="tab-item"
        :class="{ active: activeTab === tab.name }"
        @click="switchTab(tab.name)"
      >
        {{ tab.label }}
      </div>
    </div>

    <!-- 筛选表单 -->
    <el-card class="filter-card" shadow="never">
      <el-form :inline="true" @submit.prevent class="filter-form">
        <el-form-item label="时间范围" class="filter-item">
          <el-date-picker
            v-model="filters.dateRange"
            type="daterange"
            range-separator="至"
            start-placeholder="开始日期"
            end-placeholder="结束日期"
            format="YYYY-MM-DD"
            value-format="YYYY-MM-DD"
            style="width: 260px"
          />
        </el-form-item>
        <el-form-item label="市场" class="filter-item">
          <el-select v-model="filters.market" clearable placeholder="全部" style="width: 120px">
            <el-option label="全部" value="" />
            <el-option label="美股" value="美股" />
            <el-option label="A股" value="A股" />
            <el-option label="港股" value="港股" />
          </el-select>
        </el-form-item>
        <el-form-item label="状态" class="filter-item">
          <el-select v-model="filters.status" clearable placeholder="全部" style="width: 120px">
            <el-option label="全部" value="" />
            <el-option label="进行中" value="processing" />
            <el-option label="已完成" value="completed" />
            <el-option label="失败" value="failed" />
          </el-select>
        </el-form-item>
        <el-form-item label="股票" class="filter-item">
          <el-input v-model="filters.stock" placeholder="代码或名称" style="width: 160px" />
        </el-form-item>
        <el-form-item class="filter-actions">
          <el-button type="primary" @click="applyFilters" :loading="loading">
            <el-icon><Search /></el-icon>
            查询
          </el-button>
          <el-button @click="resetFilters">
            <el-icon><RefreshRight /></el-icon>
            重置
          </el-button>
        </el-form-item>
      </el-form>
    </el-card>

    <!-- 统计卡片 -->
    <div class="stats-grid">
      <div class="stat-card">
        <div class="stat-value">{{ stats.total }}</div>
        <div class="stat-label">总任务</div>
      </div>
      <div class="stat-card">
        <div class="stat-value success">{{ stats.completed }}</div>
        <div class="stat-label">已完成</div>
      </div>
      <div class="stat-card">
        <div class="stat-value danger">{{ stats.failed }}</div>
        <div class="stat-label">失败</div>
      </div>
      <div class="stat-card">
        <div class="stat-value">{{ stats.uniqueStocks }}</div>
        <div class="stat-label">股票数</div>
      </div>
    </div>

    <!-- 任务列表 -->
    <el-card class="list-card" shadow="never">
      <div class="list-toolbar">
        <div class="list-toolbar-left">
          <el-input
            v-model="keyword"
            placeholder="搜索股票代码 / 名称"
            clearable
            style="width: 240px"
            class="search-input"
          >
            <template #prefix>
              <el-icon><Search /></el-icon>
            </template>
          </el-input>
          <el-button @click="refreshList" :loading="loading" class="refresh-btn">
            <el-icon><Refresh /></el-icon>
            刷新
          </el-button>
        </div>
        <div class="list-toolbar-right">
          <el-button @click="exportSelected" :disabled="selectedRows.length===0" type="primary" plain>
            <el-icon><Download /></el-icon>
            导出所选
          </el-button>
        </div>
      </div>

      <el-table
        :data="filteredList"
        v-loading="loading"
        style="width: 100%"
        @selection-change="onSelectionChange"
        class="task-table"
        :header-cell-style="{ background: '#F8FAFC', fontWeight: 600 }"
      >
        <el-table-column type="selection" width="50" />
        <el-table-column prop="task_id" label="任务ID" min-width="200" show-overflow-tooltip />
        <el-table-column prop="stock_code" label="股票代码" width="110" />
        <el-table-column prop="stock_name" label="股票名称" width="140" />
        <el-table-column label="状态" width="100">
          <template #default="{ row }">
            <el-tag :type="getStatusType(row.status)" effect="light" round size="small">
              {{ getStatusText(row.status) }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="progress" label="进度" width="130">
          <template #default="{ row }">
            <el-progress
              :percentage="row.progress || 0"
              :status="row.status==='failed'?'exception':(row.status==='completed'?'success':undefined)"
              :stroke-width="6"
              :show-text="true"
            />
          </template>
        </el-table-column>
        <el-table-column prop="start_time" label="开始时间" width="170">
          <template #default="{ row }">
            {{ formatTime(row.start_time || row.created_at) }}
          </template>
        </el-table-column>
        <el-table-column label="操作" width="280" fixed="right">
          <template #default="{ row }">
            <div class="action-group">
              <el-button v-if="row.status==='completed'" link type="primary" size="small" @click="openResult(row)">查看结果</el-button>
              <el-button v-if="row.status==='completed'" link type="primary" size="small" @click="openReport(row)">报告详情</el-button>
              <el-button v-if="row.status==='failed'" link type="warning" size="small" @click="showErrorDetail(row)">查看错误</el-button>
              <el-button v-if="row.status==='failed'" link type="primary" size="small" @click="retryTask(row)">重试</el-button>
              <el-button
                v-if="row.status==='processing' || row.status==='running' || row.status==='pending' || row.status==='queued'"
                link
                type="warning"
                size="small"
                @click="markAsFailed(row)"
              >
                {{ row.task_type === 'vibe_agent' ? '取消' : '标记失败' }}
              </el-button>
              <el-button v-if="row.task_type !== 'vibe_agent'" link type="danger" size="small" @click="deleteTask(row)">删除</el-button>
            </div>
          </template>
        </el-table-column>
      </el-table>

      <div class="pagination-wrapper">
        <el-pagination
          v-model:current-page="currentPage"
          v-model:page-size="pageSize"
          :page-sizes="[20, 50, 100]"
          :total="total"
          layout="total, sizes, prev, pager, next, jumper"
          @size-change="handleSizeChange"
          @current-change="handleCurrentChange"
        />
      </div>
    </el-card>

    <!-- 结果弹窗 -->
    <TaskResultDialog
      v-model="resultVisible"
      :result="currentResult"
      @close="resultVisible=false"
      @view-report="openReport(currentRow)"
    />

    <!-- 报告详情弹窗 -->
    <TaskReportDialog v-model="reportVisible" :sections="reportSections" @close="reportVisible=false" />
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, onUnmounted, nextTick, watch } from 'vue'
import { useRouter, useRoute } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'
import { List, Refresh, Download, Search, RefreshRight } from '@element-plus/icons-vue'
import { analysisApi } from '@/api/analysis'
import { vibeAgentApi } from '@/api/vibeAgent'
import TaskResultDialog from '@/components/Global/TaskResultDialog.vue'
import TaskReportDialog from '@/components/Global/TaskReportDialog.vue'

const router = useRouter()
const route = useRoute()

const activeTab = ref<TabKey>('running')
const loading = ref(false)
const keyword = ref('')
const currentPage = ref(1)
const pageSize = ref(20)
const total = ref(0)
const list = ref<any[]>([])
const selectedRows = ref<any[]>([])

type TabKey = 'running' | 'completed' | 'failed' | 'all'
const tabs: { name: TabKey; label: string }[] = [
  { name: 'running', label: '进行中' },
  { name: 'completed', label: '已完成' },
  { name: 'failed', label: '失败' },
  { name: 'all', label: '全部' }
]

const filters = ref<{ dateRange: string[]; market: string; status: string; stock: string }>({
  dateRange: [], market: '', status: '', stock: ''
})
const stats = ref({ total: 0, completed: 0, failed: 0, uniqueStocks: 0 })

let wsConnections: Map<string, WebSocket> = new Map()
let timer: any = null

const setupPolling = () => {
  clearInterval(timer)
  if (activeTab.value === 'running') {
    timer = setInterval(() => loadList(), 5000)
  }
}

const connectTaskWebSocket = (taskId: string) => {
  if (wsConnections.has(taskId)) {
    return
  }

  try {
    const wsProtocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:'
    const host = window.location.host
    const wsUrl = `${wsProtocol}//${host}/api/ws/task/${taskId}`

    const ws = new WebSocket(wsUrl)

    ws.onopen = () => {
      console.log(`✅ WebSocket 连接成功: ${taskId}`)
    }

    ws.onmessage = (event) => {
      try {
        const message = JSON.parse(event.data)
        if (message.type === 'progress_update') {
          const taskIndex = list.value.findIndex(t => t.task_id === taskId)
          if (taskIndex >= 0) {
            list.value[taskIndex].progress = message.progress
            list.value[taskIndex].status = message.status
            list.value[taskIndex].message = message.message
            console.log(`📊 更新任务进度: ${taskId} -> ${message.progress}%`)
          }
        }
      } catch (e) {
        console.error('WebSocket 消息解析失败:', e)
      }
    }

    ws.onerror = (error) => {
      console.error(`❌ WebSocket 错误: ${taskId}`, error)
    }

    ws.onclose = () => {
      console.log(`🔌 WebSocket 断开: ${taskId}`)
      wsConnections.delete(taskId)
    }

    wsConnections.set(taskId, ws)
  } catch (e) {
    console.error('WebSocket 连接失败:', e)
  }
}

const disconnectAllWebSockets = () => {
  wsConnections.forEach((ws) => {
    try {
      ws.close()
    } catch (e) {
      console.error('关闭 WebSocket 失败:', e)
    }
  })
  wsConnections.clear()
}

const statusParam = computed(() => {
  if (activeTab.value === 'all') return undefined
  if (activeTab.value === 'running') return 'processing'
  return activeTab.value
})

const loadList = async () => {
  loading.value = true
  try {
    const params: any = {
      page: currentPage.value,
      page_size: pageSize.value,
      status: filters.value.status || statusParam.value,
      stock_code: filters.value.stock || undefined
    }
    if (filters.value.market) params.market_type = filters.value.market
    if (filters.value.dateRange && filters.value.dateRange.length === 2) {
      params.start_date = filters.value.dateRange[0]
      params.end_date = filters.value.dateRange[1]
    }

    const res = await analysisApi.getHistory(params)
    const body = (res as any)?.data?.data || (res as any)?.data || {}
    let tasks = body.tasks || body.analyses || []

    const noExtraFilters = !filters.value.market && !filters.value.stock && (!filters.value.dateRange || filters.value.dateRange.length === 0)
    if (tasks.length === 0 && noExtraFilters) {
      try {
        const res2 = await analysisApi.getTaskList({
          status: statusParam.value,
          limit: pageSize.value,
          offset: (currentPage.value - 1) * pageSize.value
        })
        const body2 = (res2 as any)?.data?.data || {}
        tasks = body2.tasks || []
        total.value = body2.total ?? tasks.length
      } catch {}
    } else {
      total.value = body.total ?? tasks.length
    }

    if (noExtraFilters) {
      try {
        const vibeRes = await vibeAgentApi.listTasks({
          page: currentPage.value,
          page_size: pageSize.value
        })
        const vibeBody = (vibeRes as any)?.data || {}
        const vibeTasks = (vibeBody.tasks || []).filter((task: any) => {
          const desired = filters.value.status || statusParam.value
          if (!desired) return true
          if (desired === 'processing') return ['queued', 'processing', 'pending', 'running'].includes(task.status)
          return task.status === desired
        })
        tasks = [...tasks, ...vibeTasks].sort((a: any, b: any) => {
          return new Date(b.created_at || 0).getTime() - new Date(a.created_at || 0).getTime()
        })
        total.value = (total.value || 0) + vibeTasks.length
      } catch (error) {
        console.warn('加载自然语言研究任务失败', error)
      }
    }

    list.value = tasks

    tasks.forEach((task: any) => {
      if (task.task_type !== 'vibe_agent' && (task.status === 'processing' || task.status === 'running' || task.status === 'pending')) {
        connectTaskWebSocket(task.task_id)
      }
    })

    const completed = tasks.filter((x:any) => x.status === 'completed').length
    const failed = tasks.filter((x:any) => x.status === 'failed').length
    const uniqueStocks = new Set(tasks.map((x:any) => x.stock_code || x.stock_symbol).filter(Boolean)).size
    stats.value = { total: tasks.length, completed, failed, uniqueStocks }
  } catch (e:any) {
    ElMessage.error(e?.message || '加载失败')
  } finally {
    loading.value = false
  }
}

const applyFilters = () => { currentPage.value = 1; loadList() }
const resetFilters = () => { filters.value = { dateRange: [], market: '', status: '', stock: '' }; currentPage.value = 1; loadList() }

const reportVisible = ref(false)
const reportSections = ref<Array<{ key?: string; title: string; content: any }>>([])

const filteredList = computed(() => {
  let arr = list.value
  if (keyword.value) {
    const k = keyword.value.toLowerCase()
    arr = arr.filter((x:any) => (x.stock_code||'').toLowerCase().includes(k) || (x.stock_name||'').toLowerCase().includes(k) || (x.task_id||'').toLowerCase().includes(k))
  }
  return arr
})

const handleSizeChange = (size:number) => { pageSize.value = size; currentPage.value = 1; loadList() }
const handleCurrentChange = (page:number) => { currentPage.value = page; loadList() }
const switchTab = (tab: TabKey) => {
  activeTab.value = tab
  nextTick(() => {
    currentPage.value = 1
    loadList()
    setupPolling()
  })
}
const refreshList = () => loadList()
const onSelectionChange = (rows:any[]) => { selectedRows.value = rows }

const resultVisible = ref(false)
const currentResult = ref<any>(null)
const currentRow = ref<any>(null)

const openResult = async (row:any) => {
  currentRow.value = row
  if (row.task_type === 'vibe_agent') {
    void router.push('/research-agent')
    return
  }
  try {
    const res = await analysisApi.getTaskResult(row.task_id)
    const body = (res as any)?.data?.data || {}
    currentResult.value = body
    resultVisible.value = true
  } catch (e:any) {
    ElMessage.error('获取结果失败')
  }
}

const openReport = (row:any): void => {
  if (row?.task_type === 'vibe_agent') {
    void router.push('/research-agent')
    return
  }
  const id = row?.task_id || row?.analysis_id || row?.id
  if (!id) {
    ElMessage.warning('未找到报告ID')
    return
  }
  void router.push({ name: 'ReportDetail', params: { id } })
}

const retryTask = (_row:any) => { ElMessage.info('重试功能待实现') }

const showErrorDetail = async (row: any) => {
  try {
    const taskId = row.task_id || row.analysis_id || row.id
    if (!taskId) {
      ElMessage.error('任务ID不存在')
      return
    }

    const res = await analysisApi.getTaskStatus(taskId)
    const task = (res as any)?.data?.data || row
    const errorMessage = task.error_message || task.message || '未知错误'

    await ElMessageBox.alert(
      errorMessage.replace(/\n/g, '<br>'),
      '错误详情',
      {
        confirmButtonText: '确定',
        type: 'error',
        dangerouslyUseHTMLString: true,
        customStyle: { width: '600px' }
      }
    )
  } catch (e: any) {
    if (e !== 'cancel' && e !== 'close') {
      ElMessage.error(e?.message || '获取错误详情失败')
    }
  }
}

const markAsFailed = async (row: any) => {
  try {
    await ElMessageBox.confirm(
      `确定要将任务 "${row.stock_name || row.stock_code}" 标记为失败吗？`,
      '确认操作',
      {
        confirmButtonText: '确定',
        cancelButtonText: '取消',
        type: 'warning'
      }
    )

    const taskId = row.task_id || row.analysis_id || row.id
    if (!taskId) {
      ElMessage.error('任务ID不存在')
      return
    }

    loading.value = true
    if (row.task_type === 'vibe_agent') {
      await vibeAgentApi.cancelTask(taskId)
      ElMessage.success('任务已取消')
    } else {
      await analysisApi.markTaskAsFailed(taskId)
      ElMessage.success('任务已标记为失败')
    }
    await loadList()
  } catch (e: any) {
    if (e !== 'cancel') {
      ElMessage.error(e?.message || '标记失败')
    }
  } finally {
    loading.value = false
  }
}

const deleteTask = async (row: any) => {
  try {
    await ElMessageBox.confirm(
      `确定要删除任务 "${row.stock_name || row.stock_code}" 吗？此操作不可恢复！`,
      '确认删除',
      {
        confirmButtonText: '确定',
        cancelButtonText: '取消',
        type: 'error'
      }
    )

    const taskId = row.task_id || row.analysis_id || row.id
    if (!taskId) {
      ElMessage.error('任务ID不存在')
      return
    }

    loading.value = true
    if (row.task_type === 'vibe_agent') {
      await vibeAgentApi.cancelTask(taskId)
    } else {
      await analysisApi.deleteTask(taskId)
    }
    ElMessage.success('任务已删除')
    await loadList()
  } catch (e: any) {
    if (e !== 'cancel') {
      ElMessage.error(e?.message || '删除失败')
    }
  } finally {
    loading.value = false
  }
}

const exportSelected = () => {
  try {
    const data = JSON.stringify(selectedRows.value, null, 2)
    const blob = new Blob([data], { type: 'application/json;charset=utf-8' })
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = `tasks_selected_${Date.now()}.json`
    document.body.appendChild(a)
    a.click()
    document.body.removeChild(a)
    URL.revokeObjectURL(url)
    ElMessage.success('导出成功')
  } catch {
    ElMessage.error('导出失败')
  }
}

onMounted(() => {
  const tab = String((route.query as any)?.tab || '').toLowerCase()
  const validTabs = ['running', 'completed', 'failed', 'all']
  if (validTabs.includes(tab)) {
    activeTab.value = tab as any
  }
  loadList(); setupPolling()
})

watch(() => (route.query as any)?.tab, (newVal) => {
  const tab = String(newVal || '').toLowerCase()
  const validTabs = ['running', 'completed', 'failed', 'all']
  if (validTabs.includes(tab)) {
    activeTab.value = tab as any
    currentPage.value = 1
    loadList()
    setupPolling()
  }
})

onUnmounted(() => {
  clearInterval(timer)
  disconnectAllWebSockets()
})

const getStatusType = (status:string): 'success' | 'info' | 'warning' | 'danger' => {
  const map: Record<string,'success'|'info'|'warning'|'danger'> = {
    pending: 'info', queued: 'info', processing: 'warning', completed: 'success', failed: 'danger', cancelled: 'info'
  }
  return map[status] || 'info'
}
import { formatDateTime } from '@/utils/datetime'

const getStatusText = (status:string) => ({ pending:'等待中', queued:'等待中', processing:'处理中', completed:'已完成', failed:'失败', cancelled:'已取消' } as any)[status] || status
const formatTime = (t:string) => t ? formatDateTime(t) : '-'
</script>

<style scoped lang="scss">
.task-center {
  .hero-header {
    display: flex;
    align-items: center;
    gap: 16px;
    padding: 28px 28px;
    margin-bottom: 20px;
    border-radius: 20px;
    background: var(--zt-gradient-hero);
    color: #fff;
    box-shadow: 0 10px 25px -5px rgba(14, 165, 233, 0.3);

    .hero-icon {
      width: 52px;
      height: 52px;
      border-radius: 14px;
      background: rgba(255, 255, 255, 0.2);
      backdrop-filter: blur(8px);
      display: flex;
      align-items: center;
      justify-content: center;

      .el-icon {
        font-size: 28px;
        color: #fff;
      }
    }

    .hero-content {
      .hero-title {
        font-size: 26px;
        font-weight: 700;
        color: #fff;
        margin: 0 0 6px 0;
        letter-spacing: -0.3px;
      }

      .hero-desc {
        margin: 0;
        font-size: 14px;
        color: rgba(255, 255, 255, 0.9);
      }
    }
  }

  .tabs-bar {
    display: flex;
    gap: 8px;
    margin-bottom: 16px;
    padding: 6px;
    background: var(--el-bg-color);
    border: 1px solid var(--el-border-color-light);
    border-radius: 14px;
    width: fit-content;

    .tab-item {
      padding: 8px 20px;
      border-radius: 10px;
      font-size: 14px;
      font-weight: 500;
      color: var(--el-text-color-secondary);
      cursor: pointer;
      transition: all 0.2s ease;
      user-select: none;

      &:hover {
        color: var(--el-text-color-primary);
        background: var(--el-fill-color-light);
      }

      &.active {
        color: #fff;
        background: var(--zt-gradient-hero);
        box-shadow: 0 2px 8px rgba(14, 165, 233, 0.25);
      }
    }
  }

  .filter-card {
    margin-bottom: 16px;
    border-radius: 16px;

    :deep(.el-card__body) {
      padding: 18px 20px;
    }

    .filter-form {
      display: flex;
      flex-wrap: wrap;
      align-items: center;
      gap: 8px;
      margin-bottom: -8px;

      .filter-item {
        margin-bottom: 8px;
        margin-right: 0;

        :deep(.el-form-item__label) {
          color: var(--el-text-color-secondary);
          font-size: 13px;
          padding-right: 8px;
        }
      }

      .filter-actions {
        margin-bottom: 8px;
        margin-right: 0;
      }
    }
  }

  .stats-grid {
    display: grid;
    grid-template-columns: repeat(4, 1fr);
    gap: 16px;
    margin-bottom: 16px;

    @media (max-width: 992px) {
      grid-template-columns: repeat(2, 1fr);
    }

    @media (max-width: 576px) {
      grid-template-columns: 1fr;
    }

    .stat-card {
      background: var(--el-bg-color);
      border: 1px solid var(--el-border-color-light);
      border-radius: 16px;
      padding: 22px 18px;
      text-align: center;
      transition: transform 0.2s ease, box-shadow 0.2s ease;

      &:hover {
        transform: translateY(-2px);
        box-shadow: 0 10px 15px -3px rgba(15, 23, 42, 0.06), 0 4px 6px -4px rgba(15, 23, 42, 0.03);
      }

      .stat-value {
        font-size: 32px;
        font-weight: 700;
        color: var(--el-color-primary);
        line-height: 1.2;
        margin-bottom: 6px;

        &.success { color: var(--el-color-success); }
        &.danger { color: var(--el-color-danger); }
      }

      .stat-label {
        font-size: 13px;
        color: var(--el-text-color-secondary);
      }
    }
  }

  .list-card {
    border-radius: 16px;

    :deep(.el-card__body) {
      padding: 20px;
    }

    .list-toolbar {
      display: flex;
      justify-content: space-between;
      align-items: center;
      margin-bottom: 16px;
      gap: 12px;
      flex-wrap: wrap;

      .list-toolbar-left {
        display: flex;
        align-items: center;
        gap: 10px;
      }

      .search-input {
        :deep(.el-input__wrapper) {
          border-radius: 10px;
        }
      }

      .refresh-btn {
        border-radius: 10px;
      }
    }

    .task-table {
      border-radius: 12px;
      overflow: hidden;

      :deep(.el-table__header th) {
        font-weight: 600;
      }

      .action-group {
        display: flex;
        gap: 8px;
        flex-wrap: wrap;
      }
    }

    .pagination-wrapper {
      display: flex;
      justify-content: flex-end;
      margin-top: 18px;
      padding-top: 4px;
    }
  }
}
</style>
