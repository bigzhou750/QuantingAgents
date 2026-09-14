// 主侧边栏关键功能入口清单（用于测试和可发现性校验）
// 每个 path 对应 SidebarMenu.vue 中的 el-menu-item / el-sub-menu index

export interface SidebarEntry {
  path: string
  label: string
}

export const investmentAssistantEntries: SidebarEntry[] = [
  { path: '/investment', label: '个人投资助手' },
  { path: '/investment/home', label: '新手首页' },
  { path: '/investment/profile', label: '投资画像' },
  { path: '/investment/strategies', label: '策略管理' },
  { path: '/investment/marketplace', label: '策略广场' },
  { path: '/investment/observations', label: '我的观察' },
]

export const evaluationPlatformEntries: SidebarEntry[] = [
  { path: '/evaluation', label: 'Agent 评测' },
  { path: '/evaluation/dashboard', label: '评测概览' },
  { path: '/evaluation/datasets', label: '评测集管理' },
  { path: '/evaluation/runs', label: '评测运行' },
  { path: '/evaluation/trends', label: '质量趋势' },
  { path: '/evaluation/review', label: '人工复核' },
  { path: '/evaluation/bad-cases', label: 'Bad Case 池' },
]

export const selfEvolutionEntries: SidebarEntry[] = [
  { path: '/evolution', label: '自进化' },
  { path: '/evolution/proposals', label: '候选提案' },
  { path: '/evolution/observation', label: '发布后观测' },
  { path: '/evolution/artifacts', label: 'Artifact 管理' },
  { path: '/evolution/online-badcase-config', label: '线上 Bad Case 配置' },
  { path: '/evolution/receipts', label: '进化回执' },
]

export const primaryNavigationPaths = [
  '/dashboard',
  '/research-agent',
  '/analysis',
  '/screening',
  '/favorites',
  '/paper',
]

/**
 * 校验菜单属性值不含非 ASCII 引号等非法字符。
 * 用于防止 index="..." 之类的属性值被写入全角引号导致路由匹配失效。
 */
export function hasInvalidQuoteChars(value: string): boolean {
  return /[“”‘’]/.test(value)
}
