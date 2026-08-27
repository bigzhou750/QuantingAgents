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
        <el-menu-item index="/settings/database">数据库管理</el-menu-item>
        <el-menu-item index="/settings/logs">操作日志</el-menu-item>
        <el-menu-item index="/settings/scheduler">定时任务</el-menu-item>
      </template>
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
  Setting,
  CreditCard
} from '@element-plus/icons-vue'

const route = useRoute()
const appStore = useAppStore()
const authStore = useAuthStore()

const activeMenu = computed(() => route.path)
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
}
</style>
