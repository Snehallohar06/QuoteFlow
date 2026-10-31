import { api, cleanParams } from './client'

export async function listCustomers(params = {}) {
  const { data } = await api.get('/customers', {
    params: cleanParams({ page: 1, page_size: 20, ...params }),
  })
  return data
}

export async function getCustomer(id) {
  const { data } = await api.get(`/customers/${id}`)
  return data
}

export async function createCustomer(payload) {
  const { data } = await api.post('/customers', payload)
  return data
}

export async function updateCustomer(id, payload) {
  const { data } = await api.patch(`/customers/${id}`, payload)
  return data
}

/** Manager only. `status` is one of ACTIVE / ON_HOLD / BLOCKED. */
export async function setCustomerStatus(id, newStatus) {
  const { data } = await api.post(`/customers/${id}/status`, null, {
    params: { new_status: newStatus },
  })
  return data
}

/** Request and quotation activity roll-up for one customer. */
export async function getCustomerSummary(id) {
  const { data } = await api.get(`/customers/${id}/summary`)
  return data
}
