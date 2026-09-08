<template>
  <div class="about">
    <!-- Hero Section -->
    <div class="hero-section">
      <div class="hero-content">
        <div class="hero-text">
          <h1 class="hero-title">智投</h1>
          <p class="hero-subtitle">AI智能股票分析平台</p>
          <p class="hero-description">
            基于先进的多智能体AI技术，覆盖A股、美股、港股，为投资者提供全方位的分析视角。
          </p>
          <div class="hero-actions">
            <el-button type="primary" size="large" @click="goToAnalysis">
              <el-icon><TrendCharts /></el-icon>
              开始分析
            </el-button>
          </div>
        </div>
      </div>
    </div>

    <!-- Footer -->
    <div class="footer-section">
      <div class="footer-content">
        <p>&copy; 2025 智投. All rights reserved.</p>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { useRouter } from 'vue-router'
import { TrendCharts } from '@element-plus/icons-vue'

const router = useRouter()

const goToAnalysis = () => {
  router.push('/analysis/single')
}
</script>

<style lang="scss" scoped>
.about {
  max-width: 1200px;
  margin: 0 auto;
  padding: 0 24px;

  .hero-section {
    background: var(--zt-gradient-hero);
    border-radius: 16px;
    padding: 60px 40px;
    margin-bottom: 48px;
    color: white;
    text-align: center;

    .hero-content {
      display: flex;
      justify-content: center;
    }

    .hero-text {
      max-width: 600px;
    }

    .hero-title {
      font-size: 48px;
      font-weight: 700;
      line-height: 1.2;
      margin: 0 0 16px 0;
      color: white;
    }

    .hero-subtitle {
      font-size: 24px;
      font-weight: 500;
      margin: 0 0 24px 0;
      opacity: 0.95;
    }

    .hero-description {
      font-size: 16px;
      line-height: 1.6;
      margin: 0 0 32px 0;
      opacity: 0.9;
    }

    .hero-actions {
      display: flex;
      gap: 16px;
      justify-content: center;

      :deep(.el-button) {
        background: rgba(255, 255, 255, 0.2);
        border-color: rgba(255, 255, 255, 0.3);
        color: white;

        &:hover {
          background: rgba(255, 255, 255, 0.3);
          border-color: rgba(255, 255, 255, 0.5);
        }
      }

      :deep(.el-button--primary) {
        background: white;
        border-color: white;
        color: #0EA5E9;

        &:hover {
          background: rgba(255, 255, 255, 0.9);
          color: #0284C7;
        }
      }
    }
  }

  .footer-section {
    text-align: center;
    padding: 32px 0;

    .footer-content p {
      color: var(--el-text-color-secondary);
      font-size: 14px;
      margin: 0;
    }
  }
}

@media (max-width: 768px) {
  .about {
    padding: 0 16px;

    .hero-section {
      padding: 40px 24px;

      .hero-title {
        font-size: 32px;
      }

      .hero-subtitle {
        font-size: 18px;
      }
    }
  }
}
</style>
