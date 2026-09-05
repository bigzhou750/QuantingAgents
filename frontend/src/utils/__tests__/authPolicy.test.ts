import { describe, expect, it } from 'vitest'
import { resolveRouteAccess } from '../authPolicy'

describe('route access policy', () => {
  it('redirects visitors to login for protected routes', () => {
    expect(resolveRouteAccess({ isAuthenticated: false, isAdmin: false }, true, false)).toBe('login')
  })

  it('lets normal users into user routes but not admin routes', () => {
    const state = { isAuthenticated: true, isAdmin: false }
    expect(resolveRouteAccess(state, true, false)).toBe('ok')
    expect(resolveRouteAccess(state, true, true)).toBe('admin')
  })

  it('lets admins into admin routes and public routes', () => {
    const state = { isAuthenticated: true, isAdmin: true }
    expect(resolveRouteAccess(state, true, true)).toBe('ok')
    expect(resolveRouteAccess(state, false, false)).toBe('ok')
  })
})
