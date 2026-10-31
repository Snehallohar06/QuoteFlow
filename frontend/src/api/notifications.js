import { api, cleanParams } from './client'

export async function listNotifications(params = {}) {
  const { data } = await api.get('/notifications', {
    params: cleanParams({ page: 1, page_size: 20, ...params }),
  })
  return data
}

export async function getUnreadCount() {
  const { data } = await api.get('/notifications/unread-count')
  return data.unread
}

export async function markRead(id) {
  const { data } = await api.post(`/notifications/${id}/read`)
  return data
}

export async function markAllRead() {
  const { data } = await api.post('/notifications/read-all')
  return data.updated
}
