<template>
  <el-menu
    :default-active="activeMenu"
    :collapse="appStore.sidebarCollapsed"
    :unique-opened="true"
    router
    class="sidebar-menu"
  >
    <el-menu-item index="/dashboard">
      <el-icon><Odometer /></el-icon>
      <template #title>工作台</template>
    </el-menu-item>

    <el-sub-menu index="/analysis">
      <template #title>
        <el-icon><TrendCharts /></el-icon>
        <span>股票分析</span>
      </template>
      <el-menu-item index="/analysis/single">单股分析</el-menu-item>
      <el-menu-item index="/analysis/batch">批量分析</el-menu-item>
      <el-menu-item index="/reports">分析报告</el-menu-item>
    </el-sub-menu>

    <el-menu-item index="/screening">
      <el-icon><Search /></el-icon>
      <template #title>选股器</template>
    </el-menu-item>

    <el-menu-item index="/favorites">
      <el-icon><Star /></el-icon>
      <template #title>自选股</template>
    </el-menu-item>

    <el-menu-item index="/paper">
      <el-icon><CreditCard /></el-icon>
      <template #title>模拟交易</template>
    </el-menu-item>

    <el-sub-menu index="/investment">
      <template #title>
        <el-icon><UserFilled /></el-icon>
        <span>个人投资助手</span>
      </template>
      <el-menu-item index="/investment/home">新手首页</el-menu-item>
      <el-menu-item index="/investment/marketplace">策略广场</el-menu-item>
      <el-menu-item index="/investment/observations">我的观察</el-menu-item>
      <el-menu-item index="/investment/profile">投资画像</el-menu-item>
      <el-menu-item index="/investment/strategies">策略管理</el-menu-item>
    </el-sub-menu>

    <el-sub-menu index="/news-watch">
      <template #title>
        <el-icon><Bell /></el-icon>
        <span>新闻关注</span>
      </template>
      <el-menu-item index="/news-watch/workbench">关注工作台</el-menu-item>
      <el-menu-item index="/news-watch/impact">持仓影响分析</el-menu-item>
      <el-menu-item index="/news-watch/events">事件分析</el-menu-item>
      <el-menu-item index="/news-watch/closed-loop">闭环复盘</el-menu-item>
      <el-menu-item index="/news-watch/alerts">告警配置</el-menu-item>
    </el-sub-menu>

    <el-sub-menu v-if="showEvaluationPlatform" index="/evaluation">
      <template #title>
        <el-icon><DataAnalysis /></el-icon>
        <span>Agent 评测</span>
      </template>
      <el-menu-item index="/evaluation/dashboard">评测概览</el-menu-item>
      <el-menu-item index="/evaluation/decision-audit">决策审计</el-menu-item>
      <el-menu-item index="/evaluation/datasets">评测集管理</el-menu-item>
      <el-menu-item index="/evaluation/runs">评测运行</el-menu-item>
      <el-menu-item index="/evaluation/trends">质量趋势</el-menu-item>
      <el-menu-item index="/evaluation/review">人工复核</el-menu-item>
      <el-menu-item index="/evaluation/bad-cases">Bad Case 池</el-menu-item>
    </el-sub-menu>

    <el-sub-menu v-if="showSelfEvolution" index="/evolution">
      <template #title>
        <el-icon><MagicStick /></el-icon>
        <span>自进化</span>
      </template>
      <el-menu-item index="/evolution/proposals">候选提案</el-menu-item>
      <el-menu-item index="/evolution/artifacts">Artifact 管理</el-menu-item>
      <el-menu-item index="/evolution/receipts">进化回执</el-menu-item>
    </el-sub-menu>

    <el-menu-item index="/tasks">
      <el-icon><List /></el-icon>
      <template #title>分析任务</template>
    </el-menu-item>

    <el-menu-item index="/research-agent">
      <el-icon><ChatDotRound /></el-icon>
      <template #title>AI 研究</template>
    </el-menu-item>

    <el-sub-menu index="/settings">
      <template #title>
        <el-icon><Setting /></el-icon>
        <span>设置</span>
      </template>

      <el-menu-item index="/settings">通用设置</el-menu-item>
      <el-menu-item index="/settings?tab=appearance">外观设置</el-menu-item>
      <el-menu-item index="/settings?tab=analysis">分析偏好</el-menu-item>

      <template v-if="authStore.isAdmin">
        <el-menu-item index="/settings/config">配置管理</el-menu-item>
        <el-menu-item index="/settings/cache">缓存管理</el-menu-item>
      </template>
    </el-sub-menu>

    <!-- 系统管理 -->
    <el-sub-menu v-if="authStore.isAdmin" index="/settings-admin">
      <template #title>
        <el-icon><Setting /></el-icon>
        <span>系统管理</span>
      </template>
      <el-menu-item index="/settings/users">用户管理</el-menu-item>
      <el-menu-item index="/settings/database">数据库管理</el-menu-item>
      <el-menu-item index="/settings/logs">操作日志</el-menu-item>
      <el-menu-item index="/settings/scheduler">定时任务</el-menu-item>
    </el-sub-menu>
  </el-menu>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { useRoute } from 'vue-router'
import { useAppStore } from '@/stores/app'
import { useAuthStore } from '@/stores/auth'
import {
  Odometer,
  TrendCharts,
  Search,
  Star,
  List,
  ChatDotRound,
  DataAnalysis,
  Setting,
  InfoFilled,
  CreditCard,
  UserFilled,
  Bell,
  MagicStick
} from '@element-plus/icons-vue'

const route = useRoute()
const appStore = useAppStore()
const authStore = useAuthStore()

const activeMenu = computed(() => route.path)
const showEvaluationPlatform = computed(() => {
  return import.meta.env.VITE_EVAL_PLATFORM_ENABLED === 'true' && authStore.isAdmin
})
const showSelfEvolution = computed(() => {
  return showEvaluationPlatform.value && import.meta.env.VITE_EVOLUTION_ENABLED === 'true'
})
</script>

<style lang="scss" scoped>
.sidebar-menu {
  border: none;
  height: 100%;
  padding: 0 10px;

  :deep(.el-menu-item),
  :deep(.el-sub-menu__title) {
    height: 44px;
    line-height: 44px;
    border-radius: 10px;
    margin-bottom: 4px;
    font-size: 14px;
    color: var(--el-text-color-regular);

    &:hover {
      background-color: var(--el-fill-color-light);
      color: var(--el-text-color-primary);
    }

    .el-icon {
      font-size: 18px;
      color: var(--el-text-color-secondary);
    }
  }

  :deep(.el-menu-item.is-active) {
    background: linear-gradient(135deg, var(--el-color-primary-light-9) 0%, var(--el-color-primary-light-8) 100%);
    color: var(--el-color-primary);
    font-weight: 600;

    .el-icon {
      color: var(--el-color-primary);
    }

    &::before {
      content: '';
      position: absolute;
      left: -10px;
      top: 50%;
      transform: translateY(-50%);
      width: 3px;
      height: 18px;
      border-radius: 0 3px 3px 0;
      background: var(--el-color-primary);
    }
  }

  :deep(.el-sub-menu .el-menu) {
    background: transparent;
    padding-left: 8px;
  }

  :deep(.el-sub-menu .el-menu-item) {
    height: 38px;
    line-height: 38px;
    font-size: 13px;
  }

  // 折叠状态：去掉左右 padding，图标居中
  &.el-menu--collapse {
    padding: 0;

    :deep(.el-menu-item),
    :deep(.el-menu-tooltip__trigger),
    :deep(.el-sub-menu__title) {
      display: flex !important;
      align-items: center;
      justify-content: center;
      padding-left: 0 !important;
      padding-right: 0 !important;
      text-align: center;
      border-radius: 10px;
      margin: 0 6px 4px;

      .el-icon {
        margin-right: 0 !important;
        margin-left: 0 !important;
      }
    }

    :deep(.el-tooltip__trigger) {
      justify-content: left !important;
      padding-left: 6px !important;
    }

    :deep(.el-menu-item.is-active)::before {
      left: -6px;
    }
  }
}
</style>
