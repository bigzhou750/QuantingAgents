<template>
  <main class="landing">
    <header class="landing-header">
      <router-link class="brand" to="/">
        <img src="/logo.svg" alt="智能投研助手" />
        <span>智能投研助手</span>
      </router-link>
      <nav class="landing-nav">
        <router-link to="/pricing">定价</router-link>
        <router-link to="/privacy">隐私政策</router-link>
        <router-link to="/terms">服务条款</router-link>
        <template v-if="isAuthenticated">
          <router-link class="nav-cta" to="/dashboard">进入工作台</router-link>
        </template>
        <template v-else>
          <router-link to="/login">登录</router-link>
          <router-link class="nav-cta" to="/register">注册</router-link>
        </template>
      </nav>
    </header>

    <section class="hero">
      <p class="eyebrow">zhitouagent</p>
      <h1>智能投研助手</h1>
      <p class="hero-lead">面向 A 股、港股和美股研究场景的 AI 研究工作台。</p>
      <p class="hero-copy">
        整理公开行情、新闻和财务信息，提供多角度研究分析、选股观察、新闻跟踪和模拟交易记录，结果可追溯，仅用于研究参考。
      </p>
      <div class="hero-actions">
        <el-button type="primary" size="large" @click="startNow">
          <el-icon><TrendCharts /></el-icon>
          {{ isAuthenticated ? '进入工作台' : '开始使用' }}
        </el-button>
        <router-link class="secondary-link" to="/pricing">查看定价</router-link>
      </div>
    </section>

    <section class="capabilities" aria-labelledby="capabilities-title">
      <div class="section-heading">
        <h2 id="capabilities-title">主要能力</h2>
        <p>围绕投资研究常用流程组织，任务状态与结果记录可追踪。</p>
      </div>
      <div class="capability-grid">
        <div v-for="item in capabilities" :key="item.title" class="capability-item">
          <h3>{{ item.title }}</h3>
          <p>{{ item.desc }}</p>
        </div>
      </div>
    </section>

    <section class="risk-band">
      <p><strong>风险提示：</strong>AI 分析结果仅供研究和信息整理参考，不构成投资、证券或交易建议。市场有风险，投资需谨慎。</p>
    </section>

    <footer class="landing-footer">
      <div class="footer-row">
        <span>&copy; 2026 智能投研助手 · zhitouagent</span>
        <nav>
          <router-link to="/pricing">定价</router-link>
          <router-link to="/privacy">隐私政策</router-link>
          <router-link to="/terms">服务条款</router-link>
          <a href="mailto:zh75067197@gmail.com">支持邮箱</a>
        </nav>
      </div>
    </footer>
  </main>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { useRouter } from 'vue-router'
import { useAuthStore } from '@/stores/auth'
import { TrendCharts } from '@element-plus/icons-vue'

const router = useRouter()
const authStore = useAuthStore()
const isAuthenticated = computed(() => authStore.isAuthenticated)

const startNow = () => {
  router.push(isAuthenticated.value ? '/dashboard' : '/register')
}

const capabilities = [
  { title: '市场覆盖', desc: '支持 A 股、港股和美股公开信息的研究与整理。' },
  { title: '研究分析', desc: '提供单股分析、批量研究、选股、投资画像和 AI 研究工作台。' },
  { title: '记录可追溯', desc: '任务状态、报告、观察记录和模拟交易结果可回溯查看。' }
]
</script>

<style lang="scss" scoped>
.landing {
  min-height: 100vh;
  background: #101214;
  color: #e6e9ed;
}

.landing-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 24px;
  max-width: 1180px;
  margin: 0 auto;
  padding: 18px 32px;
  border-bottom: 1px solid #2b3036;

  .brand {
    display: inline-flex;
    align-items: center;
    gap: 10px;
    color: #fff;
    font-size: 18px;
    font-weight: 700;
    text-decoration: none;

    img {
      width: 30px;
      height: 30px;
    }
  }
}

.landing-nav {
  display: flex;
  align-items: center;
  gap: 18px;
  flex-wrap: wrap;

  a {
    color: #aeb7c2;
    text-decoration: none;
    white-space: nowrap;
  }

  .nav-cta {
    padding: 8px 14px;
    border: 1px solid #3c454f;
    border-radius: 6px;
    color: #fff;
    background: #20262c;
  }
}

.hero {
  max-width: 860px;
  margin: 0 auto;
  padding: 84px 32px 64px;
}

.eyebrow {
  margin: 0 0 14px;
  color: #5ec4b6;
  font-size: 14px;
  font-weight: 600;
  text-transform: uppercase;
}

h1 {
  margin: 0 0 16px;
  font-size: 46px;
  line-height: 1.18;
  color: #fff;
}

.hero-lead {
  margin: 0 0 14px;
  font-size: 22px;
  line-height: 1.5;
  color: #dfe4e9;
}

.hero-copy {
  max-width: 720px;
  margin: 0;
  font-size: 16px;
  line-height: 1.85;
  color: #aeb7c2;
}

.hero-actions {
  display: flex;
  align-items: center;
  gap: 18px;
  margin-top: 32px;

  :deep(.el-button--primary) {
    background: #4aa8a0;
    border-color: #4aa8a0;
    color: #fff;
  }

  .secondary-link {
    color: #6fd3c4;
    text-decoration: none;
    font-weight: 500;
  }
}

.capabilities {
  max-width: 1180px;
  margin: 0 auto;
  padding: 48px 32px 64px;
}

.section-heading {
  max-width: 720px;

  h2 {
    margin: 0 0 10px;
    font-size: 28px;
    color: #fff;
  }

  p {
    margin: 0;
    color: #aeb7c2;
    line-height: 1.7;
  }
}

.capability-grid {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 16px;
  margin-top: 28px;
}

.capability-item {
  padding-top: 20px;
  border-top: 1px solid #343b43;

  h3 {
    margin: 0 0 10px;
    color: #fff;
    font-size: 18px;
  }

  p {
    margin: 0;
    color: #aeb7c2;
    line-height: 1.75;
  }
}

.risk-band {
  max-width: 1180px;
  margin: 0 auto;
  padding: 0 32px 64px;

  p {
    margin: 0;
    padding: 18px 20px;
    border-left: 3px solid #d99a4e;
    background: #1a1e24;
    color: #c6ccd2;
    line-height: 1.8;
  }
}

.landing-footer {
  border-top: 1px solid #2b3036;
  padding: 26px 32px;

  .footer-row {
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 20px;
    max-width: 1180px;
    margin: 0 auto;
    color: #7f8891;
    font-size: 13px;
  }

  nav {
    display: flex;
    flex-wrap: wrap;
    gap: 18px;
  }

  a {
    color: #aeb7c2;
    text-decoration: none;
  }
}

@media (max-width: 768px) {
  .landing-header {
    align-items: flex-start;
    flex-direction: column;
    padding: 16px 20px;
  }

  .landing-nav {
    gap: 14px;
  }

  .hero {
    padding: 56px 20px 44px;
  }

  h1 {
    font-size: 34px;
  }

  .hero-lead {
    font-size: 18px;
  }

  .hero-actions {
    align-items: flex-start;
    flex-direction: column;
  }

  .capability-grid {
    grid-template-columns: 1fr;
  }

  .capabilities,
  .risk-band {
    padding-left: 20px;
    padding-right: 20px;
  }

  .landing-footer {
    padding: 20px;
  }

  .footer-row {
    align-items: flex-start;
    flex-direction: column;
  }
}
</style>
