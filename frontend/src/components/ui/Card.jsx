import { TrendingDown, TrendingUp } from 'lucide-react'

export function Card({ children, className = '', as: Tag = 'div', ...props }) {
  return (
    <Tag
      className={`rounded-card border border-slate-200 bg-white shadow-sm ${className}`}
      {...props}
    >
      {children}
    </Tag>
  )
}

export function CardHeader({ title, description, action, icon: Icon, className = '' }) {
  return (
    <div
      className={`flex flex-wrap items-start justify-between gap-3 border-b border-slate-200 px-4 py-3.5 sm:px-5 ${className}`}
    >
      <div className="flex min-w-0 items-start gap-2.5">
        {Icon ? (
          <span className="mt-0.5 rounded-md bg-navy-50 p-1.5 text-navy-700">
            <Icon size={16} aria-hidden="true" />
          </span>
        ) : null}
        <div className="min-w-0">
          <h2 className="truncate text-[15px] font-semibold text-navy-800">{title}</h2>
          {description ? (
            <p className="mt-0.5 text-[13px] text-slate-500">{description}</p>
          ) : null}
        </div>
      </div>
      {action ? <div className="flex shrink-0 items-center gap-2">{action}</div> : null}
    </div>
  )
}

export function CardBody({ children, className = '', padded = true }) {
  return (
    <div className={`${padded ? 'px-4 py-4 sm:px-5' : ''} ${className}`}>{children}</div>
  )
}

export function CardFooter({ children, className = '' }) {
  return (
    <div
      className={`flex flex-wrap items-center justify-end gap-2 border-t border-slate-200 bg-slate-50/60 px-4 py-3 sm:px-5 ${className}`}
    >
      {children}
    </div>
  )
}

const TILE_TONES = {
  navy: 'bg-navy-50 text-navy-700',
  blue: 'bg-brand-50 text-brand-700',
  amber: 'bg-amber-50 text-amber-700',
  emerald: 'bg-emerald-50 text-emerald-700',
  rose: 'bg-rose-50 text-rose-700',
  slate: 'bg-slate-100 text-slate-600',
}

/**
 * A dashboard KPI tile.
 *
 * `delta` is a signed number rendered as a trend; `deltaLabel` names what it is
 * relative to, because a bare percentage with no baseline means nothing.
 */
export function StatCard({
  label,
  value,
  hint,
  icon: Icon,
  tone = 'navy',
  delta,
  deltaLabel,
  loading = false,
  className = '',
}) {
  return (
    <Card className={`p-4 sm:p-4.5 ${className}`}>
      <div className="flex items-start justify-between gap-3">
        <p className="text-[12.5px] font-medium uppercase tracking-wide text-slate-500">
          {label}
        </p>
        {Icon ? (
          <span className={`rounded-md p-1.5 ${TILE_TONES[tone] ?? TILE_TONES.navy}`}>
            <Icon size={15} aria-hidden="true" />
          </span>
        ) : null}
      </div>

      {loading ? (
        <div className="mt-2.5 h-7 w-24 animate-pulse rounded bg-slate-200" />
      ) : (
        <p className="tnum mt-2 text-[26px] font-semibold leading-none text-navy-800">
          {value}
        </p>
      )}

      {!loading && (hint || delta !== undefined) ? (
        <div className="mt-2 flex items-center gap-2 text-[12.5px]">
          {delta !== undefined && delta !== null ? (
            <span
              className={`inline-flex items-center gap-1 font-medium ${
                delta >= 0 ? 'text-emerald-600' : 'text-rose-600'
              }`}
            >
              {delta >= 0 ? (
                <TrendingUp size={13} aria-hidden="true" />
              ) : (
                <TrendingDown size={13} aria-hidden="true" />
              )}
              {Math.abs(delta)}%
            </span>
          ) : null}
          {deltaLabel ? <span className="text-slate-500">{deltaLabel}</span> : null}
          {hint ? <span className="text-slate-500">{hint}</span> : null}
        </div>
      ) : null}
    </Card>
  )
}

/** A label/value pair, used throughout the detail pages. */
export function DetailRow({ label, value, className = '', mono = false }) {
  return (
    <div className={`flex items-baseline justify-between gap-4 py-1.5 ${className}`}>
      <dt className="shrink-0 text-[13px] text-slate-500">{label}</dt>
      <dd
        className={`min-w-0 text-right text-[13.5px] font-medium text-slate-800 ${
          mono ? 'font-mono text-[12.5px]' : ''
        }`}
      >
        {value ?? '—'}
      </dd>
    </div>
  )
}

export function DetailList({ children, className = '' }) {
  return <dl className={`divide-y divide-slate-100 ${className}`}>{children}</dl>
}
