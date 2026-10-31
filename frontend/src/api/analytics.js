import { api, cleanParams } from './client'

/** Every dashboard section in one call. Manager only. */
export async function getDashboard(days = 30) {
  const { data } = await api.get('/analytics/dashboard', { params: { days } })
  return data
}

/** Headline KPIs. Available to employees as well as managers. */
export async function getOverview(days = 30) {
  const { data } = await api.get('/analytics/overview', { params: { days } })
  return data
}

export async function getRequestTrend(days = 30) {
  const { data } = await api.get('/analytics/requests/trend', { params: { days } })
  return data
}

export async function getRevenueTrend(days = 90) {
  const { data } = await api.get('/analytics/revenue/trend', { params: { days } })
  return data
}

export async function getTopProducts(params = {}) {
  const { data } = await api.get('/analytics/products/top', {
    params: cleanParams({ days: 30, limit: 10, ...params }),
  })
  return data
}

export async function getTopCustomers(params = {}) {
  const { data } = await api.get('/analytics/customers/top', {
    params: cleanParams({ days: 30, limit: 10, ...params }),
  })
  return data
}

export async function getExceptionBreakdown(days = 30) {
  const { data } = await api.get('/analytics/exceptions', { params: { days } })
  return data
}

export async function getApprovalPerformance(days = 30) {
  const { data } = await api.get('/analytics/approvals/performance', {
    params: { days },
  })
  return data
}

export async function getWorkflowPerformance(days = 30) {
  const { data } = await api.get('/analytics/workflow/performance', {
    params: { days },
  })
  return data
}
