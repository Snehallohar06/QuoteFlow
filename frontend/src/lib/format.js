/**
 * Display formatting.
 *
 * The backend sends money as JSON numbers already quantised to 2dp, so these
 * helpers only format; they never do arithmetic that could change a figure.
 */

const CURRENCY_LOCALE = 'en-IN'

/** `1426116.14` -> `"14,26,116.14"` (no symbol). */
export function formatAmount(value, { decimals = 2 } = {}) {
  if (value === null || value === undefined || Number.isNaN(Number(value))) return '—'
  return Number(value).toLocaleString(CURRENCY_LOCALE, {
    minimumFractionDigits: decimals,
    maximumFractionDigits: decimals,
  })
}

/** `1426116.14` -> `"₹14,26,116.14"`. */
export function formatMoney(value, { currency = 'INR', decimals = 2 } = {}) {
  if (value === null || value === undefined || Number.isNaN(Number(value))) return '—'
  const symbol = currency === 'INR' ? '₹' : `${currency} `
  return `${symbol}${formatAmount(value, { decimals })}`
}

/** Compact money for chart axes and tiles: `1426116` -> `"₹14.3L"`. */
export function formatMoneyCompact(value, { currency = 'INR' } = {}) {
  if (value === null || value === undefined || Number.isNaN(Number(value))) return '—'
  const symbol = currency === 'INR' ? '₹' : `${currency} `
  const n = Number(value)
  const abs = Math.abs(n)
  if (abs >= 1e7) return `${symbol}${(n / 1e7).toFixed(2)}Cr`
  if (abs >= 1e5) return `${symbol}${(n / 1e5).toFixed(1)}L`
  if (abs >= 1e3) return `${symbol}${(n / 1e3).toFixed(1)}K`
  return `${symbol}${n.toFixed(0)}`
}

/** `8.41` -> `"8.41%"`. */
export function formatPercent(value, { decimals = 2 } = {}) {
  if (value === null || value === undefined || Number.isNaN(Number(value))) return '—'
  const n = Number(value)
  const text = Number.isInteger(n) ? n.toString() : n.toFixed(decimals)
  return `${text}%`
}

export function formatNumber(value) {
  if (value === null || value === undefined || Number.isNaN(Number(value))) return '—'
  return Number(value).toLocaleString(CURRENCY_LOCALE)
}

/**
 * The API returns UTC timestamps. `Date` parses the ISO string and renders in
 * the viewer's local zone, which is what a user expects to see.
 */
function toDate(value) {
  if (!value) return null
  const date = new Date(value)
  return Number.isNaN(date.getTime()) ? null : date
}

/** `"2026-10-30T12:21:17Z"` -> `"30 Oct 2026"`. */
export function formatDate(value) {
  const date = toDate(value)
  if (!date) return '—'
  return date.toLocaleDateString('en-GB', {
    day: '2-digit',
    month: 'short',
    year: 'numeric',
  })
}

/** `"2026-10-30T12:21:17Z"` -> `"30 Oct 2026, 17:51"`. */
export function formatDateTime(value) {
  const date = toDate(value)
  if (!date) return '—'
  return `${formatDate(value)}, ${date.toLocaleTimeString('en-GB', {
    hour: '2-digit',
    minute: '2-digit',
  })}`
}

/** `"...T12:21:17Z"` -> `"4 minutes ago"`. */
export function formatRelative(value) {
  const date = toDate(value)
  if (!date) return '—'
  const seconds = Math.round((Date.now() - date.getTime()) / 1000)
  const future = seconds < 0
  const abs = Math.abs(seconds)

  const units = [
    ['year', 31536000],
    ['month', 2592000],
    ['day', 86400],
    ['hour', 3600],
    ['minute', 60],
  ]
  for (const [unit, size] of units) {
    if (abs >= size) {
      const count = Math.floor(abs / size)
      const plural = count === 1 ? unit : `${unit}s`
      return future ? `in ${count} ${plural}` : `${count} ${plural} ago`
    }
  }
  return future ? 'in a moment' : 'just now'
}

/** Milliseconds -> a readable duration: `24` -> `"24 ms"`, `1500` -> `"1.5 s"`. */
export function formatDuration(ms) {
  if (ms === null || ms === undefined) return '—'
  const n = Number(ms)
  if (n < 1000) return `${Math.round(n)} ms`
  if (n < 60000) return `${(n / 1000).toFixed(1)} s`
  return `${Math.round(n / 60000)} min`
}

/** Hours as a decimal -> `"2.5 h"`, or minutes when under an hour. */
export function formatHours(hours) {
  if (hours === null || hours === undefined) return '—'
  const n = Number(hours)
  if (n === 0) return 'under a minute'
  if (n < 1) return `${Math.round(n * 60)} min`
  return `${n.toFixed(1)} h`
}

/** `"DISCOUNT_LIMIT_EXCEEDED"` -> `"Discount limit exceeded"`. */
export function humanise(value) {
  if (!value) return '—'
  const text = String(value).replace(/_/g, ' ').toLowerCase()
  return text.charAt(0).toUpperCase() + text.slice(1)
}

export function initials(name) {
  if (!name) return '?'
  return name
    .split(/\s+/)
    .filter(Boolean)
    .slice(0, 2)
    .map((part) => part[0].toUpperCase())
    .join('')
}

/** Days remaining until a date; negative when already past. */
export function daysUntil(value) {
  const date = toDate(value)
  if (!date) return null
  return Math.ceil((date.getTime() - Date.now()) / 86400000)
}
