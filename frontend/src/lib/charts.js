/**
 * Chart parameters, validated rather than eyeballed.
 *
 * The palette below was checked with the data-viz validator against this app's
 * actual chart surface (white, `#ffffff`), not the validator's default surface:
 *
 *   slots 1-2, adjacent   ALL CHECKS PASS (CVD dE 24.7, normal-vision dE 33.6)
 *   slots 1-3, all pairs  pass, with a contrast WARN on aqua (2.82:1)
 *
 * Most charts in QuoteFlow therefore use a **single series**, with identity
 * carried by the axis labels rather than by hue. That is deliberate: an earlier
 * draft coloured one chart by request outcome using the four status colours, and
 * the validator failed it — `warning` and `serious` sit at a normal-vision dE of
 * 13.6, below the 15 floor, so pending and failed segments were genuinely hard
 * to tell apart. Splitting that into two single-series charts (volume over time,
 * and outcome mix) removed the problem instead of papering over it.
 *
 * Where two series are unavoidable, use SERIES[0] and SERIES[1], which clear
 * every gate.
 */

/** Categorical slots, in fixed order. Never cycled, never generated. */
export const SERIES = ['#2a78d6', '#eb6834', '#1baf7a']

/** Status colours. Reserved for state, and always paired with an icon or label. */
export const STATUS_COLORS = {
  good: '#0ca30c',
  warning: '#fab219',
  serious: '#ec835a',
  critical: '#d03b3b',
}

/** Chart chrome for the light surface this app renders on. */
export const CHART_INK = {
  surface: '#ffffff',
  grid: '#e1e0d9',
  axis: '#c3c2b7',
  muted: '#898781',
  secondary: '#52514e',
  primary: '#0b0b0b',
}

/** Shared Recharts props so every chart's chrome matches. */
export const GRID_PROPS = {
  stroke: CHART_INK.grid,
  strokeDasharray: '3 3',
}

export const AXIS_PROPS = {
  tickLine: false,
  tick: { fontSize: 11.5, fill: CHART_INK.muted },
}

export const X_AXIS_PROPS = {
  ...AXIS_PROPS,
  axisLine: { stroke: CHART_INK.axis },
}

export const Y_AXIS_PROPS = {
  ...AXIS_PROPS,
  axisLine: false,
}

/** Mark geometry: 2px lines, 4px rounded data-ends, >=8px markers. */
export const LINE_PROPS = {
  strokeWidth: 2,
  dot: false,
  activeDot: { r: 4.5, strokeWidth: 2, stroke: '#ffffff' },
}

export const BAR_RADIUS = [4, 4, 0, 0]
export const BAR_RADIUS_HORIZONTAL = [0, 4, 4, 0]

/** `"2026-10-30"` -> `"30 Oct"`, for a dense time axis. */
export function chartDate(value) {
  if (!value) return ''
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return value
  return date.toLocaleDateString('en-GB', { day: '2-digit', month: 'short' })
}

/** `"2026-10"` -> `"Oct 2026"`. */
export function chartMonth(value) {
  if (!value) return ''
  const [year, month] = String(value).split('-')
  if (!year || !month) return value
  const date = new Date(Number(year), Number(month) - 1, 1)
  if (Number.isNaN(date.getTime())) return value
  return date.toLocaleDateString('en-GB', { month: 'short', year: 'numeric' })
}
