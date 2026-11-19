<template>
  <main class="public-page">
    <header class="public-header">
      <router-link class="brand" to="/">智能投研助手</router-link>
      <nav><router-link to="/privacy">隐私政策</router-link><router-link to="/terms">服务条款</router-link><router-link to="/login">登录</router-link><router-link to="/register">注册</router-link></nav>
    </header>
    <section class="content">
      <p class="eyebrow">zhitouagent</p>
      <h1>定价与使用说明</h1>
      <p class="lead">我们按实际启用的套餐和模型用量计费。登录后看到的套餐与余额页面是当前生效配置。</p>
      <div v-if="packages.length" class="section">
        <h2>当前套餐</h2>
        <div class="packages"><div v-for="pkg in packages" :key="pkg.package_id" class="package"><strong>¥{{ pkg.amount_cny }}</strong><span>{{ pkg.quota_to_credit }} 额度</span><small v-if="pkg.gift_amount">赠送 {{ pkg.gift_amount }}</small></div></div>
      </div>
      <div class="section">
        <h2>当前计费方式</h2>
        <p>平台使用算力额度记录模型调用和 Agent 研究任务消耗。不同模型、输入输出长度和任务类型可能产生不同消耗。</p>
        <p>具体套餐金额、到账额度、赠送额度和支付状态以平台当前展示为准。尚未启用的支付能力不会被视为已开放服务。</p>
      </div>
      <div class="section">
        <h2>使用限制</h2>
        <p>账户额度、每日配额、并发任务数和数据源可用性可能因账户配置而不同。服务异常或数据源不可用时，系统会显示任务状态，不能保证分析结果按时生成。</p>
      </div>
      <div class="section">
        <h2>退款与支持</h2>
        <p>额度充值属于即时到账的数字服务，除重复扣款、平台确认的服务中断或适用法律另有规定外，一般不提供无理由退款。支付、退款和订单异常请保留订单号或流水号联系 <a href="mailto:zh75067197@gmail.com">zh75067197@gmail.com</a>，我们会按实际订单状态处理。</p>
      </div>
      <p class="notice">AI 分析结果仅供研究和信息整理参考，不构成投资、证券、交易或收益承诺。</p>
    </section>
  </main>
</template>

<script setup lang="ts">
import { onMounted, ref } from 'vue'

const DEFAULT_PACKAGES = [
  { package_id: 'pkg_20', name: '20元套餐', amount_cny: 20, quota_to_credit: 22, gift_amount: 2, tags: [] },
  { package_id: 'pkg_50', name: '50元套餐', amount_cny: 50, quota_to_credit: 55, gift_amount: 5, tags: [] },
  { package_id: 'pkg_100', name: '100元套餐', amount_cny: 100, quota_to_credit: 110, gift_amount: 10, tags: ['hot'] },
  { package_id: 'pkg_200', name: '200元套餐', amount_cny: 200, quota_to_credit: 220, gift_amount: 20, tags: [] },
  { package_id: 'pkg_500', name: '500元套餐', amount_cny: 500, quota_to_credit: 550, gift_amount: 50, tags: ['recommended'] }
]

const packages = ref<Array<{ package_id: string; name: string; amount_cny: number; quota_to_credit: number; gift_amount: number; tags: string[] }>>(DEFAULT_PACKAGES)
onMounted(async () => {
  try {
    const response = await fetch('/api/token-billing/public-packages')
    if (response.ok) {
      const items = (await response.json()).data?.items || []
      if (items.length) packages.value = items
    }
  } catch {
    // 保留默认公开套餐，确保审核和未登录访客始终能看到价格
  }
})
</script>

<style scoped>
.public-page { min-height: 100vh; background: #101214; color: #e5e7eb; }
.public-header { display: flex; justify-content: space-between; align-items: center; padding: 24px max(24px, calc((100vw - 1080px) / 2)); border-bottom: 1px solid #2b3036; }
.brand { color: #fff; font-weight: 700; text-decoration: none; }
nav { display: flex; gap: 18px; } nav a { color: #aeb7c2; text-decoration: none; }
.content { max-width: 820px; margin: 0 auto; padding: 72px 24px 96px; } .eyebrow { color: #5ec4b6; text-transform: uppercase; letter-spacing: 1px; }
h1 { font-size: clamp(32px, 5vw, 52px); margin: 12px 0 18px; } h2 { font-size: 21px; margin-bottom: 10px; } .lead, p { line-height: 1.8; color: #b9c0c8; } .section { margin-top: 42px; } a { color: #6fd3c4; } .notice { margin-top: 48px; padding-top: 24px; border-top: 1px solid #2b3036; }
.packages { display: flex; flex-wrap: wrap; gap: 12px; }.package { display: grid; gap: 4px; min-width: 140px; padding: 16px; border: 1px solid #2b3036; border-radius: 6px; }.package strong { color: #fff; font-size: 20px; }.package span, .package small { color: #aeb7c2; }
</style>
