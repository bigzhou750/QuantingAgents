/**
 * Token 计费 Store
 * Options API 风格（与项目现有 store 一致）
 */
import { defineStore } from 'pinia'
import { tokenBillingApi, type AccountInfo, type PackageItem } from '@/api/tokenBilling'

export const useTokenBillingStore = defineStore('tokenBilling', {
  state: () => ({
    balance: 0 as number,
    frozen: 0 as number,
    totalRecharged: 0 as number,
    totalConsumed: 0 as number,
    totalGifted: 0 as number,
    packages: [] as PackageItem[],
    pendingOrder: null as any,
    balanceLoading: false,
    lastFetchedAt: null as string | null,
  }),

  getters: {
    /** 余额是否低于预警阈值（5元） */
    isLowBalance: (state) => state.balance < 5 && state.balance > 0,
    /** 余额是否为零 */
    isEmptyBalance: (state) => state.balance <= 0,
    /** 格式化余额显示 */
    balanceDisplay: (state) => `¥${state.balance.toFixed(3)}`,
  },

  actions: {
    /** 获取账户信息 */
    async fetchAccount() {
      this.balanceLoading = true
      try {
        const res = await tokenBillingApi.getAccount()
        if (res.success && res.data) {
          const account = res.data as unknown as AccountInfo
          this.balance = account.balance
          this.frozen = account.frozen
          this.totalRecharged = account.total_recharged
          this.totalConsumed = account.total_consumed
          this.totalGifted = account.total_gifted
          this.lastFetchedAt = new Date().toISOString()
        }
      } catch (error: any) {
        console.error('获取账户信息失败:', error)
      } finally {
        this.balanceLoading = false
      }
    },

    /** 获取套餐列表 */
    async fetchPackages() {
      try {
        const res = await tokenBillingApi.getPackages()
        if (res.success && res.data) {
          this.packages = (res.data as any).items || []
        }
      } catch (error: any) {
        console.error('获取套餐列表失败:', error)
      }
    },

    /** SSE推送的余额更新 */
    updateBalanceFromSSE(newBalance: number, newFrozen?: number) {
      this.balance = newBalance
      if (newFrozen !== undefined) {
        this.frozen = newFrozen
      }
      this.lastFetchedAt = new Date().toISOString()
    },

    /** 检查pending订单（中断恢复） */
    async checkPendingOrder() {
      try {
        const res = await tokenBillingApi.getPendingOrder()
        if (res.success && res.data) {
          this.pendingOrder = res.data
        } else {
          this.pendingOrder = null
        }
      } catch {
        this.pendingOrder = null
      }
    },

    /** 初始化（登录时调用） */
    async init() {
      await Promise.all([this.fetchAccount(), this.fetchPackages(), this.checkPendingOrder()])
    },
  },
})
