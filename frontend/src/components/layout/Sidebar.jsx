import { NavLink } from 'react-router-dom'
import { X } from 'lucide-react'

import { useAuth } from '../../context/AuthContext'
import { ROLE_LABELS } from '../../lib/status'
import { initials } from '../../lib/format'
import { navigationFor } from './navigation'

function Brand() {
  return (
    <div className="flex items-center gap-2.5 px-4 py-4">
      <span className="grid h-8 w-8 shrink-0 place-items-center rounded-lg bg-brand-500 text-white">
        <svg viewBox="0 0 24 24" className="h-4 w-4" aria-hidden="true">
          <path
            d="M5 6h14M5 12h14M5 18h8"
            stroke="currentColor"
            strokeWidth="2.2"
            strokeLinecap="round"
            fill="none"
          />
        </svg>
      </span>
      <div className="min-w-0">
        <p className="truncate text-[15px] font-semibold leading-tight text-white">
          QuoteFlow
        </p>
        <p className="truncate text-[11px] leading-tight text-navy-300">
          Quotation Management
        </p>
      </div>
    </div>
  )
}

function NavItem({ item, badgeValue, onNavigate }) {
  const Icon = item.icon
  const count = item.badge ? badgeValue : 0

  return (
    <NavLink
      to={item.to}
      end={item.to === '/dashboard'}
      onClick={onNavigate}
      className={({ isActive }) =>
        `group flex items-center gap-2.5 rounded-md px-2.5 py-2 text-[13.5px] font-medium transition-colors ${
          isActive
            ? 'bg-brand-600 text-white shadow-sm'
            : 'text-navy-100 hover:bg-navy-600/60 hover:text-white'
        }`
      }
    >
      {({ isActive }) => (
        <>
          <Icon
            size={16}
            className={isActive ? 'text-white' : 'text-navy-300 group-hover:text-white'}
            aria-hidden="true"
          />
          <span className="min-w-0 flex-1 truncate">{item.label}</span>
          {count > 0 ? (
            <span
              className={`tnum shrink-0 rounded-full px-1.5 py-0.5 text-[10.5px] font-semibold ${
                isActive ? 'bg-white/25 text-white' : 'bg-brand-500 text-white'
              }`}
            >
              {count > 99 ? '99+' : count}
            </span>
          ) : null}
        </>
      )}
    </NavLink>
  )
}

export function SidebarContent({ badges, onNavigate }) {
  const { user, customer, role } = useAuth()
  const groups = navigationFor(role)

  return (
    <div className="flex h-full flex-col bg-navy-700">
      <Brand />

      <nav
        className="flex-1 space-y-5 overflow-y-auto scrollbar-thin px-2.5 pb-4"
        aria-label="Main navigation"
      >
        {groups.map((group, index) => (
          <div key={group.heading ?? `group-${index}`}>
            {group.heading ? (
              <p className="mb-1.5 px-2.5 text-[10.5px] font-semibold uppercase tracking-wider text-navy-400">
                {group.heading}
              </p>
            ) : null}
            <div className="space-y-0.5">
              {group.items.map((item) => (
                <NavItem
                  key={item.to}
                  item={item}
                  badgeValue={badges?.[item.badge] ?? 0}
                  onNavigate={onNavigate}
                />
              ))}
            </div>
          </div>
        ))}
      </nav>

      <div className="border-t border-navy-600/70 px-3 py-3">
        <div className="flex items-center gap-2.5">
          <span className="grid h-8 w-8 shrink-0 place-items-center rounded-full bg-navy-500 text-[12px] font-semibold text-white">
            {initials(user?.full_name)}
          </span>
          <div className="min-w-0 flex-1">
            <p className="truncate text-[13px] font-medium leading-tight text-white">
              {user?.full_name}
            </p>
            <p className="truncate text-[11px] leading-tight text-navy-300">
              {customer?.company_name ?? ROLE_LABELS[role] ?? role}
            </p>
          </div>
        </div>
      </div>
    </div>
  )
}

/** Desktop rail plus the mobile drawer. */
export function Sidebar({ open, onClose, badges }) {
  return (
    <>
      <aside className="hidden w-60 shrink-0 lg:block">
        <div className="fixed inset-y-0 left-0 w-60">
          <SidebarContent badges={badges} />
        </div>
      </aside>

      {open ? (
        <div className="fixed inset-0 z-40 lg:hidden">
          <div
            className="absolute inset-0 bg-navy-900/50"
            onClick={onClose}
            aria-hidden="true"
          />
          <div className="absolute inset-y-0 left-0 w-64 shadow-xl">
            <button
              type="button"
              onClick={onClose}
              className="absolute -right-11 top-3 rounded-md bg-white/10 p-2 text-white backdrop-blur transition hover:bg-white/20"
              aria-label="Close navigation"
            >
              <X size={18} />
            </button>
            <SidebarContent badges={badges} onNavigate={onClose} />
          </div>
        </div>
      ) : null}
    </>
  )
}
