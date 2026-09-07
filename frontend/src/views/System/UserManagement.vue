<template>
  <div class="user-management">
    <div class="page-header">
      <div class="header-left">
        <h1 class="page-title">
          <el-icon><User /></el-icon>
          用户管理
        </h1>
        <p class="page-description">
          查看和管理平台已注册账号
        </p>
      </div>
      <div class="header-right">
        <el-button type="primary" @click="openCreateDialog">
          <el-icon><Plus /></el-icon>
          创建用户
        </el-button>
      </div>
    </div>

    <el-card class="filter-panel" shadow="never">
      <el-form :inline="true" @submit.prevent="search">
        <el-form-item label="关键字">
          <el-input
            v-model="keyword"
            placeholder="用户名或邮箱"
            clearable
            style="width: 220px"
            @keyup.enter="search"
          >
            <template #prefix>
              <el-icon><Search /></el-icon>
            </template>
          </el-input>
        </el-form-item>

        <el-form-item label="状态">
          <el-select v-model="statusFilter" clearable placeholder="全部状态" style="width: 140px">
            <el-option label="全部状态" value="" />
            <el-option label="正常" value="active" />
            <el-option label="已禁用" value="disabled" />
            <el-option label="已归档" value="archived" />
          </el-select>
        </el-form-item>

        <el-form-item>
          <el-button type="primary" @click="search">
            <el-icon><Search /></el-icon>
            查询
          </el-button>
          <el-button @click="resetFilter">
            <el-icon><Refresh /></el-icon>
            重置
          </el-button>
        </el-form-item>
      </el-form>
    </el-card>

    <el-card class="user-table-card" shadow="never">
      <template #header>
        <div class="table-header">
          <h3>注册账号</h3>
          <el-button size="small" @click="loadUsers">
            <el-icon><Refresh /></el-icon>
            刷新
          </el-button>
        </div>
      </template>

      <el-alert
        v-if="errorMessage"
        :title="errorMessage"
        type="error"
        show-icon
        :closable="true"
        @close="errorMessage = ''"
        style="margin-bottom: 16px"
      />

      <el-table v-loading="loading" :data="users" style="width: 100%">
        <el-table-column prop="username" label="用户名" min-width="140">
          <template #default="{ row }">
            <div class="user-cell">
              <div class="user-name">{{ row.username }}</div>
              <div class="user-id">{{ row.id }}</div>
            </div>
          </template>
        </el-table-column>

        <el-table-column prop="email" label="邮箱" min-width="220">
          <template #default="{ row }">
            <span>{{ row.email }}</span>
          </template>
        </el-table-column>

        <el-table-column label="角色" width="110" align="center">
          <template #default="{ row }">
            <el-tag :type="row.is_admin ? 'warning' : 'info'" size="small">
              {{ row.is_admin ? '管理员' : '普通用户' }}
            </el-tag>
          </template>
        </el-table-column>

        <el-table-column label="状态" width="100" align="center">
          <template #default="{ row }">
            <el-tag :type="getStatusType(row)" size="small">
              {{ getStatusText(row) }}
            </el-tag>
          </template>
        </el-table-column>

        <el-table-column label="创建时间" width="170">
          <template #default="{ row }">
            {{ formatDateTime(row.created_at) }}
          </template>
        </el-table-column>

        <el-table-column label="最后登录" width="170">
          <template #default="{ row }">
            {{ formatDateTime(row.last_login) }}
          </template>
        </el-table-column>

        <el-table-column label="配额" width="130" align="center">
          <template #default="{ row }">
            {{ row.daily_quota }} / {{ row.concurrent_limit }}
          </template>
        </el-table-column>

        <el-table-column label="操作" width="230" fixed="right">
          <template #default="{ row }">
            <el-button size="small" @click="viewDetail(row)">详情</el-button>
            <el-button size="small" type="primary" :disabled="row.is_archived" @click="openEditDialog(row)">
              编辑
            </el-button>
            <el-dropdown
              trigger="click"
              :disabled="row.is_archived"
              @command="(command: string) => handleRowCommand(command, row)"
            >
              <el-button size="small" :disabled="row.is_archived">
                更多
                <el-icon class="el-icon--right"><ArrowDown /></el-icon>
              </el-button>
              <template #dropdown>
                <el-dropdown-menu>
                  <el-dropdown-item v-if="!row.is_active" command="enable">启用账号</el-dropdown-item>
                  <el-dropdown-item v-if="row.is_active" command="disable">禁用账号</el-dropdown-item>
                  <el-dropdown-item command="role">
                    {{ row.is_admin ? '取消管理员' : '设为管理员' }}
                  </el-dropdown-item>
                  <el-dropdown-item command="reset" divided>重置密码</el-dropdown-item>
                  <el-dropdown-item command="archive" divided :disabled="isCurrentUser(row)">
                    归档账号
                  </el-dropdown-item>
                </el-dropdown-menu>
              </template>
            </el-dropdown>
          </template>
        </el-table-column>
      </el-table>

      <el-empty
        v-if="!loading && users.length === 0"
        description="暂无符合条件的账号"
        :image-size="160"
      />

      <el-pagination
        v-if="total > 0"
        v-model:current-page="currentPage"
        v-model:page-size="pageSize"
        :total="total"
        :page-sizes="[10, 20, 50, 100]"
        layout="total, sizes, prev, pager, next, jumper"
        style="margin-top: 16px; text-align: right"
        @size-change="loadUsers"
        @current-change="loadUsers"
      />
    </el-card>

    <el-dialog v-model="detailVisible" title="账号详情" width="720px">
      <el-descriptions v-if="selectedUser" :column="2" border>
        <el-descriptions-item label="用户名">{{ selectedUser.username }}</el-descriptions-item>
        <el-descriptions-item label="邮箱">{{ selectedUser.email }}</el-descriptions-item>
        <el-descriptions-item label="角色">
          <el-tag :type="selectedUser.is_admin ? 'warning' : 'info'" size="small">
            {{ selectedUser.is_admin ? '管理员' : '普通用户' }}
          </el-tag>
        </el-descriptions-item>
        <el-descriptions-item label="状态">
          <el-tag :type="getStatusType(selectedUser)" size="small">
            {{ getStatusText(selectedUser) }}
          </el-tag>
        </el-descriptions-item>
        <el-descriptions-item label="邮箱验证">
          {{ selectedUser.is_verified ? '已验证' : '未验证' }}
        </el-descriptions-item>
        <el-descriptions-item label="用户ID">{{ selectedUser.id }}</el-descriptions-item>
        <el-descriptions-item label="创建时间">{{ formatDateTime(selectedUser.created_at) }}</el-descriptions-item>
        <el-descriptions-item label="更新时间">{{ formatDateTime(selectedUser.updated_at) }}</el-descriptions-item>
        <el-descriptions-item label="最后登录">{{ formatDateTime(selectedUser.last_login) }}</el-descriptions-item>
        <el-descriptions-item label="每日配额">{{ selectedUser.daily_quota }}</el-descriptions-item>
        <el-descriptions-item label="并发限制">{{ selectedUser.concurrent_limit }}</el-descriptions-item>
        <el-descriptions-item label="分析次数">{{ selectedUser.total_analyses }}</el-descriptions-item>
        <el-descriptions-item label="成功 / 失败">
          {{ selectedUser.successful_analyses }} / {{ selectedUser.failed_analyses }}
        </el-descriptions-item>
      </el-descriptions>
    </el-dialog>

    <el-dialog v-model="createVisible" title="创建用户" width="520px" :close-on-click-modal="false">
      <el-form ref="createFormRef" :model="createForm" :rules="createRules" label-width="90px">
        <el-form-item label="用户名" prop="username">
          <el-input v-model="createForm.username" placeholder="3-50 位用户名" />
        </el-form-item>
        <el-form-item label="邮箱" prop="email">
          <el-input v-model="createForm.email" placeholder="user@example.com" />
        </el-form-item>
        <el-form-item label="密码" prop="password">
          <el-input v-model="createForm.password" type="password" show-password placeholder="至少 8 位，包含字母和数字" />
        </el-form-item>
        <el-form-item label="管理员">
          <el-switch v-model="createForm.is_admin" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="createVisible = false">取消</el-button>
        <el-button type="primary" :loading="submitLoading" @click="submitCreateUser">创建</el-button>
      </template>
    </el-dialog>

    <el-dialog v-model="editVisible" title="编辑账号" width="520px" :close-on-click-modal="false">
      <el-form ref="editFormRef" :model="editForm" :rules="editRules" label-width="110px">
        <el-form-item label="用户名">
          <el-input :model-value="editTarget?.username" disabled />
        </el-form-item>
        <el-form-item label="邮箱" prop="email">
          <el-input v-model="editForm.email" />
        </el-form-item>
        <el-form-item label="每日配额" prop="daily_quota">
          <el-input-number v-model="editForm.daily_quota" :min="0" :max="100000" />
        </el-form-item>
        <el-form-item label="并发限制" prop="concurrent_limit">
          <el-input-number v-model="editForm.concurrent_limit" :min="1" :max="100" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="editVisible = false">取消</el-button>
        <el-button type="primary" :loading="submitLoading" @click="submitEditUser">保存</el-button>
      </template>
    </el-dialog>

    <el-dialog v-model="resetVisible" title="重置密码" width="480px" :close-on-click-modal="false">
      <p class="dialog-tip">正在为 {{ resetTarget?.username }} 设置新密码，重置后旧会话将失效。</p>
      <el-form ref="resetFormRef" :model="resetForm" :rules="resetRules" label-width="90px">
        <el-form-item label="新密码" prop="new_password">
          <el-input v-model="resetForm.new_password" type="password" show-password placeholder="至少 8 位，包含字母和数字" />
        </el-form-item>
        <el-form-item label="确认密码" prop="confirm_password">
          <el-input v-model="resetForm.confirm_password" type="password" show-password />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="resetVisible = false">取消</el-button>
        <el-button type="primary" :loading="submitLoading" @click="submitResetPassword">确认重置</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { onMounted, reactive, ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { User, Search, Refresh, Plus, ArrowDown } from '@element-plus/icons-vue'
import { authApi } from '@/api/auth'
import { useAuthStore } from '@/stores/auth'
import type { AdminUserDetail, AdminUserSummary } from '@/types/auth'
import {
  buildUserListQuery,
  formatUserDateTime,
  getUserStatusText,
  getUserStatusType,
  isCurrentUser as isSameUser
} from './userManagement'

type TagType = 'primary' | 'success' | 'warning' | 'info' | 'danger'

const authStore = useAuthStore()
const loading = ref(false)
const submitLoading = ref(false)
const errorMessage = ref('')
const users = ref<AdminUserSummary[]>([])
const total = ref(0)
const currentPage = ref(1)
const pageSize = ref(20)
const keyword = ref('')
const statusFilter = ref<'' | 'active' | 'disabled' | 'archived'>('')

const detailVisible = ref(false)
const selectedUser = ref<AdminUserDetail | null>(null)
const createVisible = ref(false)
const editVisible = ref(false)
const resetVisible = ref(false)
const createFormRef = ref()
const editFormRef = ref()
const resetFormRef = ref()
const editTarget = ref<AdminUserSummary | null>(null)
const resetTarget = ref<AdminUserSummary | null>(null)

const createForm = reactive({
  username: '',
  email: '',
  password: '',
  is_admin: false
})

const editForm = reactive({
  email: '',
  daily_quota: 1000,
  concurrent_limit: 3
})

const resetForm = reactive({
  new_password: '',
  confirm_password: ''
})

const createRules: Record<string, any[]> = {
  username: [
    { required: true, message: '请输入用户名', trigger: 'blur' },
    { min: 3, max: 50, message: '用户名长度为 3-50 位', trigger: 'blur' }
  ],
  email: [
    { required: true, message: '请输入邮箱', trigger: 'blur' },
    { type: 'email', message: '请输入有效邮箱', trigger: 'blur' }
  ],
  password: [
    { required: true, message: '请输入密码', trigger: 'blur' },
    { min: 8, message: '密码至少 8 位', trigger: 'blur' },
    {
      pattern: /^(?=.*[A-Za-z])(?=.*\d).+$/,
      message: '密码必须包含字母和数字',
      trigger: 'blur'
    }
  ]
}

const editRules: Record<string, any[]> = {
  email: [
    { required: true, message: '请输入邮箱', trigger: 'blur' },
    { type: 'email', message: '请输入有效邮箱', trigger: 'blur' }
  ],
  daily_quota: [
    { required: true, message: '请输入每日配额', trigger: 'blur' }
  ],
  concurrent_limit: [
    { required: true, message: '请输入并发限制', trigger: 'blur' }
  ]
}

const resetRules: Record<string, any[]> = {
  new_password: [
    { required: true, message: '请输入新密码', trigger: 'blur' },
    { min: 8, message: '密码至少 8 位', trigger: 'blur' },
    {
      pattern: /^(?=.*[A-Za-z])(?=.*\d).+$/,
      message: '密码必须包含字母和数字',
      trigger: 'blur'
    }
  ],
  confirm_password: [
    { required: true, message: '请确认新密码', trigger: 'blur' },
    {
      validator: (_rule: unknown, value: string, callback: (error?: Error) => void) => {
        value === resetForm.new_password ? callback() : callback(new Error('两次输入的密码不一致'))
      },
      trigger: 'blur'
    }
  ]
}

const loadUsers = async () => {
  loading.value = true
  errorMessage.value = ''
  try {
    const response = await authApi.adminListUsers(
      buildUserListQuery(keyword.value, statusFilter.value, currentPage.value, pageSize.value)
    )
    users.value = response.data.users
    total.value = response.data.total
  } catch (error) {
    errorMessage.value = '加载账号列表失败，请稍后重试'
    console.error('加载账号列表失败:', error)
  } finally {
    loading.value = false
  }
}

const search = () => {
  currentPage.value = 1
  loadUsers()
}

const resetFilter = () => {
  keyword.value = ''
  statusFilter.value = ''
  currentPage.value = 1
  loadUsers()
}

const viewDetail = async (row: AdminUserSummary) => {
  try {
    const response = await authApi.adminGetUser(row.username)
    selectedUser.value = response.data
    detailVisible.value = true
  } catch (error) {
    ElMessage.error('获取账号详情失败')
    console.error('获取账号详情失败:', error)
  }
}

const openCreateDialog = () => {
  Object.assign(createForm, { username: '', email: '', password: '', is_admin: false })
  createVisible.value = true
}

const openEditDialog = (row: AdminUserSummary) => {
  editTarget.value = row
  editForm.email = row.email
  editForm.daily_quota = row.daily_quota
  editForm.concurrent_limit = row.concurrent_limit
  editVisible.value = true
}

const openResetDialog = (row: AdminUserSummary) => {
  resetTarget.value = row
  resetForm.new_password = ''
  resetForm.confirm_password = ''
  resetVisible.value = true
}

const submitCreateUser = async () => {
  await createFormRef.value.validate()
  submitLoading.value = true
  try {
    const response = await authApi.adminCreateUser(createForm)
    ElMessage.success(response.message || '用户创建成功')
    createVisible.value = false
    loadUsers()
  } catch (error) {
    console.error('创建用户失败:', error)
  } finally {
    submitLoading.value = false
  }
}

const submitEditUser = async () => {
  if (!editTarget.value) return
  await editFormRef.value.validate()
  submitLoading.value = true
  try {
    const response = await authApi.adminUpdateUser(editTarget.value.username, {
      email: editForm.email,
      daily_quota: editForm.daily_quota,
      concurrent_limit: editForm.concurrent_limit
    })
    ElMessage.success(response.message || '账号资料已更新')
    editVisible.value = false
    loadUsers()
  } catch (error) {
    console.error('更新账号失败:', error)
  } finally {
    submitLoading.value = false
  }
}

const submitResetPassword = async () => {
  if (!resetTarget.value) return
  await resetFormRef.value.validate()
  submitLoading.value = true
  try {
    const response = await authApi.adminResetPassword(resetTarget.value.username, resetForm.new_password)
    ElMessage.success(response.message || '密码重置成功')
    resetVisible.value = false
  } catch (error) {
    console.error('重置密码失败:', error)
  } finally {
    submitLoading.value = false
  }
}

const isCurrentUser = (row: AdminUserSummary): boolean => {
  return isSameUser(authStore.user?.username, row.username)
}

const handleRowCommand = async (command: string, row: AdminUserSummary) => {
  if (command === 'enable' || command === 'disable') {
    const isActive = command === 'enable'
    try {
      await ElMessageBox.confirm(
        isActive ? `确定启用账号 ${row.username} 吗？` : `确定禁用账号 ${row.username} 吗？`,
        isActive ? '启用确认' : '禁用确认',
        { type: isActive ? 'success' : 'warning' }
      )
      const response = await authApi.adminUpdateUserStatus(row.username, isActive)
      ElMessage.success(response.message || '账号状态已更新')
      loadUsers()
    } catch (error) {
      if (error !== 'cancel') {
        console.error('更新账号状态失败:', error)
      }
    }
    return
  }

  if (command === 'role') {
    const isAdmin = !row.is_admin
    try {
      await ElMessageBox.confirm(
        isAdmin ? `确定将 ${row.username} 设为管理员吗？` : `确定取消 ${row.username} 的管理员角色吗？`,
        '角色变更确认',
        { type: 'warning' }
      )
      const response = await authApi.adminUpdateUserRole(row.username, isAdmin)
      ElMessage.success(response.message || '账号角色已更新')
      loadUsers()
    } catch (error) {
      if (error !== 'cancel') {
        console.error('更新账号角色失败:', error)
      }
    }
    return
  }

  if (command === 'reset') {
    openResetDialog(row)
    return
  }

  if (command === 'archive') {
    try {
      await ElMessageBox.confirm(
        `确定归档账号 ${row.username} 吗？归档后该账号无法登录，历史资源会保留。`,
        '归档确认',
        { type: 'error', confirmButtonText: '确认归档', cancelButtonText: '取消' }
      )
      const response = await authApi.adminArchiveUser(row.username)
      ElMessage.success(response.message || '账号已归档')
      loadUsers()
    } catch (error) {
      if (error !== 'cancel') {
        console.error('归档账号失败:', error)
      }
    }
  }
}

const getStatusType = (row: AdminUserSummary | AdminUserDetail): TagType => {
  return getUserStatusType(row.is_active, row.is_archived)
}

const getStatusText = (row: AdminUserSummary | AdminUserDetail): string => {
  return getUserStatusText(row.is_active, row.is_archived)
}

const formatDateTime = (value?: string | null): string => {
  return formatUserDateTime(value)
}

onMounted(loadUsers)
</script>

<style lang="scss" scoped>
.user-management {
  padding: 24px;
}

.page-header {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 16px;
  margin-bottom: 20px;
}

.page-title {
  display: flex;
  align-items: center;
  gap: 8px;
  margin: 0 0 6px;
  font-size: 22px;
  font-weight: 600;
}

.page-description {
  margin: 0;
  color: #667085;
  font-size: 14px;
}

.filter-panel,
.user-table-card {
  margin-bottom: 20px;
}

.table-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
}

.table-header h3 {
  margin: 0;
  font-size: 16px;
}

.user-cell {
  display: flex;
  flex-direction: column;
  gap: 2px;
}

.user-name {
  font-weight: 600;
}

.user-id {
  color: #98a2b3;
  font-size: 12px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  max-width: 220px;
}

.dialog-tip {
  margin: 0 0 16px;
  color: #667085;
}
</style>
