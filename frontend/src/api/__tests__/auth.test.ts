import { beforeEach, describe, expect, it, vi } from 'vitest'
import { ApiClient } from '@/api/request'
import { authApi } from '@/api/auth'

vi.mock('@/api/request', () => ({
  ApiClient: {
    get: vi.fn(),
    post: vi.fn(),
    put: vi.fn(),
    patch: vi.fn(),
    delete: vi.fn()
  }
}))

describe('auth admin API', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    vi.mocked(ApiClient.get).mockResolvedValue({ success: true, data: {}, message: '' })
    vi.mocked(ApiClient.post).mockResolvedValue({ success: true, data: {}, message: '' })
    vi.mocked(ApiClient.patch).mockResolvedValue({ success: true, data: {}, message: '' })
    vi.mocked(ApiClient.delete).mockResolvedValue({ success: true, data: {}, message: '' })
  })

  it('lists users with query params', async () => {
    await authApi.adminListUsers({ keyword: 'bob', status: 'active', skip: 0, limit: 20 })
    expect(ApiClient.get).toHaveBeenCalledWith('/api/auth/users', {
      keyword: 'bob',
      status: 'active',
      skip: 0,
      limit: 20
    })
  })

  it('wraps user lifecycle operations with the expected endpoints', async () => {
    await authApi.adminGetUser('bob')
    await authApi.adminCreateUser({ username: 'bob', email: 'bob@example.com', password: 'StrongPass1', is_admin: false })
    await authApi.adminUpdateUser('bob', { email: 'new@example.com', daily_quota: 500, concurrent_limit: 5 })
    await authApi.adminUpdateUserStatus('bob', false)
    await authApi.adminUpdateUserRole('bob', true)
    await authApi.adminResetPassword('bob', 'StrongPass2')
    await authApi.adminArchiveUser('bob')

    expect(ApiClient.get).toHaveBeenCalledWith('/api/auth/users/bob')
    expect(ApiClient.post).toHaveBeenCalledWith('/api/auth/create-user', {
      username: 'bob',
      email: 'bob@example.com',
      password: 'StrongPass1',
      is_admin: false
    })
    expect(ApiClient.patch).toHaveBeenCalledWith('/api/auth/users/bob', {
      email: 'new@example.com',
      daily_quota: 500,
      concurrent_limit: 5
    })
    expect(ApiClient.patch).toHaveBeenCalledWith('/api/auth/users/bob/status', { is_active: false })
    expect(ApiClient.patch).toHaveBeenCalledWith('/api/auth/users/bob/role', { is_admin: true })
    expect(ApiClient.post).toHaveBeenCalledWith('/api/auth/reset-password', { username: 'bob', new_password: 'StrongPass2' })
    expect(ApiClient.delete).toHaveBeenCalledWith('/api/auth/users/bob')
  })
})
