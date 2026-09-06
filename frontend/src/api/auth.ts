import { ApiClient } from './request'
import type { 
  LoginForm, 
  RegisterForm, 
  LoginResponse, 
  RefreshTokenResponse,
  User,
  ChangePasswordForm,
  AdminUserListData,
  AdminUserListQuery,
  AdminUserDetail,
  AdminCreateUserForm,
  AdminUpdateUserForm
} from '@/types/auth'

export const authApi = {
  // 登录
  login: (data: LoginForm) =>
    ApiClient.post<LoginResponse>('/api/auth/login', data, {
      skipAuth: true,  // 登录请求不需要认证
      skipAuthError: true  // 跳过 401 错误的自动处理
    }),

  // 注册
  register: (data: RegisterForm) =>
    ApiClient.post('/api/auth/register', data, {
      skipAuth: true,  // 注册请求不需要认证
      skipAuthError: true  // 跳过 401 错误的自动处理
    }),

  // 登出
  logout: () =>
    ApiClient.post('/api/auth/logout'),

  // 刷新Token
  refreshToken: (refreshToken: string) =>
    ApiClient.post<RefreshTokenResponse>('/api/auth/refresh', { refresh_token: refreshToken }),

  // 获取用户信息
  getUserInfo: () =>
    ApiClient.get<User>('/api/auth/me'),

  // 获取用户权限（开源版不需要，admin拥有所有权限）
  // getUserPermissions: () =>
  //   ApiClient.get<UserPermissions>('/api/auth/permissions'),

  // 更新用户信息
  updateUserInfo: (data: Partial<User>) =>
    ApiClient.put<User>('/api/auth/me', data),

  // 修改密码
  changePassword: (data: ChangePasswordForm) =>
    ApiClient.post('/api/auth/change-password', data),

  // 重置密码
  resetPassword: (username: string, new_password: string) =>
    ApiClient.post('/api/auth/reset-password', { username, new_password }),

  // 验证邮箱
  verifyEmail: (token: string) =>
    ApiClient.post('/api/auth/verify-email', { token }),

  // 管理员用户管理
  adminListUsers: (params: AdminUserListQuery = {}) =>
    ApiClient.get<AdminUserListData>('/api/auth/users', params),

  adminGetUser: (username: string) =>
    ApiClient.get<AdminUserDetail>(`/api/auth/users/${encodeURIComponent(username)}`),

  adminCreateUser: (data: AdminCreateUserForm) =>
    ApiClient.post('/api/auth/create-user', data),

  adminUpdateUser: (username: string, data: AdminUpdateUserForm) =>
    ApiClient.patch<AdminUserDetail>(`/api/auth/users/${encodeURIComponent(username)}`, data),

  adminUpdateUserStatus: (username: string, is_active: boolean) =>
    ApiClient.patch(`/api/auth/users/${encodeURIComponent(username)}/status`, { is_active }),

  adminUpdateUserRole: (username: string, is_admin: boolean) =>
    ApiClient.patch(`/api/auth/users/${encodeURIComponent(username)}/role`, { is_admin }),

  adminResetPassword: (username: string, new_password: string) =>
    ApiClient.post('/api/auth/reset-password', { username, new_password }),

  adminArchiveUser: (username: string) =>
    ApiClient.delete(`/api/auth/users/${encodeURIComponent(username)}`)
}
