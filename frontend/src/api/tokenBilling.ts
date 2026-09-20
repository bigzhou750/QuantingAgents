/**
 * 算力充值计费 API
 */
import { ApiClient } from './request'

// ==================== 类型定义 ====================

export interface AccountInfo {
  balance: number
  frozen: number
  total_recharged: number
  total_consumed: number
  total_gifted: number
  created_at: string
  updated_at: string
}

export interface PackageItem {
  package_id: string
  name: string
  amount_cny: number
  sort_order: number
  enabled: boolean
  tags: string[]
  quota_to_credit: number
  gift_amount: number
}

export interface RechargeOrderResult {
  order_id: string
  amount: number
  quota_to_credit: number
  gift_amount: number
  pay_type: 'NATIVE' | 'JSAPI' | 'MWEB'
  pay_params: Record<string, any>
  expire_at: string
  status: string
}

export interface OrderStatus {
  order_id: string
  status: string
  amount: number
  quota_to_credit: number
  pay_type: string
  created_at: string
  credited_at: string | null
  expire_at: string
}

export interface TransactionItem {
  txn_id: string
  type: string
  direction: string
  amount: number
  balance_before: number
  balance_after: number
  metadata: Record<string, any>
  status: string
  order_id: string | null
  related_txn_id: string | null
  created_at: string
}

export interface TransactionList {
  items: TransactionItem[]
  total: number
  page: number
  page_size: number
}

export interface AdminTransactionItem extends TransactionItem {
  metadata: Record<string, any> & {
    source?: string
    reason?: string
    username?: string
    email?: string
    operator_username?: string
    operator_user_id?: string
  }
}

export interface AdminTransactionList {
  items: AdminTransactionItem[]
  total: number
  page: number
  page_size: number
}

export interface AdminRechargePayload {
  username?: string
  user_id?: string
  amount: number
  reason?: string
}

export interface AdminRechargeResult {
  account: AccountInfo
  transaction: {
    txn_id: string
    amount: number
    balance_after: number
  }
}

export interface BillingConfig {
  consumption_ratio: number
  input_price: number
  output_price: number
  exchange_rate: number
  preoccupy_ratio: number
  warn_threshold_mq: number
  order_expire_minutes: number
}

// ==================== API ====================

export const tokenBillingApi = {
  /** 获取账户信息 */
  async getAccount() {
    return ApiClient.get<{ data: AccountInfo }>('/api/token-billing/account')
  },

  /** 获取套餐列表 */
  async getPackages() {
    return ApiClient.get<{ data: { items: PackageItem[] } }>('/api/token-billing/packages')
  },

  /** 创建充值订单（禁止重试！） */
  async createOrder(data: {
    package_id?: string
    custom_amount?: number
    idempotency_key: string
  }) {
    return ApiClient.post<{ data: RechargeOrderResult }>(
      '/api/token-billing/orders',
      data,
      { retryCount: 0 }
    )
  },

  /** 查询订单状态 */
  async getOrderStatus(orderId: string) {
    return ApiClient.get<{ data: OrderStatus }>(`/api/token-billing/orders/${orderId}`)
  },

  /** 获取pending订单（中断恢复） */
  async getPendingOrder() {
    return ApiClient.get<{ data: any }>('/api/token-billing/orders/pending')
  },

  /** 恢复支付：为过期的 Waffo 订单重新创建 checkout session */
  async resumePayment(orderId: string) {
    return ApiClient.post<{ data: { checkout_url: string; session_id: string; expires_at: string } }>(
      `/api/token-billing/orders/${orderId}/resume`,
      {},
      { retryCount: 0 }
    )
  },

  /** 主动查询微信订单 */
  async queryWxOrder(orderId: string) {
    return ApiClient.post<{ data: any }>(`/api/token-billing/orders/${orderId}/query-wx`)
  },

  /** 分页查询交易流水 */
  async getTransactions(params: {
    type?: string
    start_date?: string
    end_date?: string
    page?: number
    page_size?: number
  }) {
    return ApiClient.get<{ data: TransactionList }>('/api/token-billing/transactions', params)
  },

  /** 导出交易流水CSV */
  async exportTransactions(params?: {
    type?: string
    start_date?: string
    end_date?: string
  }) {
    return ApiClient.download(
      '/api/token-billing/transactions/export',
      'transactions.csv',
      { params }
    )
  },

  // ==================== Admin ====================

  /** 获取计费配置 */
  async getBillingConfig() {
    return ApiClient.get<{ data: BillingConfig }>('/api/token-billing/billing-config')
  },

  /** 更新计费配置 */
  async updateBillingConfig(data: Partial<BillingConfig>) {
    return ApiClient.put<{ data: any }>('/api/token-billing/billing-config', data)
  },

  /** 更新套餐 */
  async updatePackages(packages: PackageItem[]) {
    return ApiClient.put<{ data: any }>('/api/token-billing/packages', { packages })
  },

  /** 手动触发对账 */
  async reconcile() {
    return ApiClient.post<{ data: any }>('/api/token-billing/reconcile')
  },

  /** 管理员充值算力 */
  async adminRecharge(data: AdminRechargePayload) {
    return ApiClient.post<AdminRechargeResult>(
      '/api/token-billing/admin/recharge',
      data
    )
  },

  /** 管理员查询用户算力账户（用户名或用户ID） */
  async adminGetUserAccount(target: string) {
    return ApiClient.get<AccountInfo>(
      `/api/token-billing/admin/users/${encodeURIComponent(target)}/account`
    )
  },

  /** 管理员分页查询充值记录 */
  async adminGetTransactions(params: {
    user_id?: string
    type?: string
    keyword?: string
    start_date?: string
    end_date?: string
    page?: number
    page_size?: number
  }) {
    return ApiClient.get<AdminTransactionList>(
      '/api/token-billing/admin/transactions',
      params
    )
  },
}
