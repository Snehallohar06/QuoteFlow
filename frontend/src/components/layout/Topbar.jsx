import { useEffect, useRef, useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { Bell, ChevronDown, KeyRound, LogOut, Menu, User } from 'lucide-react'

import { useAuth } from '../../context/AuthContext'
import { ROLE_LABELS, notificationInfo } from '../../lib/status'
import { formatRelative, initials } from '../../lib/format'
import { Badge } from '../ui/Badge'

function NotificationMenu({ notifications, unread, onOpenAll }) {
  const [open, setOpen] = useState(false)
  const ref = useRef(null)

  useEffect(() => {
    if (!open) return undefined
    const onClick = (event) => {
      if (!ref.current?.contains(event.target)) setOpen(false)
    }
    const onKey = (event) => {
      if (event.key === 'Escape') setOpen(false)
    }
    document.addEventListener('mousedown', onClick)
    document.addEventListener('keydown', onKey)
    return () => {
      document.removeEventListener('mousedown', onClick)
      document.removeEventListener('keydown', onKey)
    }
  }, [open])

  return (
    <div className="relative" ref={ref}>
      <button
        type="button"
        onClick={() => setOpen((value) => !value)}
        className="relative rounded-md p-2 text-slate-500 transition hover:bg-slate-100 hover:text-slate-700"
        aria-label={unread > 0 ? `Notifications, ${unread} unread` : 'Notifications'}
        aria-expanded={open}
      >
        <Bell size={18} />
        {unread > 0 ? (
          <span className="tnum absolute -right-0.5 -top-0.5 grid h-4 min-w-4 place-items-center rounded-full bg-rose-500 px-1 text-[10px] font-semibold text-white">
            {unread > 9 ? '9+' : unread}
          </span>
        ) : null}
      </button>

      {open ? (
        <div className="absolute right-0 z-50 mt-2 w-80 overflow-hidden rounded-lg bg-white shadow-lg ring-1 ring-slate-200">
          <div className="flex items-center justify-between border-b border-slate-200 px-4 py-2.5">
            <p className="text-[13.5px] font-semibold text-navy-800">Notifications</p>
            {unread > 0 ? <Badge tone="info" size="sm">{unread} unread</Badge> : null}
          </div>

          <div className="max-h-80 overflow-y-auto scrollbar-thin">
            {notifications.length === 0 ? (
              <p className="px-4 py-8 text-center text-[13px] text-slate-500">
                Nothing new right now.
              </p>
            ) : (
              notifications.slice(0, 6).map((item) => {
                const info = notificationInfo(item.type)
                const Icon = info.icon
                return (
                  <Link
                    key={item.id}
                    to="/notifications"
                    onClick={() => setOpen(false)}
                    className={`flex gap-2.5 border-b border-slate-100 px-4 py-2.5 transition last:border-0 hover:bg-slate-50 ${
                      item.read ? '' : 'bg-brand-50/40'
                    }`}
                  >
                    <Icon
                      size={15}
                      className="mt-0.5 shrink-0 text-slate-400"
                      aria-hidden="true"
                    />
                    <div className="min-w-0">
                      <p className="truncate text-[13px] font-medium text-slate-800">
                        {item.title}
                      </p>
                      <p className="line-clamp-2 text-[12px] leading-snug text-slate-500">
                        {item.message}
                      </p>
                      <p className="mt-0.5 text-[11px] text-slate-400">
                        {formatRelative(item.created_at)}
                      </p>
                    </div>
                  </Link>
                )
              })
            )}
          </div>

          <button
            type="button"
            onClick={() => {
              setOpen(false)
              onOpenAll()
            }}
            className="w-full border-t border-slate-200 bg-slate-50/60 px-4 py-2.5 text-[13px] font-medium text-brand-700 transition hover:bg-slate-100"
          >
            View all notifications
          </button>
        </div>
      ) : null}
    </div>
  )
}

function UserMenu() {
  const { user, customer, role, logout } = useAuth()
  const [open, setOpen] = useState(false)
  const ref = useRef(null)
  const navigate = useNavigate()

  useEffect(() => {
    if (!open) return undefined
    const onClick = (event) => {
      if (!ref.current?.contains(event.target)) setOpen(false)
    }
    const onKey = (event) => {
      if (event.key === 'Escape') setOpen(false)
    }
    document.addEventListener('mousedown', onClick)
    document.addEventListener('keydown', onKey)
    return () => {
      document.removeEventListener('mousedown', onClick)
      document.removeEventListener('keydown', onKey)
    }
  }, [open])

  return (
    <div className="relative" ref={ref}>
      <button
        type="button"
        onClick={() => setOpen((value) => !value)}
        className="flex items-center gap-2 rounded-md py-1 pl-1 pr-2 transition hover:bg-slate-100"
        aria-expanded={open}
        aria-label="Account menu"
      >
        <span className="grid h-7.5 w-7.5 place-items-center rounded-full bg-navy-700 text-[11.5px] font-semibold text-white">
          {initials(user?.full_name)}
        </span>
        <span className="hidden text-left sm:block">
          <span className="block max-w-36 truncate text-[13px] font-medium leading-tight text-slate-800">
            {user?.full_name}
          </span>
          <span className="block text-[11px] leading-tight text-slate-500">
            {ROLE_LABELS[role] ?? role}
          </span>
        </span>
        <ChevronDown size={14} className="text-slate-400" aria-hidden="true" />
      </button>

      {open ? (
        <div className="absolute right-0 z-50 mt-2 w-64 overflow-hidden rounded-lg bg-white shadow-lg ring-1 ring-slate-200">
          <div className="border-b border-slate-200 px-4 py-3">
            <p className="truncate text-[13.5px] font-semibold text-navy-800">
              {user?.full_name}
            </p>
            <p className="truncate text-[12px] text-slate-500">{user?.email}</p>
            {customer ? (
              <p className="mt-1.5 truncate text-[12px] text-slate-600">
                {customer.company_name}
                <span className="ml-1 text-slate-400">({customer.code})</span>
              </p>
            ) : null}
          </div>
          <div className="p-1.5">
            <button
              type="button"
              onClick={() => {
                setOpen(false)
                navigate('/profile')
              }}
              className="flex w-full items-center gap-2.5 rounded px-2.5 py-2 text-[13px] text-slate-700 transition hover:bg-slate-100"
            >
              <User size={15} className="text-slate-400" aria-hidden="true" />
              My profile
            </button>
            <button
              type="button"
              onClick={() => {
                setOpen(false)
                navigate('/profile#password')
              }}
              className="flex w-full items-center gap-2.5 rounded px-2.5 py-2 text-[13px] text-slate-700 transition hover:bg-slate-100"
            >
              <KeyRound size={15} className="text-slate-400" aria-hidden="true" />
              Change password
            </button>
          </div>
          <div className="border-t border-slate-200 p-1.5">
            <button
              type="button"
              onClick={() => {
                setOpen(false)
                logout()
              }}
              className="flex w-full items-center gap-2.5 rounded px-2.5 py-2 text-[13px] font-medium text-rose-600 transition hover:bg-rose-50"
            >
              <LogOut size={15} aria-hidden="true" />
              Sign out
            </button>
          </div>
        </div>
      ) : null}
    </div>
  )
}

export function Topbar({ onOpenSidebar, notifications, unread, onRefreshBadges }) {
  const navigate = useNavigate()

  return (
    <header className="sticky top-0 z-30 border-b border-slate-200 bg-white/95 backdrop-blur">
      <div className="flex h-14 items-center gap-2 px-4 sm:px-6">
        <button
          type="button"
          onClick={onOpenSidebar}
          className="-ml-1 rounded-md p-2 text-slate-600 transition hover:bg-slate-100 lg:hidden"
          aria-label="Open navigation"
        >
          <Menu size={19} />
        </button>

        <div className="ml-auto flex items-center gap-1 sm:gap-2">
          <NotificationMenu
            notifications={notifications}
            unread={unread}
            onOpenAll={() => {
              navigate('/notifications')
              onRefreshBadges?.()
            }}
          />
          <div className="mx-1 hidden h-6 w-px bg-slate-200 sm:block" />
          <UserMenu />
        </div>
      </div>
    </header>
  )
}
