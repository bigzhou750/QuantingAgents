// @vitest-environment happy-dom

import { beforeEach, describe, expect, it, vi } from 'vitest'
import { flushPromises } from '@vue/test-utils'
import { authApi } from '@/api/auth'
import type { AdminUserSummary } from '@/types/auth'

vi.mock('@/api/auth', () => ({
  authApi: {
    adminListUsers: vi.fn(),
    adminGetUser: vi.fn(),
    adminCreateUser: vi.fn(),
    adminUpdateUser: vi.fn(),
    adminUpdateUserStatus: vi.fn(),
    adminUpdateUserRole: vi.fn(),
    adminResetPassword: vi.fn(),
    adminArchiveUser: vi.fn()
  }
}))

vi.mock('@/stores/auth', () => ({
  useAuthStore: () => ({
    user: { username: 'admin' }
  })
}))

const USER: AdminUserSummary = {
  id: 'u1',
  username: 'bob',
  email: 'bob@example.com',
  is_active: true,
  is_verified: true,
  is_admin: false,
  is_archived: false,
  created_at: '2026-09-06T00:00:00Z',
  last_login: null,
  preferences: {
    default_market: 'A股',
    default_depth: '3',
    ui_theme: 'light',
    language: 'zh-CN',
    notifications_enabled: true,
    email_notifications: false
  },
  daily_quota: 1000,
  concurrent_limit: 3,
  total_analyses: 0,
  successful_analyses: 0,
  failed_analyses: 0
}

describe('UserManagement.vue', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  const mountPage = async () => {
    vi.stubGlobal('navigator', { userAgent: 'vitest' })
    class Observer {
      observe() {}
      disconnect() {}
      unobserve() {}
      takeRecords() {
        return []
      }
    }
    vi.stubGlobal('MutationObserver', Observer)
    vi.stubGlobal('ResizeObserver', Observer)
    const ElementPlus = (await import('element-plus')).default
    const { mount } = await import('@vue/test-utils')
    const { default: UserManagement } = await import('../UserManagement.vue')
    const wrapper = mount(UserManagement, {
      global: {
        plugins: [ElementPlus],
        stubs: {
          ElDialog: {
            template: '<div><slot /></div>'
          }
        }
      }
    })
    await flushPromises()
    return wrapper
  }

  it('renders the account list after loading', async () => {
    vi.mocked(authApi.adminListUsers).mockResolvedValue({
      success: true,
      data: { users: [USER], total: 1, skip: 0, limit: 20 },
      message: ''
    })

    const wrapper = await mountPage()

    expect(wrapper.text()).toContain('用户管理')
    expect(wrapper.text()).toContain('bob')
    expect(wrapper.text()).toContain('bob@example.com')
    expect(wrapper.text()).toContain('普通用户')
  })

  it('shows an empty state when no accounts match', async () => {
    vi.mocked(authApi.adminListUsers).mockResolvedValue({
      success: true,
      data: { users: [], total: 0, skip: 0, limit: 20 },
      message: ''
    })

    const wrapper = await mountPage()

    expect(wrapper.text()).toContain('暂无符合条件的账号')
  })

  it('shows account detail without exposing credentials', async () => {
    vi.mocked(authApi.adminListUsers).mockResolvedValue({
      success: true,
      data: { users: [USER], total: 1, skip: 0, limit: 20 },
      message: ''
    })
    vi.mocked(authApi.adminGetUser).mockResolvedValue({
      success: true,
      data: { ...USER, updated_at: '2026-09-06T10:00:00Z' },
      message: ''
    })

    const wrapper = await mountPage()
    const detailButton = wrapper.findAll('button').find((button) => button.text().includes('详情'))
    await detailButton?.trigger('click')
    await flushPromises()

    expect(wrapper.text()).toContain('bob@example.com')
    expect(wrapper.text()).not.toContain('hashed_password')
    expect(wrapper.text()).not.toContain('access_token')
  })

  it('opens the create dialog with required fields', async () => {
    vi.mocked(authApi.adminListUsers).mockResolvedValue({
      success: true,
      data: { users: [], total: 0, skip: 0, limit: 20 },
      message: ''
    })

    const wrapper = await mountPage()
    const createButton = wrapper.findAll('button').find((button) => button.text().includes('创建用户'))
    await createButton?.trigger('click')
    await flushPromises()

    expect(wrapper.find('input[placeholder="3-50 位用户名"]').exists()).toBe(true)
    expect(wrapper.find('input[placeholder="user@example.com"]').exists()).toBe(true)
    expect(wrapper.find('input[placeholder="至少 8 位，包含字母和数字"]').exists()).toBe(true)
  })
})
