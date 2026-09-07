export type AdminUserStatusFilter = '' | 'active' | 'disabled' | 'archived'

export interface UserManagementListQuery {
  keyword?: string
  status?: AdminUserStatusFilter
  skip: number
  limit: number
}

export const buildUserListQuery = (
  keyword: string,
  status: AdminUserStatusFilter,
  currentPage: number,
  pageSize: number
): UserManagementListQuery => ({
  keyword: keyword || undefined,
  status: status || undefined,
  skip: (currentPage - 1) * pageSize,
  limit: pageSize
})

export const getUserStatusType = (
  isActive: boolean,
  isArchived: boolean
): 'success' | 'danger' | 'info' => {
  if (isArchived) return 'info'
  return isActive ? 'success' : 'danger'
}

export const getUserStatusText = (
  isActive: boolean,
  isArchived: boolean
): string => {
  if (isArchived) return '已归档'
  return isActive ? '正常' : '已禁用'
}

export const isCurrentUser = (
  currentUsername: string | null | undefined,
  username: string
): boolean => currentUsername === username

export const formatUserDateTime = (value?: string | null): string => {
  if (!value) return '-'
  return new Date(value).toLocaleString('zh-CN', { hour12: false })
}
