import { forwardRef, useId } from 'react'
import { AlertCircle, ChevronDown } from 'lucide-react'

const BASE_CONTROL =
  'w-full rounded-md bg-white text-sm text-slate-900 shadow-sm ring-1 transition placeholder:text-slate-400 disabled:cursor-not-allowed disabled:bg-slate-50 disabled:text-slate-500'

function controlClasses(invalid, extra = '') {
  const ring = invalid
    ? 'ring-rose-300 focus:ring-2 focus:ring-rose-500'
    : 'ring-slate-300 focus:ring-2 focus:ring-brand-500'
  return `${BASE_CONTROL} ${ring} focus:outline-none ${extra}`
}

/**
 * Label + control + help/error text.
 *
 * The error message is wired to the control with `aria-describedby` and
 * `aria-invalid`, so screen readers announce it rather than it being colour-only.
 */
export function Field({
  label,
  htmlFor,
  error,
  hint,
  required,
  children,
  className = '',
}) {
  return (
    <div className={className}>
      {label ? (
        <label
          htmlFor={htmlFor}
          className="mb-1.5 block text-[13px] font-medium text-slate-700"
        >
          {label}
          {required ? (
            <span className="ml-0.5 text-rose-600" aria-hidden="true">
              *
            </span>
          ) : null}
        </label>
      ) : null}
      {children}
      {error ? (
        <p
          id={htmlFor ? `${htmlFor}-error` : undefined}
          className="mt-1.5 flex items-start gap-1 text-[12.5px] text-rose-600"
        >
          <AlertCircle size={13} className="mt-0.5 shrink-0" aria-hidden="true" />
          <span>{error}</span>
        </p>
      ) : hint ? (
        <p
          id={htmlFor ? `${htmlFor}-hint` : undefined}
          className="mt-1.5 text-[12.5px] text-slate-500"
        >
          {hint}
        </p>
      ) : null}
    </div>
  )
}

export const Input = forwardRef(function Input(
  { label, error, hint, required, className = '', id, prefix, ...props },
  ref
) {
  const generatedId = useId()
  const inputId = id ?? generatedId
  const describedBy = error
    ? `${inputId}-error`
    : hint
      ? `${inputId}-hint`
      : undefined

  return (
    <Field
      label={label}
      htmlFor={inputId}
      error={error}
      hint={hint}
      required={required}
      className={className}
    >
      <div className="relative">
        {prefix ? (
          <span className="pointer-events-none absolute left-3 top-1/2 -translate-y-1/2 text-sm text-slate-500">
            {prefix}
          </span>
        ) : null}
        <input
          ref={ref}
          id={inputId}
          aria-invalid={error ? true : undefined}
          aria-describedby={describedBy}
          className={controlClasses(
            Boolean(error),
            `h-9.5 px-3 ${prefix ? 'pl-9' : ''}`
          )}
          {...props}
        />
      </div>
    </Field>
  )
})

export const Textarea = forwardRef(function Textarea(
  { label, error, hint, required, className = '', id, rows = 3, ...props },
  ref
) {
  const generatedId = useId()
  const inputId = id ?? generatedId
  const describedBy = error
    ? `${inputId}-error`
    : hint
      ? `${inputId}-hint`
      : undefined

  return (
    <Field
      label={label}
      htmlFor={inputId}
      error={error}
      hint={hint}
      required={required}
      className={className}
    >
      <textarea
        ref={ref}
        id={inputId}
        rows={rows}
        aria-invalid={error ? true : undefined}
        aria-describedby={describedBy}
        className={controlClasses(Boolean(error), 'px-3 py-2 leading-relaxed')}
        {...props}
      />
    </Field>
  )
})

export const Select = forwardRef(function Select(
  {
    label,
    error,
    hint,
    required,
    className = '',
    id,
    options = [],
    placeholder,
    children,
    ...props
  },
  ref
) {
  const generatedId = useId()
  const inputId = id ?? generatedId
  const describedBy = error
    ? `${inputId}-error`
    : hint
      ? `${inputId}-hint`
      : undefined

  return (
    <Field
      label={label}
      htmlFor={inputId}
      error={error}
      hint={hint}
      required={required}
      className={className}
    >
      <div className="relative">
        <select
          ref={ref}
          id={inputId}
          aria-invalid={error ? true : undefined}
          aria-describedby={describedBy}
          className={controlClasses(Boolean(error), 'h-9.5 appearance-none pl-3 pr-9')}
          {...props}
        >
          {placeholder ? <option value="">{placeholder}</option> : null}
          {options.map((option) => (
            <option key={option.value} value={option.value}>
              {option.label}
            </option>
          ))}
          {children}
        </select>
        <ChevronDown
          size={15}
          className="pointer-events-none absolute right-3 top-1/2 -translate-y-1/2 text-slate-400"
          aria-hidden="true"
        />
      </div>
    </Field>
  )
})

export function Checkbox({ label, hint, id, className = '', ...props }) {
  const generatedId = useId()
  const inputId = id ?? generatedId
  return (
    <div className={`flex items-start gap-2.5 ${className}`}>
      <input
        id={inputId}
        type="checkbox"
        className="mt-0.5 h-4 w-4 shrink-0 rounded border-slate-300 text-brand-600 focus:ring-2 focus:ring-brand-500"
        {...props}
      />
      <div className="min-w-0">
        <label htmlFor={inputId} className="text-[13.5px] font-medium text-slate-700">
          {label}
        </label>
        {hint ? <p className="text-[12.5px] text-slate-500">{hint}</p> : null}
      </div>
    </div>
  )
}
