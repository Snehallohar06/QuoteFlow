import { CHART_INK } from '../../lib/charts'

/**
 * The hover tooltip every chart shares.
 *
 * An HTML chart is interactive by default, so each chart ships a tooltip rather
 * than relying on axis reading. Values wear text ink, never the series colour —
 * the swatch beside them carries identity.
 */
export function ChartTooltip({
  active,
  payload,
  label,
  labelFormatter,
  valueFormatter,
  hideLabel = false,
}) {
  if (!active || !payload?.length) return null

  const heading = labelFormatter ? labelFormatter(label) : label

  return (
    <div className="rounded-md border border-slate-200 bg-white px-2.5 py-2 shadow-lg">
      {!hideLabel && heading ? (
        <p className="mb-1.5 text-[12px] font-semibold text-slate-800">{heading}</p>
      ) : null}
      <ul className="space-y-1">
        {payload.map((entry, index) => (
          <li
            key={`${entry.dataKey}-${index}`}
            className="flex items-center justify-between gap-4 text-[12px]"
          >
            <span className="flex items-center gap-1.5">
              <span
                aria-hidden="true"
                className="h-2 w-2 shrink-0 rounded-sm"
                style={{ background: entry.color ?? entry.fill ?? CHART_INK.muted }}
              />
              <span className="text-slate-600">{entry.name}</span>
            </span>
            <span className="tnum font-medium text-slate-900">
              {valueFormatter ? valueFormatter(entry.value) : entry.value}
            </span>
          </li>
        ))}
      </ul>
    </div>
  )
}

/**
 * A ranked horizontal bar list, built in plain HTML.
 *
 * Preferred over a charting library for "which of these is biggest" when the
 * categories are text: the label sits beside the bar at full contrast, the value
 * is a direct label, and one hue means no colour-separation problem at all.
 */
export function RankedBars({
  rows,
  valueFormatter = (value) => value,
  color = '#2a78d6',
  emptyLabel = 'No data in this period',
  className = '',
}) {
  if (!rows?.length) {
    return (
      <p className={`py-6 text-center text-[13px] text-slate-500 ${className}`}>
        {emptyLabel}
      </p>
    )
  }

  const max = Math.max(...rows.map((row) => Number(row.value) || 0), 1)

  return (
    <ul className={`space-y-2.5 ${className}`}>
      {rows.map((row) => (
        <li key={row.key ?? row.label}>
          <div className="flex items-baseline justify-between gap-3">
            <span className="min-w-0 truncate text-[13px] text-slate-700">
              {row.label}
            </span>
            <span className="tnum shrink-0 text-[12.5px] font-medium text-slate-900">
              {valueFormatter(row.value)}
            </span>
          </div>
          <div className="mt-1 h-2 overflow-hidden rounded-full bg-slate-100">
            <div
              className="h-full rounded-full"
              style={{
                width: `${Math.max((Number(row.value) / max) * 100, 1.5)}%`,
                background: color,
              }}
            />
          </div>
          {row.hint ? (
            <p className="mt-0.5 text-[11.5px] text-slate-500">{row.hint}</p>
          ) : null}
        </li>
      ))}
    </ul>
  )
}
