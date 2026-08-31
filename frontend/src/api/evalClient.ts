import { ApiClient } from './request'

type RequestConfig = Record<string, any>

export const evalApiClient = {
  async get(url: string, config?: RequestConfig) {
    return { data: await ApiClient.get(url, config?.params, config) }
  },

  async post(url: string, data?: any, config?: RequestConfig) {
    return { data: await ApiClient.post(url, data, config) }
  },

  async put(url: string, data?: any, config?: RequestConfig) {
    return { data: await ApiClient.put(url, data, config) }
  },

  async delete(url: string, config?: RequestConfig) {
    return { data: await ApiClient.delete(url, config) }
  },
}
