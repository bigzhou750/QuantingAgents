import { createRouter, createWebHistory } from 'vue-router'
import type { RouteRecordRaw } from 'vue-router'
import { nextTick } from 'vue'
import { useAuthStore } from '@/stores/auth'
import { useAppStore } from '@/stores/app'
import { ElMessage } from 'element-plus'
import NProgress from 'nprogress'
import 'nprogress/nprogress.css'

// 配置NProgress
NProgress.configure({
  showSpinner: false,
  minimum: 0.2,
  easing: 'ease',
  speed: 500
})

// 路由配置
const routes: RouteRecordRaw[] = [
  {
    path: '/',
    redirect: '/dashboard'
  },
  // 兼容文档链接：将 /paper/<name>.md 重定向到学习中心文章路由
  {
    path: '/paper/:name.md',
    name: 'PaperMdRedirect',
    redirect: (to) => `/learning/article/${to.params.name as string}`,
    meta: { title: '文档跳转', hideInMenu: true, requiresAuth: false }
  },
  {
    path: '/dashboard',
    name: 'Dashboard',
    component: () => import('@/layouts/BasicLayout.vue'),
    meta: {
      title: '工作台',
      icon: 'Dashboard',
      requiresAuth: true,
      transition: 'fade'
    },
    children: [
      {
        path: '',
        name: 'DashboardHome',
        component: () => import('@/views/Dashboard/index.vue'),
        meta: {
          title: '工作台',
          requiresAuth: true
        }
      }
    ]
  },
  {
    path: '/analysis',
    name: 'Analysis',
    component: () => import('@/layouts/BasicLayout.vue'),
    redirect: '/analysis/single',
    children: [
      {
        path: 'single',
        name: 'SingleAnalysis',
        component: () => import('@/views/Analysis/SingleAnalysis.vue')
      },
      {
        path: 'batch',
        name: 'BatchAnalysis',
        component: () => import('@/views/Analysis/BatchAnalysis.vue')
      },

    ]
  },
  {
    path: '/screening',
    name: 'StockScreening',
    component: () => import('@/layouts/BasicLayout.vue'),
    meta: {
      title: '选股器',
      icon: 'Search',
      requiresAuth: true,
      transition: 'slide-up'
    },
    children: [
      {
        path: '',
        name: 'StockScreeningHome',
        component: () => import('@/views/Screening/index.vue'),
        meta: {
          title: '选股器',
          requiresAuth: true
        }
      }
    ]
  },

  {
    path: '/favorites',
    name: 'Favorites',
    component: () => import('@/layouts/BasicLayout.vue'),
    meta: {
      title: '自选股',
      icon: 'Star',
      requiresAuth: true,
      transition: 'slide-up'
    },
    children: [
      {
        path: '',
        name: 'FavoritesHome',
        component: () => import('@/views/Favorites/index.vue'),
        meta: {
          title: '自选股',
          requiresAuth: true
        }
      }
    ]
  },
  {
    path: '/learning',
    name: 'Learning',
    component: () => import('@/layouts/BasicLayout.vue'),
    meta: {
      title: '学习中心',
      icon: 'Reading',
      requiresAuth: false,
      transition: 'fade'
    },
    children: [
      {
        path: '',
        name: 'LearningHome',
        component: () => import('@/views/Learning/index.vue'),
        meta: {
          title: '学习中心',
          requiresAuth: false
        }
      },
      {
        path: ':category',
        name: 'LearningCategory',
        component: () => import('@/views/Learning/Category.vue'),
        meta: {
          title: '学习分类',
          requiresAuth: false
        }
      },
      {
        path: 'article/:id',
        name: 'LearningArticle',
        component: () => import('@/views/Learning/Article.vue'),
        meta: {
          title: '文章详情',
          requiresAuth: false
        }
      }
    ]
  },
  {
    path: '/stocks',
    name: 'Stocks',
    component: () => import('@/layouts/BasicLayout.vue'),
    meta: {
      title: '股票详情',
      icon: 'TrendCharts',
      requiresAuth: true,
      hideInMenu: true,
      transition: 'fade'
    },
    children: [
      {
        path: ':code',
        name: 'StockDetail',
        component: () => import('@/views/Stocks/Detail.vue'),
        meta: {
          title: '股票详情',
          requiresAuth: true,
          hideInMenu: true,
          transition: 'fade'
        }
      }
    ]
  },


  {
    path: '/tasks',
    name: 'TaskCenter',
    component: () => import('@/layouts/BasicLayout.vue'),
    meta: {
      title: '分析任务',
      icon: 'List',
      requiresAuth: true,
      transition: 'slide-up'
    },
    children: [
      {
        path: '',
        name: 'TaskCenterHome',
        component: () => import('@/views/Tasks/TaskCenter.vue'),
        meta: { title: '任务中心', requiresAuth: true }
      }
    ]
  },
  {
    path: '/research-agent',
    name: 'ResearchAgent',
    component: () => import('@/layouts/BasicLayout.vue'),
    meta: {
      title: 'AI 研究',
      icon: 'ChatDotRound',
      requiresAuth: true,
      transition: 'fade'
    },
    children: [
      {
        path: '',
        name: 'ResearchAgentHome',
        component: () => import('@/views/VibeAgent/index.vue'),
        meta: { title: '自然语言研究', requiresAuth: true }
      }
    ]
  },
  { path: '/queue', redirect: '/tasks' },
  { path: '/analysis/history', redirect: '/tasks?tab=completed' },
  {
    path: '/reports',
    name: 'Reports',
    component: () => import('@/layouts/BasicLayout.vue'),
    meta: {
      title: '分析报告',
      icon: 'Document',
      requiresAuth: true,
      transition: 'fade'
    },
    children: [
      {
        path: '',
        name: 'ReportsHome',
        component: () => import('@/views/Reports/index.vue'),
        meta: {
          title: '分析报告',
          requiresAuth: true
        }
      },
      {
        path: 'view/:id',
        name: 'ReportDetail',
        component: () => import('@/views/Reports/ReportDetail.vue'),
        meta: {
          title: '报告详情',
          requiresAuth: true
        }
      },
      {
        path: 'token',
        name: 'TokenStatistics',
        component: () => import('@/views/Reports/TokenStatistics.vue'),
        meta: {
          title: 'Token统计',
          requiresAuth: true
        }
      }
    ]
  },
  {
    path: '/settings',
    name: 'Settings',
    component: () => import('@/layouts/BasicLayout.vue'),
    meta: {
      title: '设置',
      icon: 'Setting',
      requiresAuth: true,
      transition: 'slide-left'
    },
    children: [
      {
        path: '',
        name: 'SettingsHome',
        component: () => import('@/views/Settings/index.vue'),
        meta: {
          title: '设置',
          requiresAuth: true
        }
      },
      {
        path: 'config',
        name: 'ConfigManagement',
        component: () => import('@/views/Settings/ConfigManagement.vue'),
        meta: {
          title: '配置管理',
          requiresAuth: true
        }
      },
      {
        path: 'database',
        name: 'DatabaseManagement',
        component: () => import('@/views/System/DatabaseManagement.vue'),
        meta: {
          title: '数据库管理',
          requiresAuth: true
        }
      },
      {
        path: 'logs',
        name: 'OperationLogs',
        component: () => import('@/views/System/OperationLogs.vue'),
        meta: {
          title: '操作日志',
          requiresAuth: true
        }
      },
      {
        path: 'system-logs',
        name: 'LogManagement',
        component: () => import('@/views/System/LogManagement.vue'),
        meta: {
          title: '系统日志',
          requiresAuth: true
        }
      },
      {
        path: 'sync',
        name: 'MultiSourceSync',
        component: () => import('@/views/System/MultiSourceSync.vue'),
        meta: {
          title: '多数据源同步',
          requiresAuth: true
        }
      },
      {
        path: 'cache',
        name: 'CacheManagement',
        component: () => import('@/views/Settings/CacheManagement.vue'),
        meta: {
          title: '缓存管理',
          requiresAuth: true
        }
      },
      {
        path: 'usage',
        name: 'UsageStatistics',
        component: () => import('@/views/Settings/UsageStatistics.vue'),
        meta: {
          title: '使用统计',
          requiresAuth: true
        }
      },
      {
        path: 'scheduler',
        name: 'SchedulerManagement',
        component: () => import('@/views/System/SchedulerManagement.vue'),
        meta: {
          title: '定时任务',
          requiresAuth: true
        }
      },
      // 计费配置页：requiresAdmin 标记使路由守卫在用户非管理员时重定向到 /dashboard，
      // 与侧边栏 v-if="authStore.isAdmin" 形成前后端双重权限校验。
      {
        path: 'billing',
        name: 'BillingConfig',
        component: () => import('@/views/Settings/BillingConfig.vue'),
        meta: {
          title: '计费配置',
          requiresAuth: true,
          requiresAdmin: true
        }
      }
    ]
  },

  // ==================== 算力充值计费 ====================
  {
    path: '/token-recharge',
    name: 'TokenRecharge',
    component: () => import('@/layouts/BasicLayout.vue'),
    meta: {
      title: '算力充值',
      icon: 'Wallet',
      requiresAuth: true,
      transition: 'fade'
    },
    children: [
      {
        path: '',
        name: 'TokenRechargeHome',
        component: () => import('@/views/TokenRecharge/index.vue'),
        meta: {
          title: '算力充值',
          requiresAuth: true
        }
      },
      {
        path: 'transactions',
        name: 'TokenTransactions',
        component: () => import('@/views/TokenRecharge/Transactions.vue'),
        meta: {
          title: '交易明细',
          requiresAuth: true
        }
      }
    ]
  },

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
    path: '/about',
    name: 'About',
    component: () => import('@/views/About/index.vue'),
    meta: {
      title: '关于',
      icon: 'InfoFilled',
      requiresAuth: false, // 关于页面不需要认证
      transition: 'fade'
    }
  },
  {
    path: '/paper',
    name: 'PaperTrading',
    component: () => import('@/layouts/BasicLayout.vue'),
    meta: {
      title: '模拟交易',
      icon: 'CreditCard',
      requiresAuth: true,
      transition: 'slide-up'
    },
    children: [
      {
        path: '',
        name: 'PaperTradingHome',
        component: () => import('@/views/PaperTrading/index.vue'),
        meta: {
          title: '模拟交易',
          requiresAuth: true
        }
      }
    ]
  },

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
  // 开始进度条
  NProgress.start()

  const authStore = useAuthStore()
  const appStore = useAppStore()

  // 设置页面标题
  const title = to.meta.title as string
  if (title) {
    document.title = `${title} - 智投`
  }

  console.log('🚦 路由守卫检查:', {
    path: to.fullPath,
    name: to.name,
    requiresAuth: to.meta.requiresAuth,
    isAuthenticated: authStore.isAuthenticated,
    hasToken: !!authStore.token
  })

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



  // 管理员权限校验：放在认证检查之后，确保 authStore 已完成用户信息加载。
  // requiresAdmin 路由的 meta 在路由配置中声明，此处统一拦截，避免每个页面自行判断。
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
  // 结束进度条
  NProgress.done()

  // 页面切换后的处理
  nextTick(() => {
    // 可以在这里添加页面分析、埋点等逻辑
  })
})

// 路由错误处理
router.onError((error) => {
  console.error('路由错误:', error)
  NProgress.done()
  ElMessage.error('页面加载失败，请重试')
})

export default router

// 导出路由配置供其他地方使用
export { routes }
