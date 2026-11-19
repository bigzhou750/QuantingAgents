import { createRouter, createWebHistory } from 'vue-router'
import type { RouteRecordRaw } from 'vue-router'
import { nextTick } from 'vue'
import { useAuthStore } from '@/stores/auth'
import { useAppStore } from '@/stores/app'
import { ElMessage } from 'element-plus'
import { resolveRouteAccess } from '@/utils/authPolicy'

// 路由配置
// 所有需要布局的页面统一放在一个 BasicLayout 下，避免切换菜单时重建侧边栏和顶栏
const routes: RouteRecordRaw[] = [
  // ==================== 无布局路由 ====================
  {
    path: '/login',
    name: 'Login',
    component: () => import('@/views/Auth/Login.vue'),
    meta: {
      title: '登录',
      hideInMenu: true,
      transition: 'fade'
    }
  },
  {
    path: '/register',
    name: 'Register',
    component: () => import('@/views/Auth/Register.vue'),
    meta: { title: '注册', hideInMenu: true, transition: 'fade' }
  },
  {
    path: '/',
    name: 'Home',
    component: () => import('@/views/About/index.vue'),
    alias: '/about',
    meta: {
      title: '智能投研助手',
      hideInMenu: true,
      requiresAuth: false,
      transition: 'fade'
    }
  },
  {
    path: '/pricing',
    name: 'Pricing',
    component: () => import('@/views/Public/Pricing.vue'),
    meta: { title: '定价说明', hideInMenu: true, requiresAuth: false, transition: 'fade' }
  },
  {
    path: '/privacy',
    name: 'Privacy',
    component: () => import('@/views/Public/Privacy.vue'),
    meta: { title: '隐私政策', hideInMenu: true, requiresAuth: false, transition: 'fade' }
  },
  {
    path: '/terms',
    name: 'Terms',
    component: () => import('@/views/Public/Terms.vue'),
    meta: { title: '服务条款', hideInMenu: true, requiresAuth: false, transition: 'fade' }
  },
  // 兼容文档链接
  {
    path: '/paper/:name.md',
    name: 'PaperMdRedirect',
    redirect: (to) => `/learning/article/${to.params.name as string}`,
    meta: { title: '文档跳转', hideInMenu: true, requiresAuth: false }
  },
  // 重定向
  { path: '/queue', redirect: '/tasks' },
  { path: '/analysis/history', redirect: '/tasks?tab=completed' },

  // ==================== 统一布局路由 ====================
  {
    path: '/',
    component: () => import('@/layouts/BasicLayout.vue'),
    children: [
      // 根路径重定向
      { path: '', redirect: '/dashboard' },

      // ---------- 工作台 ----------
      {
        path: 'dashboard',
        name: 'DashboardHome',
        component: () => import('@/views/Dashboard/index.vue'),
        meta: {
          title: '工作台',
          icon: 'Dashboard',
          requiresAuth: true,
          transition: 'fade'
        }
      },

      // ---------- 股票分析 ----------
      {
        path: 'analysis',
        redirect: '/analysis/single'
      },
      {
        path: 'analysis/single',
        name: 'SingleAnalysis',
        component: () => import('@/views/Analysis/SingleAnalysis.vue'),
        meta: {
          title: '单股分析',
          requiresAuth: true,
          transition: 'fade'
        }
      },
      {
        path: 'analysis/batch',
        name: 'BatchAnalysis',
        component: () => import('@/views/Analysis/BatchAnalysis.vue'),
        meta: {
          title: '批量分析',
          requiresAuth: true,
          transition: 'fade'
        }
      },

      // ---------- 选股器 ----------
      {
        path: 'screening',
        name: 'StockScreeningHome',
        component: () => import('@/views/Screening/index.vue'),
        meta: {
          title: '选股器',
          icon: 'Search',
          requiresAuth: true,
          transition: 'slide-up'
        }
      },

      // ---------- 自选股 ----------
      {
        path: 'favorites',
        name: 'FavoritesHome',
        component: () => import('@/views/Favorites/index.vue'),
        meta: {
          title: '自选股',
          icon: 'Star',
          requiresAuth: true,
          transition: 'slide-up'
        }
      },

      // ---------- 学习中心 ----------
      {
        path: 'learning',
        name: 'LearningHome',
        component: () => import('@/views/Learning/index.vue'),
        meta: {
          title: '学习中心',
          icon: 'Reading',
          requiresAuth: false,
          transition: 'fade'
        }
      },
      {
        path: 'learning/:category',
        name: 'LearningCategory',
        component: () => import('@/views/Learning/Category.vue'),
        meta: {
          title: '学习分类',
          requiresAuth: false,
          transition: 'fade'
        }
      },
      {
        path: 'learning/article/:id',
        name: 'LearningArticle',
        component: () => import('@/views/Learning/Article.vue'),
        meta: {
          title: '文章详情',
          requiresAuth: false,
          transition: 'fade'
        }
      },

      // ---------- 股票详情 ----------
      {
        path: 'stocks/:code',
        name: 'StockDetail',
        component: () => import('@/views/Stocks/Detail.vue'),
        meta: {
          title: '股票详情',
          icon: 'TrendCharts',
          requiresAuth: true,
          hideInMenu: true,
          transition: 'fade'
        }
      },

      // ---------- 分析任务 ----------
      {
        path: 'tasks',
        name: 'TaskCenterHome',
        component: () => import('@/views/Tasks/TaskCenter.vue'),
        meta: {
          title: '分析任务',
          icon: 'List',
          requiresAuth: true,
          transition: 'slide-up'
        }
      },

      // ---------- AI 研究 ----------
      {
        path: 'research-agent',
        name: 'ResearchAgentHome',
        component: () => import('@/views/VibeAgent/index.vue'),
        meta: {
          title: 'AI 研究',
          icon: 'ChatDotRound',
          requiresAuth: true,
          transition: 'fade'
        }
      },

      // ---------- 个人投资助手 ----------
      {
        path: 'investment',
        redirect: '/investment/home'
      },
      {
        path: 'investment/home',
        name: 'InvestmentHome',
        component: () => import('@/views/PersonalInvestment/Home.vue'),
        meta: {
          title: '新手首页',
          requiresAuth: true,
          transition: 'slide-up'
        }
      },
      {
        path: 'investment/profile',
        name: 'InvestmentProfile',
        component: () => import('@/views/PersonalInvestment/Profile.vue'),
        meta: {
          title: '投资画像',
          requiresAuth: true,
          transition: 'slide-up'
        }
      },
      {
        path: 'investment/strategies',
        name: 'StrategyManagement',
        component: () => import('@/views/PersonalInvestment/Strategies.vue'),
        meta: {
          title: '策略管理',
          requiresAuth: true,
          transition: 'slide-up'
        }
      },
      {
        path: 'investment/marketplace',
        name: 'StrategyMarketplace',
        component: () => import('@/views/PersonalInvestment/Marketplace.vue'),
        meta: {
          title: '策略广场',
          requiresAuth: true,
          transition: 'slide-up'
        }
      },
      {
        path: 'investment/marketplace/:templateId',
        name: 'MarketplaceDetail',
        component: () => import('@/views/PersonalInvestment/MarketplaceDetail.vue'),
        meta: {
          title: '策略详情',
          requiresAuth: true,
          hideInMenu: true,
          transition: 'slide-up'
        }
      },
      {
        path: 'investment/observations',
        name: 'MyObservations',
        component: () => import('@/views/PersonalInvestment/Observations.vue'),
        meta: {
          title: '我的观察',
          requiresAuth: true,
          transition: 'slide-up'
        }
      },
      {
        path: 'investment/screening/:taskId?',
        name: 'ScreeningResults',
        component: () => import('@/views/PersonalInvestment/ScreeningResults.vue'),
        meta: {
          title: '选股结果',
          requiresAuth: true,
          hideInMenu: true,
          transition: 'slide-up'
        }
      },
      {
        path: 'investment/checkup/:taskId?',
        name: 'CheckupResults',
        component: () => import('@/views/PersonalInvestment/CheckupResults.vue'),
        meta: {
          title: '体检结果',
          requiresAuth: true,
          hideInMenu: true,
          transition: 'slide-up'
        }
      },

      // ---------- 新闻关注 ----------
      {
        path: 'news-watch',
        redirect: '/news-watch/workbench'
      },
      {
        path: 'news-watch/workbench',
        name: 'NewsWatchWorkbench',
        component: () => import('@/views/NewsWatch/Workbench.vue'),
        meta: {
          title: '关注工作台',
          requiresAuth: true,
          transition: 'slide-up'
        }
      },
      {
        path: 'news-watch/impact',
        name: 'NewsImpactAnalysis',
        component: () => import('@/views/NewsWatch/ImpactAnalysis.vue'),
        meta: {
          title: '持仓影响分析',
          requiresAuth: true,
          transition: 'slide-up'
        }
      },
      {
        path: 'news-watch/alerts',
        name: 'NewsAlertConfig',
        component: () => import('@/views/NewsWatch/AlertConfig.vue'),
        meta: {
          title: '告警配置',
          requiresAuth: true,
          transition: 'slide-up'
        }
      },
      {
        path: 'news-watch/events',
        name: 'NewsEventAnalysis',
        component: () => import('@/views/NewsWatch/EventAnalysis.vue'),
        meta: {
          title: '事件分析',
          requiresAuth: true,
          transition: 'slide-up'
        }
      },
      {
        path: 'news-watch/closed-loop',
        name: 'NewsClosedLoop',
        component: () => import('@/views/NewsWatch/ClosedLoop.vue'),
        meta: {
          title: '闭环复盘',
          requiresAuth: true,
          transition: 'slide-up'
        }
      },

      // ---------- 分析报告 ----------
      {
        path: 'reports',
        name: 'ReportsHome',
        component: () => import('@/views/Reports/index.vue'),
        meta: {
          title: '分析报告',
          icon: 'Document',
          requiresAuth: true,
          transition: 'fade'
        }
      },
      {
        path: 'reports/view/:id',
        name: 'ReportDetail',
        component: () => import('@/views/Reports/ReportDetail.vue'),
        meta: {
          title: '报告详情',
          requiresAuth: true,
          transition: 'fade'
        }
      },
      {
        path: 'reports/token',
        name: 'TokenStatistics',
        component: () => import('@/views/Reports/TokenStatistics.vue'),
        meta: {
          title: 'Token统计',
          requiresAuth: true,
          transition: 'fade'
        }
      },

      // ---------- 设置 ----------
      {
        path: 'settings',
        name: 'SettingsHome',
        component: () => import('@/views/Settings/index.vue'),
        meta: {
          title: '设置',
          icon: 'Setting',
          requiresAuth: true,
          transition: 'slide-left'
        }
      },
      {
        path: 'settings/config',
        name: 'ConfigManagement',
        component: () => import('@/views/Settings/ConfigManagement.vue'),
        meta: {
          title: '配置管理',
          requiresAuth: true,
          requiresAdmin: true,
          transition: 'slide-left'
        }
      },
      {
        path: 'settings/database',
        name: 'DatabaseManagement',
        component: () => import('@/views/System/DatabaseManagement.vue'),
        meta: {
          title: '数据库管理',
          requiresAuth: true,
          requiresAdmin: true,
          transition: 'slide-left'
        }
      },
      {
        path: 'settings/logs',
        name: 'OperationLogs',
        component: () => import('@/views/System/OperationLogs.vue'),
        meta: {
          title: '操作日志',
          requiresAuth: true,
          requiresAdmin: true,
          transition: 'slide-left'
        }
      },
      {
        path: 'settings/system-logs',
        name: 'LogManagement',
        component: () => import('@/views/System/LogManagement.vue'),
        meta: {
          title: '系统日志',
          requiresAuth: true,
          requiresAdmin: true,
          transition: 'slide-left'
        }
      },
      {
        path: 'settings/sync',
        name: 'MultiSourceSync',
        component: () => import('@/views/System/MultiSourceSync.vue'),
        meta: {
          title: '多数据源同步',
          requiresAuth: true,
          requiresAdmin: true,
          transition: 'slide-left'
        }
      },
      {
        path: 'settings/cache',
        name: 'CacheManagement',
        component: () => import('@/views/Settings/CacheManagement.vue'),
        meta: {
          title: '缓存管理',
          requiresAuth: true,
          requiresAdmin: true,
          transition: 'slide-left'
        }
      },
      {
        path: 'settings/usage',
        name: 'UsageStatistics',
        component: () => import('@/views/Settings/UsageStatistics.vue'),
        meta: {
          title: '使用统计',
          requiresAuth: true,
          requiresAdmin: true,
          transition: 'slide-left'
        }
      },
      {
        path: 'settings/users',
        name: 'UserManagement',
        component: () => import('@/views/System/UserManagement.vue'),
        meta: {
          title: '用户管理',
          requiresAuth: true,
          requiresAdmin: true,
          transition: 'slide-left'
        }
      },
      {
        path: 'settings/scheduler',
        name: 'SchedulerManagement',
        component: () => import('@/views/System/SchedulerManagement.vue'),
        meta: {
          title: '定时任务',
          requiresAuth: true,
          requiresAdmin: true,
          transition: 'slide-left'
        }
      },
      {
        path: 'settings/billing',
        name: 'BillingConfig',
        component: () => import('@/views/Settings/BillingConfig.vue'),
        meta: {
          title: '计费配置',
          requiresAuth: true,
          requiresAdmin: true,
          transition: 'slide-left'
        }
      },
      {
        path: 'settings/recharges',
        name: 'RechargeManagement',
        component: () => import('@/views/System/RechargeManagement.vue'),
        meta: {
          title: '充值记录',
          requiresAuth: true,
          requiresAdmin: true,
          transition: 'slide-left'
        }
      },

      // ---------- 算力充值 ----------
      {
        path: 'token-recharge',
        name: 'TokenRechargeHome',
        component: () => import('@/views/TokenRecharge/index.vue'),
        meta: {
          title: '算力充值',
          icon: 'Wallet',
          requiresAuth: true,
          transition: 'fade'
        }
      },
      {
        path: 'token-recharge/transactions',
        name: 'TokenTransactions',
        component: () => import('@/views/TokenRecharge/Transactions.vue'),
        meta: {
          title: '交易明细',
          requiresAuth: true,
          transition: 'fade'
        }
      },

      // ---------- Agent 评测平台 ----------
      {
        path: 'evaluation',
        redirect: '/evaluation/dashboard'
      },
      {
        path: 'evaluation/dashboard',
        name: 'EvaluationDashboard',
        component: () => import('@/views/Evaluation/index.vue'),
        meta: {
          title: '评测概览',
          requiresAuth: true,
          requiresAdmin: true,
          transition: 'fade'
        }
      },
      {
        path: 'evaluation/decision-audit',
        name: 'DecisionAudit',
        component: () => import('@/views/Evaluation/DecisionAudit.vue'),
        meta: {
          title: '决策审计',
          requiresAuth: true,
          requiresAdmin: true,
          transition: 'fade'
        }
      },
      {
        path: 'evaluation/datasets',
        name: 'EvalDatasets',
        component: () => import('@/views/Evaluation/Datasets.vue'),
        meta: {
          title: '评测集管理',
          requiresAuth: true,
          requiresAdmin: true,
          transition: 'fade'
        }
      },
      {
        path: 'evaluation/runs',
        name: 'EvalRuns',
        component: () => import('@/views/Evaluation/Runs.vue'),
        meta: {
          title: '评测运行',
          requiresAuth: true,
          requiresAdmin: true,
          transition: 'fade'
        }
      },
      {
        path: 'evaluation/runs/create',
        name: 'EvalRunCreate',
        component: () => import('@/views/Evaluation/RunCreate.vue'),
        meta: {
          title: '新建评测运行',
          requiresAuth: true,
          requiresAdmin: true,
          hideInMenu: true,
          transition: 'fade'
        }
      },
      {
        path: 'evaluation/runs/compare',
        name: 'EvalRunCompare',
        component: () => import('@/views/Evaluation/RunCompare.vue'),
        meta: {
          title: '运行对比',
          requiresAuth: true,
          requiresAdmin: true,
          hideInMenu: true,
          transition: 'fade'
        }
      },
      {
        path: 'evaluation/runs/:id',
        name: 'EvalRunDetail',
        component: () => import('@/views/Evaluation/RunDetail.vue'),
        meta: {
          title: '评测运行详情',
          requiresAuth: true,
          requiresAdmin: true,
          hideInMenu: true,
          transition: 'fade'
        }
      },
      {
        path: 'evaluation/runs/:id/report',
        name: 'EvalRunReport',
        component: () => import('@/views/Evaluation/RunReport.vue'),
        meta: {
          title: '评测报告',
          requiresAuth: true,
          requiresAdmin: true,
          hideInMenu: true,
          transition: 'fade'
        }
      },
      {
        path: 'evaluation/datasets/:id',
        name: 'EvalDatasetDetail',
        component: () => import('@/views/Evaluation/DatasetDetail.vue'),
        meta: {
          title: '评测集详情',
          requiresAuth: true,
          requiresAdmin: true,
          hideInMenu: true,
          transition: 'fade'
        }
      },
      {
        path: 'evaluation/review',
        name: 'EvalHumanReview',
        component: () => import('@/views/Evaluation/HumanReview.vue'),
        meta: {
          title: '人工复核',
          requiresAuth: true,
          requiresAdmin: true,
          transition: 'fade'
        }
      },
      {
        path: 'evaluation/bad-cases',
        name: 'EvalBadCases',
        component: () => import('@/views/Evaluation/BadCases.vue'),
        meta: {
          title: 'Bad Case 池',
          requiresAuth: true,
          requiresAdmin: true,
          transition: 'fade'
        }
      },
      {
        path: 'evaluation/trends',
        name: 'EvalTrends',
        component: () => import('@/views/Evaluation/Trends.vue'),
        meta: {
          title: '质量趋势',
          requiresAuth: true,
          requiresAdmin: true,
          transition: 'fade'
        }
      },

      // ---------- Agent 自进化 ----------
      {
        path: 'evolution',
        redirect: '/evolution/proposals'
      },
      {
        path: 'evolution/proposals',
        name: 'EvolutionProposals',
        component: () => import('@/views/Evolution/Proposals.vue'),
        meta: {
          title: '候选提案',
          requiresAuth: true,
          requiresAdmin: true,
          transition: 'fade'
        }
      },
      {
        path: 'evolution/proposals/:id',
        name: 'EvolutionProposalDetail',
        component: () => import('@/views/Evolution/ProposalDetail.vue'),
        meta: {
          title: '提案详情',
          requiresAuth: true,
          requiresAdmin: true,
          hideInMenu: true,
          transition: 'fade'
        }
      },
      {
        path: 'evolution/observation',
        name: 'EvolutionPostReleaseObservation',
        component: () => import('@/views/Evolution/PostReleaseObservation.vue'),
        meta: {
          title: '发布后观测',
          requiresAuth: true,
          requiresAdmin: true,
          transition: 'fade'
        }
      },
      {
        path: 'evolution/artifacts',
        name: 'EvolutionArtifacts',
        component: () => import('@/views/Evolution/Artifacts.vue'),
        meta: {
          title: 'Artifact 管理',
          requiresAuth: true,
          requiresAdmin: true,
          transition: 'fade'
        }
      },
      {
        path: 'evolution/online-badcase-config',
        name: 'EvolutionOnlineBadcaseConfig',
        component: () => import('@/views/Evolution/OnlineBadcaseConfig.vue'),
        meta: {
          title: '线上 Bad Case 配置',
          requiresAuth: true,
          requiresAdmin: true,
          transition: 'fade'
        }
      },
      {
        path: 'evolution/receipts',
        name: 'EvolutionReceipts',
        component: () => import('@/views/Evolution/Receipts.vue'),
        meta: {
          title: '进化回执',
          requiresAuth: true,
          requiresAdmin: true,
          transition: 'fade'
        }
      },

      // ---------- 模拟交易 ----------
      {
        path: 'paper',
        name: 'PaperTradingHome',
        component: () => import('@/views/PaperTrading/index.vue'),
        meta: {
          title: '模拟交易',
          icon: 'CreditCard',
          requiresAuth: true,
          transition: 'slide-up'
        }
      }
    ]
  },

  // ==================== 404 ====================
  {
    path: '/:pathMatch(.*)*',
    name: 'NotFound',
    component: () => import('@/views/Error/404.vue'),
    meta: {
      title: '页面不存在',
      hideInMenu: true,
      requiresAuth: true
    }
  }
]

// 创建路由实例
const router = createRouter({
  history: createWebHistory(import.meta.env.BASE_URL),
  routes,
  scrollBehavior(_to, _from, savedPosition) {
    if (savedPosition) {
      return savedPosition
    } else {
      return { top: 0 }
    }
  }
})

// 全局前置守卫
router.beforeEach(async (to, _from, next) => {
  const authStore = useAuthStore()
  const appStore = useAppStore()

  // 设置页面标题
  const title = to.meta.title as string
  if (title) {
    document.title = `${title} - 智能投研助手`
  }

  console.log(' 路由守卫检查:', {
    path: to.fullPath,
    name: to.name,
    requiresAuth: to.meta.requiresAuth,
    isAuthenticated: authStore.isAuthenticated,
    hasToken: !!authStore.token
  })

  // A cached token may establish a provisional session, but never a role.
  // Resolve identity from the server before protected navigation.
  if (authStore.isAuthenticated && !authStore.user) {
    try {
      await authStore.checkAuthStatus()
    } catch {
      authStore.clearAuthInfo()
    }
  }

  // 检查是否需要认证
  if (to.meta.requiresAuth && !authStore.isAuthenticated) {
    console.log('🔒 需要认证但用户未登录:', {
      path: to.fullPath,
      requiresAuth: to.meta.requiresAuth,
      isAuthenticated: authStore.isAuthenticated,
      token: authStore.token ? '存在' : '不存在'
    })
    // 保存原始路径，登录后跳转
    authStore.setRedirectPath(to.fullPath)
    next('/login')
    return
  }

  if (to.meta.requiresAdmin && authStore.isAuthenticated && !authStore.isAdmin) {
    await authStore.fetchUserPermissions()
  }

  const access = resolveRouteAccess(
    { isAuthenticated: authStore.isAuthenticated, isAdmin: authStore.isAdmin },
    Boolean(to.meta.requiresAuth),
    Boolean(to.meta.requiresAdmin)
  )

  if (access === 'login') {
    authStore.setRedirectPath(to.fullPath)
    next('/login')
    return
  }

  if (access === 'admin') {
    ElMessage.warning('需要管理员权限')
    next('/dashboard')
    return
  }

  // 管理员权限校验
  if (to.meta.requiresAdmin && !authStore.isAdmin) {
    ElMessage.error('需要管理员权限')
    next('/dashboard')
    return
  }

  // 如果已登录且访问登录页，重定向到仪表板
  if (authStore.isAuthenticated && to.name === 'Login') {
    next('/dashboard')
    return
  }

  // 更新当前路由信息
  appStore.setCurrentRoute(to)

  next()
})

// 全局后置守卫
router.afterEach((_to, _from) => {
  // 页面切换后的处理
  nextTick(() => {
    // 可以在这里添加页面分析、埋点等逻辑
  })
})

// 路由错误处理
router.onError((error) => {
  console.error('路由错误:', error)
  ElMessage.error('页面加载失败，请重试')
})

export default router

// 导出路由配置供其他地方使用
export { routes }
