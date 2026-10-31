import { api, cleanParams } from './client'

/** Manager only. The trail is read-only — there is no write endpoint. */
export async function listAuditLogs(params = {}) {
  const { data } = await api.get('/audit-logs', {
    params: cleanParams({ page: 1, page_size: 25, ...params }),
  })
  return data
}

/** Full chronological history for one entity, oldest first. */
export async function getEntityTrail(entityType, entityId) {
  const { data } = await api.get(`/audit-logs/${entityType}/${entityId}`)
  return data
}

/** Actions the filter dropdown offers, matching the backend's AuditAction enum. */
export const AUDIT_ACTIONS = [
  'USER_REGISTERED',
  'USER_LOGGED_IN',
  'CUSTOMER_CREATED',
  'CUSTOMER_UPDATED',
  'PRODUCT_CREATED',
  'PRODUCT_UPDATED',
  'PRODUCT_DELETED',
  'REQUEST_CREATED',
  'REQUEST_UPDATED',
  'REQUEST_SUBMITTED',
  'REQUEST_CANCELLED',
  'WORKFLOW_EXECUTED',
  'APPROVAL_DECIDED',
  'QUOTATION_GENERATED',
  'QUOTATION_DOWNLOADED',
  'QUOTATION_VERIFIED',
  'SETTINGS_UPDATED',
]

export const AUDIT_ENTITY_TYPES = [
  'user',
  'customer',
  'product',
  'quotation_request',
  'approval',
  'quotation',
  'company_settings',
]
