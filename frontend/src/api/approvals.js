import { api, cleanParams } from './client'

export async function listApprovals(params = {}) {
  const { data } = await api.get('/approvals', {
    params: cleanParams({ page: 1, page_size: 20, ...params }),
  })
  return data
}

export async function getPendingCount() {
  const { data } = await api.get('/approvals/pending-count')
  return data.pending
}

/**
 * The decision screen's whole payload in one read:
 * `{ approval, request, customer, latest_execution, recent_quotations }`.
 */
export async function getApproval(id) {
  const { data } = await api.get(`/approvals/${id}`)
  return data
}

/**
 * Record a manager decision.
 *
 * `decision` is APPROVE | REJECT | REQUEST_MODIFICATION. A comment is required
 * for the latter two; `override_discount_percent` may only accompany APPROVE.
 */
export async function decide(id, { decision, comments, override_discount_percent }) {
  const payload = { decision }
  if (comments) payload.comments = comments
  if (override_discount_percent !== undefined && override_discount_percent !== null) {
    payload.override_discount_percent = override_discount_percent
  }
  const { data } = await api.post(`/approvals/${id}/decision`, payload)
  return data
}
