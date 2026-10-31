import { createContext, useCallback, useContext, useMemo, useRef, useState } from 'react'
import { AlertTriangle, CheckCircle2, Info, X, XCircle } from 'lucide-react'

const ToastContext = createContext(null)

const VARIANTS = {
  success: {
    icon: CheckCircle2,
    ring: 'ring-emerald-200',
    bg: 'bg-emerald-50',
    iconColor: 'text-emerald-600',
  },
  error: {
    icon: XCircle,
    ring: 'ring-rose-200',
    bg: 'bg-rose-50',
    iconColor: 'text-rose-600',
  },
  warning: {
    icon: AlertTriangle,
    ring: 'ring-amber-200',
    bg: 'bg-amber-50',
    iconColor: 'text-amber-600',
  },
  info: {
    icon: Info,
    ring: 'ring-brand-200',
    bg: 'bg-brand-50',
    iconColor: 'text-brand-600',
  },
}

const DEFAULT_DURATION = 5000

export function ToastProvider({ children }) {
  const [toasts, setToasts] = useState([])
  const timers = useRef(new Map())

  const dismiss = useCallback((id) => {
    setToasts((current) => current.filter((toast) => toast.id !== id))
    const timer = timers.current.get(id)
    if (timer) {
      clearTimeout(timer)
      timers.current.delete(id)
    }
  }, [])

  const push = useCallback(
    (variant, title, description, { duration = DEFAULT_DURATION } = {}) => {
      const id = `${Date.now()}-${Math.random().toString(36).slice(2, 8)}`
      setToasts((current) => [...current, { id, variant, title, description }])
      if (duration > 0) {
        timers.current.set(
          id,
          setTimeout(() => dismiss(id), duration)
        )
      }
      return id
    },
    [dismiss]
  )

  const toast = useMemo(
    () => ({
      success: (title, description, options) =>
        push('success', title, description, options),
      error: (title, description, options) => push('error', title, description, options),
      warning: (title, description, options) =>
        push('warning', title, description, options),
      info: (title, description, options) => push('info', title, description, options),
      /**
       * Render an ApiError without the caller having to unpack it. Permission
       * and auth failures get a gentler wording than a server fault.
       */
      fromError: (error, fallbackTitle = 'Something went wrong') => {
        if (!error) return push('error', fallbackTitle)
        if (error.isForbidden) {
          return push('warning', 'Not permitted', error.message)
        }
        if (error.status === 0) {
          return push('error', 'Cannot reach the server', error.message, {
            duration: 8000,
          })
        }
        return push('error', fallbackTitle, error.message)
      },
      dismiss,
    }),
    [push, dismiss]
  )

  return (
    <ToastContext.Provider value={toast}>
      {children}
      <div
        className="pointer-events-none fixed inset-x-0 top-0 z-[100] flex flex-col items-center gap-2 px-4 pt-4 sm:items-end sm:px-6"
        role="region"
        aria-label="Notifications"
      >
        {toasts.map((item) => {
          const variant = VARIANTS[item.variant] ?? VARIANTS.info
          const Icon = variant.icon
          return (
            <div
              key={item.id}
              role="status"
              aria-live="polite"
              className={`pointer-events-auto flex w-full max-w-md items-start gap-3 rounded-lg ${variant.bg} px-4 py-3 shadow-lg ring-1 ${variant.ring}`}
            >
              <Icon
                size={18}
                className={`mt-0.5 shrink-0 ${variant.iconColor}`}
                aria-hidden="true"
              />
              <div className="min-w-0 flex-1">
                <p className="text-sm font-semibold text-slate-900">{item.title}</p>
                {item.description ? (
                  <p className="mt-0.5 text-[13px] leading-snug text-slate-600">
                    {item.description}
                  </p>
                ) : null}
              </div>
              <button
                type="button"
                onClick={() => dismiss(item.id)}
                className="-mr-1 -mt-1 shrink-0 rounded p-1 text-slate-400 transition hover:bg-white/60 hover:text-slate-700"
                aria-label="Dismiss notification"
              >
                <X size={15} />
              </button>
            </div>
          )
        })}
      </div>
    </ToastContext.Provider>
  )
}

export function useToast() {
  const context = useContext(ToastContext)
  if (!context) throw new Error('useToast must be used inside a ToastProvider')
  return context
}
