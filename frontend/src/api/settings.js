import { api } from './client'

/** The whole rule book. Readable by every role. */
export async function getSettings() {
  const { data } = await api.get('/settings')
  return data
}

/** Tier table and ceilings on their own, for the catalogue and request form. */
export async function getDiscountPolicy() {
  const { data } = await api.get('/settings/discount-policy')
  return data
}

/**
 * Partial update, manager only.
 *
 * Nested objects are merged field by field by the backend; lists such as the
 * discount tier table are replaced wholesale. An invalid patch is rejected with
 * a 422 before anything is written.
 */
export async function updateSettings(patch) {
  const { data } = await api.patch('/settings', patch)
  return data
}
