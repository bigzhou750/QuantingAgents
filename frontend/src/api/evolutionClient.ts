import { ApiClient } from './request'

export const evolutionApi = {
  // Config
  async getConfig() {
    return { data: await ApiClient.get('/api/evolution/config') }
  },
  async updateConfig(data: any) {
    return { data: await ApiClient.put('/api/evolution/config', data) }
  },

  // Artifacts
  async getArtifacts(params?: Record<string, any>) {
    return { data: await ApiClient.get('/api/evolution/artifacts', params) }
  },
  async registerArtifact(data: any) {
    return { data: await ApiClient.post('/api/evolution/artifacts', data) }
  },
  async getArtifact(artifactId: string) {
    return { data: await ApiClient.get(`/api/evolution/artifacts/${artifactId}`) }
  },
  async getArtifactVersions(artifactId: string, params?: Record<string, any>) {
    return { data: await ApiClient.get(`/api/evolution/artifacts/${artifactId}/versions`, params) }
  },
  async getArtifactReleaseHistory(artifactId: string) {
    return { data: await ApiClient.get(`/api/evolution/artifacts/${artifactId}/release-history`) }
  },
  async rollbackArtifact(artifactId: string, data: any) {
    return { data: await ApiClient.post(`/api/evolution/artifacts/${artifactId}/rollback`, data) }
  },

  // Proposals
  async getProposals(params?: Record<string, any>) {
    return { data: await ApiClient.get('/api/evolution/proposals', params) }
  },
  async getProposal(proposalId: string) {
    return { data: await ApiClient.get(`/api/evolution/proposals/${proposalId}`) }
  },
  async verifyProposal(proposalId: string) {
    return { data: await ApiClient.post(`/api/evolution/proposals/${proposalId}/verify`) }
  },
  async getVerification(proposalId: string) {
    return { data: await ApiClient.get(`/api/evolution/proposals/${proposalId}/verification`) }
  },

  // Approval
  async approveProposal(proposalId: string, data?: any) {
    return { data: await ApiClient.post(`/api/evolution/proposals/${proposalId}/approve`, data || {}) }
  },
  async rejectProposal(proposalId: string, data?: any) {
    return { data: await ApiClient.post(`/api/evolution/proposals/${proposalId}/reject`, data || {}) }
  },
  async commentProposal(proposalId: string, data: any) {
    return { data: await ApiClient.post(`/api/evolution/proposals/${proposalId}/comment`, data) }
  },
  async getAuditTrail(proposalId: string) {
    return { data: await ApiClient.get(`/api/evolution/proposals/${proposalId}/audit`) }
  },

  // Promote / Stop
  async promoteProposal(proposalId: string) {
    return { data: await ApiClient.post(`/api/evolution/proposals/${proposalId}/promote`) }
  },
  async stopProposal(proposalId: string, data?: any) {
    return { data: await ApiClient.post(`/api/evolution/proposals/${proposalId}/stop`, data || { reason: 'manual' }) }
  },

  // Receipts
  async getReceipts(params?: Record<string, any>) {
    return { data: await ApiClient.get('/api/evolution/receipts', params) }
  },
  async getReceipt(receiptId: string) {
    return { data: await ApiClient.get(`/api/evolution/receipts/${receiptId}`) }
  },

  // Stats & Audit
  async getStats() {
    return { data: await ApiClient.get('/api/evolution/stats') }
  },
  async getAuditLog(params?: Record<string, any>) {
    return { data: await ApiClient.get('/api/evolution/audit-log', params) }
  },
  async getFollowUpActions(params?: Record<string, any>) {
    return { data: await ApiClient.get('/api/evolution/follow-up-actions', params) }
  },
}
