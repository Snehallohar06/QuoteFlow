import { api, tokenStore } from './client'

export async function login(email, password) {
  const { data } = await api.post(
    '/auth/login',
    { email, password },
    { skipAuth: true }
  )
  tokenStore.set(data)
  return data
}

export async function register(payload) {
  const { data } = await api.post('/auth/register', payload, { skipAuth: true })
  tokenStore.set(data)
  return data
}

/** `{ user, customer }` — customer is null for staff accounts. */
export async function getProfile() {
  const { data } = await api.get('/auth/me')
  return data
}

export async function changePassword(current_password, new_password) {
  await api.post('/auth/change-password', { current_password, new_password })
}

export async function createStaffUser(payload) {
  const { data } = await api.post('/auth/staff', payload)
  return data
}

export function logout() {
  tokenStore.clear()
}
