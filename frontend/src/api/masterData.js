/**
 * Master-data authorisation: a sales employee proposes a customer or product,
 * a sales manager decides.
 *
 * A sales employee has no write access to `/customers` or `/products`; the
 * backend refuses it. These calls are the route they use instead.
 */

import { api, cleanParams } from './client'

export async function listRequests(params = {}) {
  const { data } = await api.get('/master-data-requests', {
    params: cleanParams({ page: 1, page_size: 20, ...params }),
  })
  return data
}

export async function getPendingCount() {
  const { data } = await api.get('/master-data-requests/pending-count')
  return data.pending
}

export async function getRequest(id) {
  const { data } = await api.get(`/master-data-requests/${id}`)
  return data
}

/** `customer` is the same payload `POST /customers` takes. */
export async function submitCustomer(customer, reason) {
  const { data } = await api.post('/master-data-requests/customers', {
    customer,
    reason: reason || undefined,
  })
  return data
}

/** `product` is the same payload `POST /products` takes. */
export async function submitProduct(product, reason) {
  const { data } = await api.post('/master-data-requests/products', {
    product,
    reason: reason || undefined,
  })
  return data
}

/**
 * Manager only. Approving creates the record; refusing requires a reason, and
 * the backend rejects a blank one rather than recording a silent refusal.
 */
export async function decide(id, { approve, comments }) {
  const { data } = await api.post(`/master-data-requests/${id}/decision`, {
    approve,
    comments: comments || undefined,
  })
  return data
}

/** Withdraw a request you raised yourself, while it is still open. */
export async function withdraw(id) {
  const { data } = await api.post(`/master-data-requests/${id}/withdraw`)
  return data
}
