// @vitest-environment happy-dom

import { beforeEach, describe, expect, it, vi } from 'vitest'
import { flushPromises } from '@vue/test-utils'
import { evolutionApi } from '@/api/evolutionClient'

vi.mock('@/api/evolutionClient', () => ({
  evolutionApi: {
    getReceipts: vi.fn(),
    getFollowUpActions: vi.fn(),
    observePostRelease: vi.fn()
  }
}))

describe('PostReleaseObservation.vue', () => {
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
    const { default: PostReleaseObservation } = await import('../PostReleaseObservation.vue')
    const wrapper = mount(PostReleaseObservation, {
      global: {
        plugins: [ElementPlus]
      }
    })
    await flushPromises()
    return wrapper
  }

  it('renders receipts, follow-up actions and submits observation', async () => {
    vi.mocked(evolutionApi.getReceipts).mockResolvedValue({
      success: true,
      data: { items: [{ receipt_id: 'receipt_1' }] },
      message: ''
    })
    vi.mocked(evolutionApi.getFollowUpActions).mockResolvedValue({
      success: true,
      data: {
        items: [
          {
            action_id: 'action_1',
            action_type: 'bad_case',
            status: 'pending',
            severity: 'warning'
          }
        ]
      },
      message: ''
    })
    vi.mocked(evolutionApi.observePostRelease).mockResolvedValue({
      success: true,
      data: {
        passed: true,
        rollback_suggestion: false,
        failures: []
      },
      message: ''
    })

    const wrapper = await mountPage()
    expect(wrapper.text()).toContain('发布后观测')
    expect(wrapper.text()).toContain('action_1')

    const submitButton = wrapper.findAll('button').find((button) => button.text().includes('提交观测'))
    await submitButton?.trigger('click')
    await flushPromises()

    expect(vi.mocked(evolutionApi.observePostRelease)).toHaveBeenCalledTimes(1)
    expect(wrapper.text()).toContain('观测通过')
  })
})
