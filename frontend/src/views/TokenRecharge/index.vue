<template>
  <div class="token-recharge-page">
    <!-- Header -->
    <div class="page-header">
      <h1 class="page-title">
        <el-icon><Wallet /></el-icon>
        算力充值
      </h1>
      <p class="page-description">充值额度用于Agent对话和模型调用，额度永久有效</p>
    </div>

    <!-- 余额概览 -->
    <el-row :gutter="20" class="balance-overview">
      <el-col :span="6">
        <el-card shadow="never" class="metric-card">
          <div class="metric-value primary">{{ billingStore.balanceDisplay }}</div>
          <div class="metric-label">当前余额</div>
        </el-card>
      </el-col>
      <el-col :span="6">
        <el-card shadow="never" class="metric-card">
          <div class="metric-value">¥{{ billingStore.totalRecharged.toFixed(2) }}</div>
          <div class="metric-label">累计充值</div>
        </el-card>
      </el-col>
      <el-col :span="6">
        <el-card shadow="never" class="metric-card">
          <div class="metric-value">¥{{ billingStore.totalConsumed.toFixed(3) }}</div>
          <div class="metric-label">累计消耗</div>
        </el-card>
      </el-col>
      <el-col :span="6">
        <el-card shadow="never" class="metric-card">
          <div class="metric-value">¥{{ billingStore.totalGifted.toFixed(2) }}</div>
          <div class="metric-label">累计赠送</div>
        </el-card>
      </el-col>
    </el-row>

    <!-- 中断恢复提示 -->
    <el-alert
      v-if="billingStore.pendingOrder"
      type="warning"
      :closable="true"
      show-icon
      class="pending-alert"
    >
      <template #title>
        您有一笔未完成的支付订单（{{ billingStore.pendingOrder.amount }}元），
        <el-link type="primary" @click="resumePayment">继续支付</el-link>
      </template>
    </el-alert>

    <!-- 充值套餐 -->
    <el-card shadow="never" class="packages-card">
      <template #header>
        <div class="card-header">
          <span>选择充值套餐</span>
          <span class="rate-hint">兑换率: 1元 = {{ exchangeRate }}额度</span>
        </div>
      </template>

      <el-row :gutter="16">
        <el-col
          v-for="pkg in billingStore.packages"
          :key="pkg.package_id"
          :xs="12" :sm="8" :md="6" :lg="4"
        >
          <div
            class="package-item"
            :class="{ active: selectedPackage === pkg.package_id }"
            @click="selectPackage(pkg)"
          >
            <div class="package-tags">
              <el-tag v-for="tag in pkg.tags" :key="tag" size="small" type="danger" effect="dark">
                {{ tag === 'hot' ? '热门' : tag === 'recommended' ? '推荐' : tag }}
              </el-tag>
            </div>
            <div class="package-amount">¥{{ pkg.amount_cny }}</div>
            <div class="package-quota">得 {{ pkg.quota_to_credit?.toFixed(1) || (pkg.amount_cny * exchangeRate).toFixed(1) }} 额度</div>
            <div class="package-gift" v-if="(pkg.gift_amount || 0) > 0">
              含赠 {{ pkg.gift_amount?.toFixed(1) || ((pkg.amount_cny * exchangeRate) - pkg.amount_cny).toFixed(1) }}
            </div>
          </div>
        </el-col>
      </el-row>

      <!-- 充值按钮 -->
      <div class="recharge-action">
        <el-button
          type="primary"
          size="large"
          :disabled="!selectedPackage"
          @click="confirmDialogVisible = true"
          class="recharge-btn"
        >
          {{ selectedPackage ? `立即充值 ¥${confirmAmount.toFixed(2)}` : '请选择充值套餐' }}
        </el-button>
      </div>
    </el-card>

    <!-- 确认付款弹窗 -->
    <el-dialog
      v-model="confirmDialogVisible"
      title="确认付款"
      width="480px"
      :close-on-click-modal="false"
    >
      <div class="confirm-content">
        <el-alert
          type="info"
          :closable="false"
          show-icon
          class="safety-endorsement"
        >
          <template #title>微信支付 · 平台担保</template>
          您的支付由微信支付提供安全保障，充值即时到账
        </el-alert>

        <el-descriptions :column="1" border class="order-summary">
          <el-descriptions-item label="充值金额">¥{{ confirmAmount.toFixed(2) }}</el-descriptions-item>
          <el-descriptions-item label="到账额度">{{ confirmQuota.toFixed(3) }}</el-descriptions-item>
          <el-descriptions-item label="赠送额度" v-if="confirmGift > 0">
            <span class="gift-text">+{{ confirmGift.toFixed(3) }}</span>
          </el-descriptions-item>
          <el-descriptions-item label="支付方式">微信支付</el-descriptions-item>
        </el-descriptions>
        <el-alert
          type="warning"
          :closable="false"
          show-icon
          class="refund-notice"
          title="退款说明"
        >
          额度为即时到账数字服务，除重复扣款、平台原因或法律要求外不支持无理由退款。订单问题请联系
          <a href="mailto:zh75067197@gmail.com">zh75067197@gmail.com</a>。
        </el-alert>
      </div>

      <template #footer>
        <el-button @click="confirmDialogVisible = false">取消</el-button>
        <el-button type="primary" :loading="paying" @click="confirmPay">
          确认付款 ¥{{ confirmAmount.toFixed(2) }}
        </el-button>
      </template>
    </el-dialog>

    <!-- 支付状态弹窗 -->
    <el-dialog
      v-model="payStatusDialogVisible"
      :title="payStatusTitle"
      width="400px"
      :close-on-click-modal="false"
      :show-close="payStatus !== 'polling'"
    >
      <div class="pay-status-content">
        <!-- 扫码支付 -->
        <div v-if="payType === 'NATIVE' && payStatus === 'polling'" class="qr-section">
          <div class="qr-placeholder">
            <el-icon :size="48"><Monitor /></el-icon>
            <p>请使用微信扫码支付</p>
          </div>
          <p class="qr-tip">二维码有效期 {{ expireMinutes }} 分钟</p>
        </div>

        <!-- MWEB跳转 -->
        <div v-if="payType === 'MWEB' && payStatus === 'polling'" class="mweb-section">
          <el-button type="primary" @click="openMwebPay">打开微信支付</el-button>
          <p class="mweb-tip">若未自动跳转，请手动点击按钮</p>
        </div>

        <!-- 支付成功 -->
        <div v-if="payStatus === 'success'" class="success-section">
          <el-icon :size="64" color="#67C23A"><CircleCheckFilled /></el-icon>
          <h3>充值成功！</h3>
          <p>到账额度: {{ confirmQuota.toFixed(3) }}</p>
          <p class="support-line">订单问题请联系 <a href="mailto:zh75067197@gmail.com">zh75067197@gmail.com</a></p>
        </div>

        <!-- 支付失败 -->
        <div v-if="payStatus === 'failed'" class="fail-section">
          <el-icon :size="64" color="#F56C6C"><CircleCloseFilled /></el-icon>
          <h3>支付未完成</h3>
          <p>{{ payFailMessage }}</p>
          <el-button type="primary" @click="retryPay">重新支付</el-button>
        </div>
      </div>
    </el-dialog>

    <!-- 底部链接 -->
    <div class="page-footer">
      <router-link to="/token-recharge/transactions">查看交易明细</router-link>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, onUnmounted } from 'vue'
import { ElMessage } from 'element-plus'
import { Wallet, Monitor, CircleCheckFilled, CircleCloseFilled } from '@element-plus/icons-vue'
import { useTokenBillingStore } from '@/stores/tokenBilling'
import { tokenBillingApi } from '@/api/tokenBilling'

const billingStore = useTokenBillingStore()

// 状态
const selectedPackage = ref<string>('')
const confirmDialogVisible = ref(false)
const payStatusDialogVisible = ref(false)
const paying = ref(false)
const payStatus = ref<'idle' | 'polling' | 'success' | 'failed'>('idle')
const payType = ref('NATIVE')
const payFailMessage = ref('')
const currentOrderId = ref('')
const mwebUrl = ref('')
const codeUrl = ref('')
let pollTimer: ReturnType<typeof setInterval> | null = null

// 计算属性
const exchangeRate = computed(() => {
  // 从第一个套餐推算，或取默认值
  const pkg = billingStore.packages[0]
  if (pkg && pkg.quota_to_credit && pkg.amount_cny) {
    return parseFloat((pkg.quota_to_credit / pkg.amount_cny).toFixed(2))
  }
  return 1.1
})

const confirmAmount = computed(() => {
  const pkg = billingStore.packages.find(p => p.package_id === selectedPackage.value)
  return pkg?.amount_cny || 0
})

const confirmQuota = computed(() => {
  const pkg = billingStore.packages.find(p => p.package_id === selectedPackage.value)
  return pkg?.quota_to_credit || (confirmAmount.value * exchangeRate.value)
})

const confirmGift = computed(() => {
  return Math.max(confirmQuota.value - confirmAmount.value, 0)
})

const payStatusTitle = computed(() => {
  switch (payStatus.value) {
    case 'polling': return '等待支付'
    case 'success': return '支付成功'
    case 'failed': return '支付未完成'
    default: return '支付'
  }
})

const expireMinutes = ref(30)

// 方法
function selectPackage(pkg: any) {
  selectedPackage.value = pkg.package_id
}

async function confirmPay() {
  if (!selectedPackage.value) {
    ElMessage.warning('请选择充值套餐')
    return
  }

  confirmDialogVisible.value = false
  paying.value = true

  try {
    const idempotencyKey = `recharge_${Date.now()}_${Math.random().toString(36).slice(2, 8)}`
    const res = await tokenBillingApi.createOrder({
      package_id: selectedPackage.value,
      idempotency_key: idempotencyKey,
    })

    if (res.success && res.data) {
      const order = res.data as any
      currentOrderId.value = order.order_id
      payType.value = order.pay_type
      expireMinutes.value = Math.round(new Date(order.expire_at).getTime() - Date.now()) / 60000

      if (order.pay_type === 'NATIVE') {
        codeUrl.value = order.pay_params?.code_url || ''
      } else if (order.pay_type === 'MWEB') {
        mwebUrl.value = order.pay_params?.mweb_url || ''
      }

      // 模拟支付模式：后端已直接入账，无需轮询
      if (order.pay_params?.mock) {
        payStatus.value = 'success'
        payStatusDialogVisible.value = true
        billingStore.fetchAccount()
        setTimeout(() => {
          payStatusDialogVisible.value = false
          ElMessage.success('模拟充值成功！额度已到账')
        }, 2000)
      } else {
        payStatus.value = 'polling'
        payStatusDialogVisible.value = true
        startPolling()
      }
    } else {
      ElMessage.error(res.message || '创建订单失败')
    }
  } catch (error: any) {
    ElMessage.error(error?.message || '创建订单失败')
  } finally {
    paying.value = false
  }
}

function startPolling() {
  if (pollTimer) clearInterval(pollTimer)
  pollTimer = setInterval(async () => {
    try {
      const res = await tokenBillingApi.getOrderStatus(currentOrderId.value)
      if (res.success && res.data) {
        const status = (res.data as any).status
        if (status === 'credited') {
          payStatus.value = 'success'
          stopPolling()
          billingStore.fetchAccount()
          setTimeout(() => {
            payStatusDialogVisible.value = false
            ElMessage.success('充值到账成功！')
          }, 2000)
        } else if (['failed', 'expired', 'cancelled'].includes(status)) {
          payStatus.value = 'failed'
          payFailMessage.value = status === 'expired' ? '订单已过期' : '支付未完成'
          stopPolling()
        }
      }
    } catch {
      // 轮询失败忽略，继续下一次
    }
  }, 3000)
}

function stopPolling() {
  if (pollTimer) {
    clearInterval(pollTimer)
    pollTimer = null
  }
}

function openMwebPay() {
  if (mwebUrl.value) {
    window.location.href = mwebUrl.value
  }
}

function resumePayment() {
  if (billingStore.pendingOrder) {
    currentOrderId.value = billingStore.pendingOrder.order_id
    payType.value = billingStore.pendingOrder.pay_type
    payStatus.value = 'polling'
    payStatusDialogVisible.value = true
    startPolling()
  }
}

function retryPay() {
  payStatusDialogVisible.value = false
  confirmDialogVisible.value = true
}

onMounted(() => {
  billingStore.init()
})

onUnmounted(() => {
  stopPolling()
})
</script>

<style lang="scss" scoped>
.token-recharge-page {
  padding: 20px;
  max-width: 1200px;
  margin: 0 auto;
}

.page-header {
  margin-bottom: 24px;

  .page-title {
    display: flex;
    align-items: center;
    gap: 8px;
    font-size: 24px;
    font-weight: 600;
    color: var(--el-text-color-primary);
    margin: 0 0 8px;
  }

  .page-description {
    color: var(--el-text-color-secondary);
    margin: 0;
  }
}

.balance-overview {
  margin-bottom: 20px;
}

.metric-card {
  text-align: center;
  padding: 8px 0;

  .metric-value {
    font-size: 28px;
    font-weight: 700;
    color: var(--el-text-color-primary);
    line-height: 1.4;

    &.primary {
      color: var(--el-color-primary);
    }
  }

  .metric-label {
    font-size: 14px;
    color: var(--el-text-color-secondary);
    margin-top: 4px;
  }
}

.pending-alert {
  margin-bottom: 20px;
}

.packages-card {
  margin-bottom: 20px;

  .card-header {
    display: flex;
    justify-content: space-between;
    align-items: center;

    .rate-hint {
      font-size: 13px;
      color: var(--el-text-color-secondary);
    }
  }
}

.package-item {
  border: 2px solid var(--el-border-color-light);
  border-radius: 8px;
  padding: 16px;
  text-align: center;
  cursor: pointer;
  transition: all 0.2s;
  margin-bottom: 16px;
  position: relative;

  &:hover {
    border-color: var(--el-color-primary-light-5);
  }

  &.active {
    border-color: var(--el-color-primary);
    background-color: var(--el-color-primary-light-9);
  }

  .package-tags {
    min-height: 22px;
    margin-bottom: 8px;
  }

  .package-amount {
    font-size: 28px;
    font-weight: 700;
    color: var(--el-text-color-primary);
  }

  .package-quota {
    font-size: 14px;
    color: var(--el-color-primary);
    margin-top: 4px;
  }

  .package-gift {
    font-size: 12px;
    color: var(--el-color-success);
    margin-top: 2px;
  }
}

.recharge-action {
  text-align: center;
  padding: 20px 0 4px;

  .recharge-btn {
    min-width: 240px;
    font-size: 16px;
    height: 44px;
  }
}

.confirm-content {
  .safety-endorsement {
    margin-bottom: 16px;
  }

  .gift-text {
    color: var(--el-color-success);
    font-weight: 600;
  }
}

.pay-status-content {
  text-align: center;
  padding: 20px 0;

  .qr-section {
    .qr-placeholder {
      width: 200px;
      height: 200px;
      margin: 0 auto 16px;
      border: 1px dashed var(--el-border-color);
      border-radius: 8px;
      display: flex;
      flex-direction: column;
      align-items: center;
      justify-content: center;
      color: var(--el-text-color-secondary);
    }

    .qr-tip {
      font-size: 13px;
      color: var(--el-text-color-secondary);
    }
  }

  .mweb-section {
    .mweb-tip {
      margin-top: 12px;
      font-size: 13px;
      color: var(--el-text-color-secondary);
    }
  }

  .success-section, .fail-section {
    h3 {
      margin: 16px 0 8px;
      color: var(--el-text-color-primary);
    }

    p {
      color: var(--el-text-color-secondary);
    }

    .support-line {
      margin-top: 10px;
      font-size: 13px;

      a {
        color: var(--el-color-primary);
        text-decoration: none;
      }
    }
  }
}

.page-footer {
  text-align: center;
  padding: 20px 0;

  a {
    color: var(--el-color-primary);
    text-decoration: none;

    &:hover {
      text-decoration: underline;
    }
  }
}
</style>
