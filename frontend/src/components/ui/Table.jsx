import { ChevronLeft, ChevronRight, Inbox, Loader2, SearchX } from 'lucide-react'
import { Button } from './Button'

/**
 * A data table with explicit loading, empty and error states.
 *
 * Columns are declared as `{ key, header, align, width, className, render }`.
 * Passing `onRowClick` makes rows keyboard-activatable as well as clickable.
 */
export function Table({
  columns,
  rows,
  loading = false,
  error = null,
  empty,
  onRowClick,
  rowKey = (row, index) => row.id ?? index,
  skeletonRows = 5,
  className = '',
}) {
  const alignClass = (align) =>
    align === 'right' ? 'text-right' : align === 'center' ? 'text-center' : 'text-left'

  if (error) {
    return (
      <ErrorState
        error={error}
        className="border-t border-slate-200"
      />
    )
  }

  const showEmpty = !loading && rows.length === 0

  return (
    <div className={`w-full overflow-x-auto scrollbar-thin ${className}`}>
      <table className="w-full min-w-full border-collapse text-sm">
        <thead>
          <tr className="border-b border-slate-200 bg-slate-50/80">
            {columns.map((column) => (
              <th
                key={column.key}
                scope="col"
                style={column.width ? { width: column.width } : undefined}
                className={`whitespace-nowrap px-3.5 py-2.5 text-[11.5px] font-semibold uppercase tracking-wide text-slate-500 first:pl-4 last:pr-4 sm:first:pl-5 sm:last:pr-5 ${alignClass(
                  column.align
                )}`}
              >
                {column.header}
              </th>
            ))}
          </tr>
        </thead>
        <tbody className="divide-y divide-slate-100">
          {loading
            ? Array.from({ length: skeletonRows }).map((_, rowIndex) => (
                <tr key={`skeleton-${rowIndex}`}>
                  {columns.map((column) => (
                    <td
                      key={column.key}
                      className="px-3.5 py-3 first:pl-4 last:pr-4 sm:first:pl-5 sm:last:pr-5"
                    >
                      <div
                        className="h-3.5 animate-pulse rounded bg-slate-200"
                        style={{ width: `${55 + ((rowIndex * 7 + column.key.length * 3) % 40)}%` }}
                      />
                    </td>
                  ))}
                </tr>
              ))
            : rows.map((row, index) => {
                const clickable = Boolean(onRowClick)
                return (
                  <tr
                    key={rowKey(row, index)}
                    onClick={clickable ? () => onRowClick(row) : undefined}
                    onKeyDown={
                      clickable
                        ? (event) => {
                            if (event.key === 'Enter' || event.key === ' ') {
                              event.preventDefault()
                              onRowClick(row)
                            }
                          }
                        : undefined
                    }
                    tabIndex={clickable ? 0 : undefined}
                    role={clickable ? 'button' : undefined}
                    className={`transition-colors ${
                      clickable
                        ? 'cursor-pointer hover:bg-brand-50/50 focus-visible:bg-brand-50/50'
                        : ''
                    }`}
                  >
                    {columns.map((column) => (
                      <td
                        key={column.key}
                        className={`px-3.5 py-3 align-middle first:pl-4 last:pr-4 sm:first:pl-5 sm:last:pr-5 ${alignClass(
                          column.align
                        )} ${column.className ?? ''}`}
                      >
                        {column.render ? column.render(row, index) : row[column.key]}
                      </td>
                    ))}
                  </tr>
                )
              })}
        </tbody>
      </table>

      {showEmpty ? <div className="border-t border-slate-100">{empty}</div> : null}
    </div>
  )
}

export function EmptyState({
  icon: Icon = Inbox,
  title,
  description,
  action,
  className = '',
}) {
  return (
    <div className={`flex flex-col items-center px-6 py-12 text-center ${className}`}>
      <span className="rounded-full bg-slate-100 p-3 text-slate-400">
        <Icon size={22} aria-hidden="true" />
      </span>
      <p className="mt-3 text-[15px] font-medium text-slate-700">{title}</p>
      {description ? (
        <p className="mt-1 max-w-sm text-[13.5px] leading-relaxed text-slate-500">
          {description}
        </p>
      ) : null}
      {action ? <div className="mt-4">{action}</div> : null}
    </div>
  )
}

/** Shown when a filtered list comes back empty but the collection is not. */
export function NoResultsState({ onClear, className = '' }) {
  return (
    <EmptyState
      icon={SearchX}
      title="No matches"
      description="No records match the current filters. Try a different search term or clear the filters."
      action={
        onClear ? (
          <Button variant="secondary" size="sm" onClick={onClear}>
            Clear filters
          </Button>
        ) : null
      }
      className={className}
    />
  )
}

export function ErrorState({ error, onRetry, className = '' }) {
  const message =
    error?.message ?? 'The request failed. Please try again in a moment.'
  return (
    <div className={`flex flex-col items-center px-6 py-10 text-center ${className}`}>
      <span className="rounded-full bg-rose-50 p-3 text-rose-500">
        <SearchX size={22} aria-hidden="true" />
      </span>
      <p className="mt-3 text-[15px] font-medium text-slate-800">Could not load data</p>
      <p className="mt-1 max-w-md text-[13.5px] leading-relaxed text-slate-500">
        {message}
      </p>
      {onRetry ? (
        <Button variant="secondary" size="sm" className="mt-4" onClick={onRetry}>
          Try again
        </Button>
      ) : null}
    </div>
  )
}

/** Page-level pagination bar driven by the backend's `meta` envelope. */
export function Pagination({ meta, onPageChange, className = '' }) {
  if (!meta || meta.total === 0) return null

  const { page, page_size: pageSize, total, total_pages: totalPages } = meta
  const first = (page - 1) * pageSize + 1
  const last = Math.min(page * pageSize, total)

  return (
    <div
      className={`flex flex-wrap items-center justify-between gap-3 border-t border-slate-200 px-4 py-3 sm:px-5 ${className}`}
    >
      <p className="text-[13px] text-slate-500">
        Showing <span className="font-medium text-slate-700">{first}</span>–
        <span className="font-medium text-slate-700">{last}</span> of{' '}
        <span className="font-medium text-slate-700">{total}</span>
      </p>
      <div className="flex items-center gap-1.5">
        <Button
          variant="secondary"
          size="sm"
          icon={ChevronLeft}
          disabled={page <= 1}
          onClick={() => onPageChange(page - 1)}
        >
          Previous
        </Button>
        <span className="px-2 text-[13px] text-slate-500">
          Page {page} of {Math.max(totalPages, 1)}
        </span>
        <Button
          variant="secondary"
          size="sm"
          iconRight={ChevronRight}
          disabled={page >= totalPages}
          onClick={() => onPageChange(page + 1)}
        >
          Next
        </Button>
      </div>
    </div>
  )
}

export function Spinner({ size = 18, className = '', label }) {
  return (
    <span className={`inline-flex items-center gap-2 ${className}`} role="status">
      <Loader2 size={size} className="animate-spin text-brand-600" aria-hidden="true" />
      {label ? <span className="text-[13.5px] text-slate-600">{label}</span> : null}
      <span className="sr-only">{label ?? 'Loading'}</span>
    </span>
  )
}

export function PageLoader({ label = 'Loading' }) {
  return (
    <div className="flex items-center justify-center py-20">
      <Spinner size={22} label={label} />
    </div>
  )
}
