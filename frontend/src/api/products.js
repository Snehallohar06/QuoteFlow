import { api, cleanParams } from './client'

/** Customer-facing catalogue: no cost price, plus the viewer's discount cap. */
export async function listCatalogue(params = {}) {
  const { data } = await api.get('/products/catalogue', {
    params: cleanParams({ page: 1, page_size: 12, ...params }),
  })
  return data
}

/** Internal product list, including cost price. Staff only. */
export async function listProducts(params = {}) {
  const { data } = await api.get('/products', {
    params: cleanParams({ page: 1, page_size: 20, ...params }),
  })
  return data
}

export async function listCategories() {
  const { data } = await api.get('/products/categories')
  return data
}

export async function getProduct(id) {
  const { data } = await api.get(`/products/${id}`)
  return data
}

export async function createProduct(payload) {
  const { data } = await api.post('/products', payload)
  return data
}

export async function updateProduct(id, payload) {
  const { data } = await api.patch(`/products/${id}`, payload)
  return data
}

export async function adjustStock(id, delta, reason) {
  const { data } = await api.post(`/products/${id}/stock`, { delta, reason })
  return data
}

export async function discontinueProduct(id) {
  const { data } = await api.delete(`/products/${id}`)
  return data
}

/** Pre-flight stock check for a set of lines, before submitting a request. */
export async function checkAvailability(items) {
  const { data } = await api.post('/products/check-availability', { items })
  return data
}
