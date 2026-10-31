import { forwardRef } from 'react'
import { Loader2 } from 'lucide-react'

const VARIANTS = {
  primary:
    'bg-brand-600 text-white shadow-sm hover:bg-brand-700 active:bg-brand-800 disabled:bg-brand-300',
  secondary:
    'bg-white text-slate-700 ring-1 ring-slate-300 shadow-sm hover:bg-slate-50 hover:text-slate-900 disabled:text-slate-400',
  navy: 'bg-navy-700 text-white shadow-sm hover:bg-navy-800 active:bg-navy-900 disabled:bg-navy-300',
  danger:
    'bg-rose-600 text-white shadow-sm hover:bg-rose-700 active:bg-rose-800 disabled:bg-rose-300',
  success:
    'bg-emerald-600 text-white shadow-sm hover:bg-emerald-700 active:bg-emerald-800 disabled:bg-emerald-300',
  ghost: 'text-slate-600 hover:bg-slate-100 hover:text-slate-900 disabled:text-slate-400',
  link: 'text-brand-700 underline-offset-2 hover:underline disabled:text-slate-400',
}

const SIZES = {
  sm: 'h-8 gap-1.5 px-3 text-[13px]',
  md: 'h-9.5 gap-2 px-3.5 text-sm',
  lg: 'h-11 gap-2 px-5 text-[15px]',
  icon: 'h-9 w-9 justify-center',
  'icon-sm': 'h-7.5 w-7.5 justify-center',
}

export const Button = forwardRef(function Button(
  {
    variant = 'primary',
    size = 'md',
    loading = false,
    icon: Icon,
    iconRight: IconRight,
    children,
    className = '',
    disabled,
    type = 'button',
    ...props
  },
  ref
) {
  const isDisabled = disabled || loading
  const iconSize = size === 'sm' || size === 'icon-sm' ? 14 : 16

  return (
    <button
      ref={ref}
      type={type}
      disabled={isDisabled}
      aria-busy={loading || undefined}
      className={`inline-flex shrink-0 items-center rounded-md font-medium transition-colors disabled:cursor-not-allowed ${VARIANTS[variant]} ${SIZES[size]} ${className}`}
      {...props}
    >
      {loading ? (
        <Loader2 size={iconSize} className="animate-spin" aria-hidden="true" />
      ) : Icon ? (
        <Icon size={iconSize} aria-hidden="true" />
      ) : null}
      {children}
      {IconRight && !loading ? <IconRight size={iconSize} aria-hidden="true" /> : null}
    </button>
  )
})
