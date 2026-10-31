import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { Bell, BellOff, CheckCheck, RefreshCw } from 'lucide-react'

import { useToast } from '../../context/ToastContext'
import { useAsync } from '../../hooks/useAsync'
import * as notificationsApi from '../../api/notifications'
import { PageHeader } from '../../components/layout/PageHeader'
import { Button } from '../../components/ui/Button'
import { Card } from '../../components/ui/Card'
import { Badge } from '../../components/ui/Badge'
import { Checkbox } from '../../components/ui/Field'
import {
  EmptyState,
  ErrorState,
  Pagination,
  Spinner,
} from '../../components/ui/Table'
import { formatDateTime, formatRelative, humanise } from '../../lib/format'
import { notificationInfo } from '../../lib/status'

/** Where a notification's entity lives in the app. */
function targetFor(notification) {
  if (!notification.entity_id) return null
  if (notification.entity_type === 'quotation_request') {
    return `/requests/${notification.entity_id}`
  }
  if (notification.entity_type === 'quotation') {
    return `/quotations/${notification.entity_id}`
  }
  return null
}

export function Notifications() {
  const toast = useToast()
  const navigate = useNavigate()

  const [unreadOnly, setUnreadOnly] = useState(false)
  const [page, setPage] = useState(1)
  const [busy, setBusy] = useState(null)

  const notifications = useAsync(
    () =>
      notificationsApi.listNotifications({
        page,
        page_size: 20,
        unread_only: unreadOnly || undefined,
      }),
    [page, unreadOnly]
  )

  const items = notifications.data?.items ?? []
  const unreadCount = items.filter((item) => !item.read).length

  async function open(notification) {
    const target = targetFor(notification)
    if (!notification.read) {
      try {
        await notificationsApi.markRead(notification.id)
        notifications.reload()
      } catch {
        /* Navigation matters more than the read flag; ignore a failure here. */
      }
    }
    if (target) navigate(target)
  }

  async function markOne(notification, event) {
    event.stopPropagation()
    setBusy(notification.id)
    try {
      await notificationsApi.markRead(notification.id)
      notifications.reload()
    } catch (error) {
      toast.fromError(error, 'Could not mark it read')
    } finally {
      setBusy(null)
    }
  }

  async function markAll() {
    setBusy('all')
    try {
      const updated = await notificationsApi.markAllRead()
      toast.success(
        updated > 0 ? `${updated} marked read` : 'Nothing unread',
        updated > 0 ? 'Your inbox is clear.' : undefined
      )
      notifications.reload()
    } catch (error) {
      toast.fromError(error, 'Could not mark everything read')
    } finally {
      setBusy(null)
    }
  }

  return (
    <>
      <PageHeader
        title="Notifications"
        description="Raised automatically by the workflow and approval engine."
        actions={
          <>
            <Button variant="secondary" icon={RefreshCw} onClick={notifications.reload}>
              Refresh
            </Button>
            <Button
              icon={CheckCheck}
              loading={busy === 'all'}
              disabled={unreadCount === 0}
              onClick={markAll}
            >
              Mark all read
            </Button>
          </>
        }
      />

      <Card>
        <div className="flex flex-wrap items-center gap-3 border-b border-slate-200 px-4 py-3 sm:px-5">
          <Checkbox
            label="Unread only"
            checked={unreadOnly}
            onChange={(event) => {
              setUnreadOnly(event.target.checked)
              setPage(1)
            }}
          />
          <span className="ml-auto text-[12.5px] text-slate-500">
            {notifications.loading
              ? 'Loading…'
              : `${notifications.data?.meta?.total ?? 0} notification(s)`}
          </span>
        </div>

        {notifications.error ? (
          <ErrorState error={notifications.error} onRetry={notifications.reload} />
        ) : notifications.loading ? (
          <div className="px-4 py-10 text-center sm:px-5">
            <Spinner label="Loading notifications" />
          </div>
        ) : items.length === 0 ? (
          <EmptyState
            icon={unreadOnly ? BellOff : Bell}
            title={unreadOnly ? 'Nothing unread' : 'No notifications yet'}
            description={
              unreadOnly
                ? 'You have read everything in your inbox.'
                : 'The system notifies you when a request is priced, escalated or decided.'
            }
            action={
              unreadOnly ? (
                <Button variant="secondary" size="sm" onClick={() => setUnreadOnly(false)}>
                  Show all
                </Button>
              ) : null
            }
          />
        ) : (
          <ul className="divide-y divide-slate-100">
            {items.map((notification) => {
              const info = notificationInfo(notification.type)
              const Icon = info.icon
              const target = targetFor(notification)

              return (
                <li
                  key={notification.id}
                  role={target ? 'button' : undefined}
                  tabIndex={target ? 0 : undefined}
                  onClick={target ? () => open(notification) : undefined}
                  onKeyDown={
                    target
                      ? (event) => {
                          if (event.key === 'Enter') open(notification)
                        }
                      : undefined
                  }
                  className={`flex gap-3 px-4 py-3.5 transition sm:px-5 ${
                    notification.read ? '' : 'bg-brand-50/40'
                  } ${target ? 'cursor-pointer hover:bg-brand-50/70' : ''}`}
                >
                  <span
                    className={`mt-0.5 grid h-8 w-8 shrink-0 place-items-center rounded-full ${
                      info.tone === 'success'
                        ? 'bg-emerald-50 text-emerald-600'
                        : info.tone === 'danger'
                          ? 'bg-rose-50 text-rose-600'
                          : info.tone === 'warning'
                            ? 'bg-amber-50 text-amber-600'
                            : 'bg-brand-50 text-brand-600'
                    }`}
                  >
                    <Icon size={15} aria-hidden="true" />
                  </span>

                  <div className="min-w-0 flex-1">
                    <div className="flex flex-wrap items-center gap-2">
                      <p
                        className={`text-[13.5px] ${
                          notification.read
                            ? 'font-medium text-slate-700'
                            : 'font-semibold text-slate-900'
                        }`}
                      >
                        {notification.title}
                      </p>
                      {!notification.read ? (
                        <Badge tone="info" size="sm">
                          New
                        </Badge>
                      ) : null}
                      <Badge tone="neutral" size="sm">
                        {humanise(notification.type)}
                      </Badge>
                    </div>
                    <p className="mt-0.5 text-[12.5px] leading-snug text-slate-600">
                      {notification.message}
                    </p>
                    <p
                      className="mt-1 text-[11px] text-slate-400"
                      title={formatDateTime(notification.created_at)}
                    >
                      {formatRelative(notification.created_at)}
                      {notification.read && notification.read_at
                        ? ` · read ${formatRelative(notification.read_at)}`
                        : ''}
                    </p>
                  </div>

                  {!notification.read ? (
                    <Button
                      variant="ghost"
                      size="sm"
                      loading={busy === notification.id}
                      onClick={(event) => markOne(notification, event)}
                      className="shrink-0 self-center"
                    >
                      Mark read
                    </Button>
                  ) : null}
                </li>
              )
            })}
          </ul>
        )}

        <Pagination meta={notifications.data?.meta} onPageChange={setPage} />
      </Card>
    </>
  )
}
