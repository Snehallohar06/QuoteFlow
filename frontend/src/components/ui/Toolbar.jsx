import { Search, SlidersHorizontal, X } from 'lucide-react'
import { Button } from './Button'

/** The search box used above every table. */
export function SearchInput({
  value,
  onChange,
  placeholder = 'Search…',
  className = '',
  ...props
}) {
  return (
    <div className={`relative ${className}`}>
      <Search
        size={15}
        className="pointer-events-none absolute left-3 top-1/2 -translate-y-1/2 text-slate-400"
        aria-hidden="true"
      />
      <input
        type="search"
        value={value}
        onChange={(event) => onChange(event.target.value)}
        placeholder={placeholder}
        aria-label={placeholder}
        className="h-9.5 w-full rounded-md bg-white pl-9 pr-8 text-sm text-slate-900 shadow-sm ring-1 ring-slate-300 transition placeholder:text-slate-400 focus:outline-none focus:ring-2 focus:ring-brand-500"
        {...props}
      />
      {value ? (
        <button
          type="button"
          onClick={() => onChange('')}
          className="absolute right-2.5 top-1/2 -translate-y-1/2 rounded p-0.5 text-slate-400 transition hover:bg-slate-100 hover:text-slate-700"
          aria-label="Clear search"
        >
          <X size={14} />
        </button>
      ) : null}
    </div>
  )
}

/** A compact filter select for a toolbar, with no separate label row. */
export function FilterSelect({
  value,
  onChange,
  options,
  placeholder = 'All',
  label,
  className = '',
}) {
  return (
    <select
      value={value ?? ''}
      onChange={(event) => onChange(event.target.value || undefined)}
      aria-label={label ?? placeholder}
      className={`h-9.5 rounded-md bg-white px-3 text-sm text-slate-700 shadow-sm ring-1 ring-slate-300 transition focus:outline-none focus:ring-2 focus:ring-brand-500 ${className}`}
    >
      <option value="">{placeholder}</option>
      {options.map((option) => (
        <option key={option.value} value={option.value}>
          {option.label}
        </option>
      ))}
    </select>
  )
}

/**
 * The filter row above a table.
 *
 * When `activeCount` is above zero a "Clear" button appears, so a user can
 * always get back to the unfiltered list in one click.
 */
export function Toolbar({ children, activeCount = 0, onClear, className = '' }) {
  return (
    <div
      className={`flex flex-wrap items-center gap-2 border-b border-slate-200 px-4 py-3 sm:px-5 ${className}`}
    >
      {children}
      {activeCount > 0 && onClear ? (
        <Button variant="ghost" size="sm" icon={X} onClick={onClear}>
          Clear
          <span className="ml-0.5 rounded-full bg-slate-200 px-1.5 text-[11px] font-semibold text-slate-600">
            {activeCount}
          </span>
        </Button>
      ) : null}
    </div>
  )
}

export function ToolbarSpacer() {
  return <div className="ml-auto" />
}

export { SlidersHorizontal }
