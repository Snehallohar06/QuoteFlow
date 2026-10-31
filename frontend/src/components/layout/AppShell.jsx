import { useCallback, useEffect, useRef, useState } from 'react'
import { Outlet, useLocation } from 'react-router-dom'

import { useAuth } from '../../context/AuthContext'
import * as notificationsApi from '../../api/notifications'
import * as approvalsApi from '../../api/approvals'
import * as masterDataApi from '../../api/masterData'
import * as requestsApi from '../../api/requests'
import { Sidebar } from './Sidebar'
import { Topbar } from './Topbar'

/** How often the sidebar badges re-poll, in milliseconds. */
const BADGE_POLL_MS = 60000

/**
 * The authenticated application frame: sidebar, top bar and the routed page.
 *
 * It also owns the badge counts, because they appear in both the sidebar and
 * the top bar and should be fetched once rather than per consumer.
 */
export function AppShell() {
  const { isStaff, isManager } = useAuth()
  const location = useLocation()

  const [sidebarOpen, setSidebarOpen] = useState(false)
  const [notifications, setNotifications] = useState([])
  const [badges, setBadges] = useState({
    unread: 0,
    pending: 0,
    exceptions: 0,
    masterData: 0,
  })
  const mounted = useRef(true)

  useEffect(() => {
    mounted.current = true
    return () => {
      mounted.current = false
    }
  }, [])

  const loadBadges = useCallback(async () => {
    // Each count is independent; one failing must not blank the others, and a
    // 403 for a role that cannot see a figure is expected, not an error.
    const results = await Promise.allSettled([
      notificationsApi.listNotifications({ page_size: 6 }),
      isStaff ? approvalsApi.getPendingCount() : Promise.resolve(0),
      isStaff
        ? requestsApi.listRequests({ status: 'VALIDATION_FAILED', page_size: 1 })
        : Promise.resolve(null),
      isManager ? masterDataApi.getPendingCount() : Promise.resolve(0),
    ])

    if (!mounted.current) return

    const [inbox, pending, failed, masterData] = results

    if (inbox.status === 'fulfilled') {
      const items = inbox.value.items ?? []
      setNotifications(items)
      setBadges((current) => ({
        ...current,
        unread: items.filter((item) => !item.read).length,
      }))
    }
    if (pending.status === 'fulfilled') {
      setBadges((current) => ({ ...current, pending: pending.value ?? 0 }))
    }
    if (failed.status === 'fulfilled' && failed.value) {
      setBadges((current) => ({
        ...current,
        exceptions: failed.value.meta?.total ?? 0,
      }))
    }
    if (masterData.status === 'fulfilled') {
      setBadges((current) => ({ ...current, masterData: masterData.value ?? 0 }))
    }
  }, [isStaff, isManager])

  useEffect(() => {
    loadBadges()
    const timer = setInterval(loadBadges, BADGE_POLL_MS)
    return () => clearInterval(timer)
  }, [loadBadges])

  // Re-check on navigation: acting on a request usually changes a count.
  useEffect(() => {
    loadBadges()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [location.pathname])

  // Close the mobile drawer whenever the route changes.
  useEffect(() => {
    setSidebarOpen(false)
  }, [location.pathname])

  return (
    <div className="flex min-h-dvh bg-slate-50">
      <Sidebar
        open={sidebarOpen}
        onClose={() => setSidebarOpen(false)}
        badges={badges}
      />

      <div className="flex min-w-0 flex-1 flex-col">
        <Topbar
          onOpenSidebar={() => setSidebarOpen(true)}
          notifications={notifications}
          unread={badges.unread}
          onRefreshBadges={loadBadges}
        />
        <main className="flex-1 px-4 py-5 sm:px-6 sm:py-6">
          <div className="mx-auto w-full max-w-[1400px]">
            <Outlet context={{ refreshBadges: loadBadges, isManager }} />
          </div>
        </main>
      </div>
    </div>
  )
}
