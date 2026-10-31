import { TONE_CLASSES } from '../../lib/status'

/**
 * A pill whose colour carries meaning.
 *
 * `tone` comes from the status helpers in lib/status.js, so the same state
 * always renders the same colour everywhere in the app.
 */
export function Badge({
  children,
  tone = 'neutral',
  icon: Icon,
  size = 'md',
  className = '',
  spinIcon = false,
}) {
  const sizes = {
    sm: 'px-1.5 py-0.5 text-[11px] gap-1',
    md: 'px-2 py-0.5 text-[12px] gap-1.5',
    lg: 'px-2.5 py-1 text-[13px] gap-1.5',
  }
  return (
    <span
      className={`inline-flex items-center rounded-full font-medium ring-1 ring-inset ${
        TONE_CLASSES[tone] ?? TONE_CLASSES.neutral
      } ${sizes[size]} ${className}`}
    >
      {Icon ? (
        <Icon
          size={size === 'sm' ? 11 : 12}
          className={spinIcon ? 'animate-spin' : ''}
          aria-hidden="true"
        />
      ) : null}
      {children}
    </span>
  )
}

/**
 * Renders any of the `*Info()` results from lib/status.js.
 *
 * The in-progress statuses use a spinning icon, which is the one place an
 * animation genuinely conveys state rather than decorating it.
 */
export function StatusBadge({ info, size = 'md', showIcon = true, className = '' }) {
  if (!info) return null
  const spin = info.tone === 'progress'
  return (
    <Badge
      tone={info.tone}
      icon={showIcon ? info.icon : undefined}
      size={size}
      spinIcon={spin}
      className={className}
    >
      {info.label}
    </Badge>
  )
}
