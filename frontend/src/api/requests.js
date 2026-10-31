import { api, cleanParams } from './client'

/**
 * Customers see only their own requests; staff see every request and can
 * filter. The backend applies the scoping, not the client.
 */
export async function listRequests(params = {}) {
  const { data } = await api.get('/quotation-requests', {
    params: cleanParams({ page: 1, page_size: 20, ...params }),
  })
  return data
}

export async function getRequest(id) {
  const { data } = await api.get(`/quotation-requests/${id}`)
  return data
}

/**
 * Create a request.
 *
 * With `submit: true` (the default) the backend runs the whole workflow and
 * returns `{submitted: true, workflow: {...}}`, so one call tells us whether
 * the quotation is ready or waiting on a manager. With `submit: false` it
 * returns `{submitted: false, request: {...}}` for a saved draft.
 */
export async function createRequest(payload) {
  const { data } = await api.post('/quotation-requests', payload)
  return data
}

export async function updateRequest(id, payload) {
  const { data } = await api.patch(`/quotation-requests/${id}`, payload)
  return data
}

/** Runs the pipeline. Returns the workflow result. */
export async function submitRequest(id) {
  const { data } = await api.post(`/quotation-requests/${id}/submit`)
  return data
}

/** Staff re-run, for requests that failed on stale stock or catalogue data. */
export async function reprocessRequest(id) {
  const { data } = await api.post(`/quotation-requests/${id}/reprocess`)
  return data
}

export async function cancelRequest(id, reason) {
  const { data } = await api.post(`/quotation-requests/${id}/cancel`, { reason })
  return data
}

export async function setInternalNotes(id, internal_notes) {
  const { data } = await api.put(`/quotation-requests/${id}/internal-notes`, {
    internal_notes,
  })
  return data
}

/** Every pipeline run for one request, newest first, with per-step detail. */
export async function listExecutions(id) {
  const { data } = await api.get(`/quotation-requests/${id}/executions`)
  return data
}
