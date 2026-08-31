import { ApiClient } from './request'

export const investmentApi = {
  getProfile() {
    return ApiClient.get('/api/investment/profile')
  },
  updateProfile(data: Record<string, unknown>) {
    return ApiClient.put('/api/investment/profile', data)
  },
  listStrategies() {
    return ApiClient.get('/api/investment/strategies')
  },
  createStrategy(data: Record<string, unknown>) {
    return ApiClient.post('/api/investment/strategies', data)
  },
  updateStrategy(strategyId: string, data: Record<string, unknown>) {
    return ApiClient.put(`/api/investment/strategies/${strategyId}`, data)
  },
  toggleStrategy(strategyId: string, action: 'enable' | 'disable') {
    return ApiClient.post(`/api/investment/strategies/${strategyId}/${action}`)
  },
  createTask(type: 'screening' | 'checkup', data: Record<string, unknown>) {
    const endpoint = type === 'screening' ? 'screening-tasks' : 'checkup-tasks'
    return ApiClient.post(`/api/investment/${endpoint}`, data)
  },
  getTask(taskId: string) {
    return ApiClient.get(`/api/investment/tasks/${taskId}`)
  },
  getTaskResult(type: 'screening' | 'checkup', taskId: string) {
    const endpoint = type === 'screening' ? 'screening-tasks' : 'checkup-tasks'
    return ApiClient.get(`/api/investment/${endpoint}/${taskId}/result`)
  },
}
