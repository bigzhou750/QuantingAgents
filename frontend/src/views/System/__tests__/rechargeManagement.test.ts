// @vitest-environment happy-dom

import { beforeEach, describe, expect, it, vi } from 'vitest'
import { flushPromises } from '@vue/test-utils'
import { tokenBillingApi } from '@/api/tokenBilling'
import type { AdminTransactionItem } from '@/api/tokenBilling'

vi.mock('@/api/tokenBilling', () => ({
  tokenBillingApi: {
    adminGetTransactions: vi.fn()
  }
}))

const RECORD: AdminTransactionItem = {
  txn_id: 'ADM_20260914000001',
  user_id: 'u1',
  order_id: null,
  type: 'admin_recharge',
  direction: 'in',
  amount: 5,
  balance_before: 0,
  balance_after: 5,
  metadata: {
    source: 'admin_recharge',
    username: 'bob',
    email: 'bob@example.com',
    operator_username: 'admin',
    reason: '运营补偿'
  },
  status: 'success',
  related_txn_id: null,
  created_at: '2026-09-14T10:00:00+08:00'
}

describe('RechargeManagement.vue', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  const mountPage = async () => {
    vi.stubGlobal('navigator', { userAgent: 'vitest' })
    class Observer {
      observe() {}
      disconnect() {}
      unobserve() {}
      takeRecords() {
        return []
      }
    }
    vi.stubGlobal('MutationObserver', Observer)
    vi.stubGlobal('ResizeObserver', Observer)
    const ElementPlus = (await import('element-plus')).default
    const { mount } = await import('@vue/test-utils')
    const { default: RechargeManagement } = await import('../RechargeManagement.vue')
    const wrapper = mount(RechargeManagement, {
      global: {
        plugins: [ElementPlus]
      }
    })
    await flushPromises()
    return wrapper
  }

  it('renders recharge records with traceability metadata', async () => {
    vi.mocked(tokenBillingApi.adminGetTransactions).mockResolvedValue({
      success: true,
      data: { items: [RECORD], total: 1, page: 1, page_size: 20 },
      message: ''
    })

    const wrapper = await mountPage()

    expect(wrapper.text()).toContain('充值记录')
    expect(wrapper.text()).toContain('bob')
    expect(wrapper.text()).toContain('管理员充值')
    expect(wrapper.text()).toContain('admin')
    expect(wrapper.text()).toContain('运营补偿')
  })

  it('sends keyword and page parameters on search', async () => {
    vi.mocked(tokenBillingApi.adminGetTransactions).mockResolvedValue({
      success: true,
      data: { items: [RECORD], total: 1, page: 1, page_size: 20 },
      message: ''
    })

    const wrapper = await mountPage()
    const input = wrapper.find('input[placeholder="用户名 / 邮箱 / 用户ID / 流水号 / 订单号"]')
    await input.setValue('bob')

    const searchButton = wrapper.findAll('button').find((button) => button.text().includes('查询'))
    await searchButton?.trigger('click')
    await flushPromises()

    expect(tokenBillingApi.adminGetTransactions).toHaveBeenLastCalledWith(
      expect.objectContaining({ keyword: 'bob', page: 1, page_size: 20 })
    )
  })
})
