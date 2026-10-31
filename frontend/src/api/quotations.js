import { api, cleanParams, tokenStore, API_ORIGIN } from './client'

export async function listQuotations(params = {}) {
  const { data } = await api.get('/quotations', {
    params: cleanParams({ page: 1, page_size: 20, ...params }),
  })
  return data
}

export async function getQuotation(id) {
  const { data } = await api.get(`/quotations/${id}`)
  return data
}

/**
 * Download the PDF.
 *
 * The endpoint needs the bearer token, so a plain anchor href will not do —
 * the file is fetched as a blob and handed to the browser through a temporary
 * object URL.
 */
export async function downloadQuotationPdf(id, quotationNumber) {
  const response = await api.get(`/quotations/${id}/pdf`, {
    responseType: 'blob',
  })

  const blob = new Blob([response.data], { type: 'application/pdf' })
  const url = URL.createObjectURL(blob)
  const link = document.createElement('a')
  link.href = url
  link.download = `${quotationNumber || 'quotation'}.pdf`
  document.body.appendChild(link)
  link.click()
  link.remove()
  // Revoke on the next tick so the download has started.
  setTimeout(() => URL.revokeObjectURL(url), 1000)
}

/** Opens the PDF in a new tab instead of saving it. */
export async function openQuotationPdf(id) {
  const response = await api.get(`/quotations/${id}/pdf`, { responseType: 'blob' })
  const blob = new Blob([response.data], { type: 'application/pdf' })
  const url = URL.createObjectURL(blob)
  window.open(url, '_blank', 'noopener')
  setTimeout(() => URL.revokeObjectURL(url), 60000)
}

export async function setQuotationStatus(id, newStatus) {
  const { data } = await api.post(`/quotations/${id}/status`, null, {
    params: { new_status: newStatus },
  })
  return data
}

export async function expireDueQuotations() {
  const { data } = await api.post('/quotations/expire-due')
  return data.expired
}

/**
 * Public verification. Deliberately sent without a token: this is the same
 * unauthenticated call a quotation recipient would make.
 */
export async function verifyQuotation(code) {
  const { data } = await api.get(`/verify/${encodeURIComponent(code)}`, {
    skipAuth: true,
  })
  return data
}

export { tokenStore, API_ORIGIN }
