import { beforeEach, describe, expect, it, vi } from 'vitest'
import { createPinia, setActivePinia } from 'pinia'

class LocalStorageMock {
  private values = new Map<string, string>()

  getItem(key: string) {
    return this.values.get(key) ?? null
  }

  setItem(key: string, value: string) {
    this.values.set(key, value)
  }

  removeItem(key: string) {
    this.values.delete(key)
  }

  clear() {
    this.values.clear()
  }
}

vi.mock('element-plus', () => ({
  ElMessage: {
    success: vi.fn(),
    error: vi.fn(),
    warning: vi.fn()
  }
}))

vi.mock('element-plus/theme-chalk/base.css', () => ({}))
vi.mock('element-plus/dist/index.css', () => ({}))
vi.mock('nprogress/nprogress.css', () => ({}))

vi.mock('@vueuse/core', () => ({
  useStorage: (key: string, defaultValue: unknown) => ({
    get value() {
      return globalThis.localStorage?.getItem(key) ?? defaultValue
    },
    set value(next: unknown) {
      if (next === null || next === undefined) {
        globalThis.localStorage?.removeItem(key)
      } else {
        globalThis.localStorage?.setItem(key, String(next))
      }
    }
  })
}))

vi.mock('@/utils/auth', () => ({
  setupTokenRefreshTimer: vi.fn()
}))

vi.mock('@/api/auth', () => ({
  authApi: {
    login: vi.fn(),
    register: vi.fn(),
    logout: vi.fn(),
    refreshToken: vi.fn(),
    getUserInfo: vi.fn(),
    updateUserInfo: vi.fn(),
    changePassword: vi.fn(),
    resetPassword: vi.fn(),
    verifyEmail: vi.fn()
  }
}))

import { authApi } from '@/api/auth'
import { useAuthStore } from '../auth'

const USER_INFO = {
  id: 'u1',
  username: 'alice',
  email: 'alice@example.com',
  is_active: true,
  is_verified: true,
  is_admin: false,
  roles: ['user'],
  created_at: '2026-01-01T00:00:00Z',
  updated_at: '2026-01-01T00:00:00Z',
  preferences: { ui_theme: 'light', language: 'zh-CN' },
  daily_quota: 100,
  concurrent_limit: 3,
  total_analyses: 0,
  successful_analyses: 0,
  failed_analyses: 0
}

describe('auth store tenant safety', () => {
  beforeEach(() => {
    localStorage.clear()
    setActivePinia(createPinia())
    vi.clearAllMocks()
  })

  it('never grants roles from cached local user info', () => {
    localStorage.setItem('auth-token', 'a.b.c')
    localStorage.setItem('refresh-token', 'd.e.f')
    localStorage.setItem('user-info', JSON.stringify({ ...USER_INFO, is_admin: true, roles: ['admin'] }))

    const store = useAuthStore()
    expect(store.isAuthenticated).toBe(true)
    expect(store.isAdmin).toBe(false)
    expect(store.roles).toEqual(['user'])
    expect(store.user?.is_admin).toBe(false)
  })

  it('deduplicates concurrent refresh attempts and restores server user', async () => {
    localStorage.setItem('auth-token', 'a.b.c')
    localStorage.setItem('refresh-token', 'd.e.f')
    localStorage.setItem('user-info', JSON.stringify(USER_INFO))
    vi.mocked(authApi.refreshToken).mockResolvedValue({
      success: true,
      data: { access_token: 'x.y.z', refresh_token: 'u.v.w' },
      message: 'ok'
    })
    vi.mocked(authApi.getUserInfo).mockResolvedValue({
      success: true,
      data: USER_INFO,
      message: 'ok'
    })

    const store = useAuthStore()
    await Promise.all([store.refreshAccessToken(), store.refreshAccessToken()])
    expect(authApi.refreshToken).toHaveBeenCalledTimes(1)
    expect(store.token).toBe('x.y.z')
    expect(store.refreshToken).toBe('u.v.w')
    expect(store.user?.username).toBe('alice')
  })

  it('clears dirty auth state when refresh is rejected by server', async () => {
    localStorage.setItem('auth-token', 'a.b.c')
    localStorage.setItem('refresh-token', 'd.e.f')
    localStorage.setItem('user-info', JSON.stringify(USER_INFO))
    vi.mocked(authApi.refreshToken).mockRejectedValue({
      code: 'ERR_BAD_REQUEST',
      response: { status: 401 }
    })

    const store = useAuthStore()
    await store.refreshAccessToken()
    expect(store.token).toBeNull()
    expect(store.refreshToken).toBeNull()
    expect(store.user).toBeNull()
    expect(localStorage.getItem('user-info')).toBeNull()
  })

  it('logs in, logs out, and changes password through the auth store', async () => {
    vi.mocked(authApi.login).mockResolvedValue({
      success: true,
      data: {
        access_token: 'a.b.c',
        refresh_token: 'd.e.f',
        expires_in: 3600,
        user: { ...USER_INFO, preferences: { ui_theme: 'light', language: 'zh-CN' } }
      },
      message: 'ok'
    })
    vi.mocked(authApi.logout).mockResolvedValue({ success: true, data: {}, message: 'ok' })
    vi.mocked(authApi.changePassword).mockResolvedValue({ success: true, data: {}, message: 'ok' })

    const store = useAuthStore()
    expect(await store.login({ username: 'alice', password: 'StrongPass1' })).toBe(true)
    expect(store.isAuthenticated).toBe(true)
    expect(await store.changePassword('StrongPass1', 'NewStrongPass2')).toBe(true)
    await store.logout()
    expect(store.isAuthenticated).toBe(false)
    expect(store.token).toBeNull()
  })
})
