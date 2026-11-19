export type RouteAccessDecision = 'ok' | 'login' | 'admin'

export interface AuthRouteState {
  isAuthenticated: boolean
  isAdmin: boolean
}

export function resolveRouteAccess(
  state: AuthRouteState,
  requiresAuth: boolean,
  requiresAdmin: boolean
): RouteAccessDecision {
  if (requiresAuth && !state.isAuthenticated) return 'login'
  if (requiresAdmin && !state.isAdmin) return 'admin'
  return 'ok'
}
