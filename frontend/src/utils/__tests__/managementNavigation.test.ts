import { describe, expect, it } from 'vitest'
import { readFileSync } from 'node:fs'
import { fileURLToPath } from 'node:url'
import { dirname, resolve } from 'node:path'
import { resolveRouteAccess } from '../authPolicy'

const __dirname = dirname(fileURLToPath(import.meta.url))
const sidebarSource = readFileSync(
  resolve(__dirname, '../../components/Layout/SidebarMenu.vue'),
  'utf-8'
)
const routerSource = readFileSync(
  resolve(__dirname, '../../router/index.ts'),
  'utf-8'
)
const basicLayoutSource = readFileSync(
  resolve(__dirname, '../../layouts/BasicLayout.vue'),
  'utf-8'
)
const headerActionsSource = readFileSync(
  resolve(__dirname, '../../components/Layout/HeaderActions.vue'),
  'utf-8'
)

const managementPaths = [
  '/settings/config',
  '/settings/cache',
  '/settings/recharges',
  '/evaluation/dashboard',
  '/evolution/proposals',
]

describe('management navigation access', () => {
  it('marks management routes as admin-only', () => {
    managementPaths.forEach((managementPath) => {
      const routePath = managementPath.replace(/^\//, '')
      const start = routerSource.indexOf(`path: '${routePath}'`)
      expect(start).toBeGreaterThan(-1)
      expect(routerSource.slice(start, start + 400)).toContain('requiresAdmin: true')
    })
  })

  it('keeps direct admin URL checks in the shared route policy', () => {
    const normalUser = { isAuthenticated: true, isAdmin: false }
    const admin = { isAuthenticated: true, isAdmin: true }
    managementPaths.forEach(() => {
      expect(resolveRouteAccess(normalUser, true, true)).toBe('admin')
      expect(resolveRouteAccess(admin, true, true)).toBe('ok')
    })
  })

  it('side menu gates admin management groups by role', () => {
    expect(sidebarSource).toContain('v-if="authStore.isAdmin"')
    expect(sidebarSource).toContain('<template v-if="authStore.isAdmin">')
  })

  it('router no longer reads eval/evolution feature enable env vars', () => {
    expect(routerSource).not.toContain('requiresEvalPlatform')
    expect(routerSource).not.toContain('VITE_EVAL_PLATFORM_ENABLED')
    expect(routerSource).not.toContain('VITE_EVOLUTION_ENABLED')
  })

  it('keeps recharge access outside the sidebar main menu', () => {
    expect(sidebarSource).not.toContain('index="/token-recharge"')
    expect(basicLayoutSource).toContain("router.push('/token-recharge')")
    expect(headerActionsSource).toContain("router.push('/token-recharge')")
  })
})
