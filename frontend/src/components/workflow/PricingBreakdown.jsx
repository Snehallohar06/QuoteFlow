import { AlertTriangle, Info } from 'lucide-react'

import { Badge, StatusBadge } from '../ui/Badge'
import { availabilityInfo, exceptionInfo } from '../../lib/status'
import { formatMoney, formatPercent, humanise } from '../../lib/format'

/**
 * The priced line table.
 *
 * Every column here is a figure the backend computed; nothing is re-derived in
 * the browser. A line whose requested discount exceeded its ceiling is flagged,
 * because that is what sent the request to a manager.
 */
export function LineItemsTable({ items = [], currency = 'INR', showAvailability = true }) {
  if (items.length === 0) {
    return (
      <p className="px-4 py-6 text-center text-[13px] text-slate-500 sm:px-5">
        No line items on this request.
      </p>
    )
  }

  return (
    <div className="overflow-x-auto scrollbar-thin">
      <table className="w-full min-w-[840px] text-sm">
        <thead>
          <tr className="border-b border-slate-200 bg-slate-50/80 text-[11.5px] uppercase tracking-wide text-slate-500">
            <th className="py-2.5 pl-4 pr-3 text-left font-semibold sm:pl-5">Item</th>
            <th className="px-3 py-2.5 text-right font-semibold">Qty</th>
            <th className="px-3 py-2.5 text-right font-semibold">Unit price</th>
            <th className="px-3 py-2.5 text-right font-semibold">Subtotal</th>
            <th className="px-3 py-2.5 text-right font-semibold">Discount</th>
            <th className="px-3 py-2.5 text-right font-semibold">Taxable</th>
            <th className="px-3 py-2.5 text-right font-semibold">Tax</th>
            <th className="py-2.5 pl-3 pr-4 text-right font-semibold sm:pr-5">
              Line total
            </th>
          </tr>
        </thead>
        <tbody className="divide-y divide-slate-100">
          {items.map((item, index) => (
            <tr key={item.product_id ?? index} className="align-top">
              <td className="py-3 pl-4 pr-3 sm:pl-5">
                <p className="font-medium text-slate-800">{item.name}</p>
                <p className="mt-0.5 font-mono text-[11.5px] text-slate-500">
                  {item.sku}
                </p>
                {showAvailability && item.availability ? (
                  <div className="mt-1.5">
                    <Badge
                      tone={availabilityInfo(item.availability.status).tone}
                      size="sm"
                    >
                      {availabilityInfo(item.availability.status).label}
                      {item.availability.shortfall > 0
                        ? ` · ${item.availability.shortfall} short`
                        : ''}
                    </Badge>
                  </div>
                ) : null}
                {item.notes ? (
                  <p className="mt-1 text-[12px] italic text-slate-500">{item.notes}</p>
                ) : null}
              </td>

              <td className="tnum px-3 py-3 text-right text-slate-700">
                {item.quantity}
                <span className="ml-1 text-[11.5px] text-slate-400">{item.unit}</span>
              </td>

              <td className="tnum px-3 py-3 text-right text-slate-700">
                {formatMoney(item.unit_price, { currency })}
              </td>

              <td className="tnum px-3 py-3 text-right text-slate-700">
                {formatMoney(item.line_subtotal, { currency })}
              </td>

              <td className="px-3 py-3 text-right">
                <p className="tnum text-slate-700">
                  {formatMoney(item.line_discount_amount, { currency })}
                </p>
                <p
                  className={`tnum mt-0.5 text-[11.5px] ${
                    item.discount_exception ? 'font-semibold text-amber-700' : 'text-slate-500'
                  }`}
                >
                  {formatPercent(item.applied_discount_percent)}
                  {item.discount_exception ? (
                    <span className="ml-1 text-slate-400">
                      (max {formatPercent(item.max_allowed_discount_percent)})
                    </span>
                  ) : null}
                </p>
              </td>

              <td className="tnum px-3 py-3 text-right text-slate-700">
                {formatMoney(item.line_taxable_amount, { currency })}
              </td>

              <td className="px-3 py-3 text-right">
                <p className="tnum text-slate-700">
                  {formatMoney(item.line_tax_amount, { currency })}
                </p>
                <p className="tnum mt-0.5 text-[11.5px] text-slate-500">
                  {formatPercent(item.tax_rate)}
                </p>
              </td>

              <td className="tnum py-3 pl-3 pr-4 text-right font-semibold text-navy-800 sm:pr-5">
                {formatMoney(item.line_total, { currency })}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}

/**
 * The totals block.
 *
 * The order of rows is the order the engine calculates in: subtotal, then
 * discount, then the taxable amount tax is charged on, then tax, then the final
 * amount.
 */
export function PricingSummary({ pricing, className = '', emphasis = true }) {
  if (!pricing) {
    return (
      <div className={`flex items-start gap-2 px-4 py-4 sm:px-5 ${className}`}>
        <Info size={15} className="mt-0.5 shrink-0 text-slate-400" aria-hidden="true" />
        <p className="text-[13px] text-slate-500">
          This request has not been priced yet. Figures appear once the workflow runs.
        </p>
      </div>
    )
  }

  const currency = pricing.currency ?? 'INR'
  const rows = [
    { label: 'Subtotal', value: formatMoney(pricing.subtotal, { currency }) },
    {
      label: `Discount (${formatPercent(pricing.effective_discount_percent)})`,
      value: `−${formatMoney(pricing.total_discount, { currency })}`,
      tone: 'text-emerald-700',
    },
    { label: 'Taxable amount', value: formatMoney(pricing.taxable_amount, { currency }) },
    {
      label: pricing.tax_label ?? 'Tax',
      value: formatMoney(pricing.total_tax, { currency }),
    },
  ]

  return (
    <div className={`px-4 py-4 sm:px-5 ${className}`}>
      <dl className="ml-auto max-w-sm space-y-1.5">
        {rows.map((row) => (
          <div key={row.label} className="flex items-baseline justify-between gap-6">
            <dt className="text-[13px] text-slate-500">{row.label}</dt>
            <dd className={`tnum text-[13.5px] font-medium ${row.tone ?? 'text-slate-800'}`}>
              {row.value}
            </dd>
          </div>
        ))}

        <div
          className={`flex items-baseline justify-between gap-6 border-t pt-2 ${
            emphasis ? 'border-navy-200' : 'border-slate-200'
          }`}
        >
          <dt className="text-[14px] font-semibold text-navy-800">
            Final amount ({currency})
          </dt>
          <dd className="tnum text-[17px] font-semibold text-navy-800">
            {formatMoney(pricing.final_amount, { currency })}
          </dd>
        </div>

        <div className="flex items-baseline justify-between gap-6 pt-1">
          <dt className="text-[11.5px] text-slate-400">
            {pricing.line_count} line(s) · {pricing.total_quantity} unit(s)
          </dt>
        </div>
      </dl>
    </div>
  )
}

/** The rule exceptions that sent a request for review. */
export function ExceptionList({ exceptions = [], className = '' }) {
  if (exceptions.length === 0) return null

  return (
    <ul className={`space-y-2 ${className}`}>
      {exceptions.map((exception, index) => {
        const info = exceptionInfo(exception.type)
        return (
          <li
            key={`${exception.type}-${index}`}
            className="rounded-md border border-amber-200 bg-amber-50/70 px-3 py-2.5"
          >
            <div className="flex items-start gap-2.5">
              <AlertTriangle
                size={15}
                className="mt-0.5 shrink-0 text-amber-600"
                aria-hidden="true"
              />
              <div className="min-w-0 flex-1">
                <div className="flex flex-wrap items-center gap-2">
                  <p className="text-[13px] font-semibold text-amber-900">
                    {info.label}
                  </p>
                  <Badge tone={info.tone} size="sm">
                    {humanise(exception.type)}
                  </Badge>
                </div>
                <p className="mt-1 text-[12.5px] leading-snug text-amber-900/80">
                  {exception.message}
                </p>
                {info.hint ? (
                  <p className="mt-1 text-[11.5px] leading-snug text-amber-700/70">
                    {info.hint}
                  </p>
                ) : null}
              </div>
            </div>
          </li>
        )
      })}
    </ul>
  )
}

/** Validation errors that stopped a request before it could be priced. */
export function ValidationErrors({ errors = [], className = '' }) {
  if (errors.length === 0) return null

  return (
    <div
      className={`rounded-md border border-rose-200 bg-rose-50/70 px-3.5 py-3 ${className}`}
    >
      <div className="flex items-start gap-2.5">
        <AlertTriangle
          size={15}
          className="mt-0.5 shrink-0 text-rose-600"
          aria-hidden="true"
        />
        <div className="min-w-0">
          <p className="text-[13px] font-semibold text-rose-900">
            {errors.length === 1
              ? 'This request could not be processed'
              : `${errors.length} issues stopped this request`}
          </p>
          <ul className="mt-1.5 space-y-1">
            {errors.map((error, index) => (
              <li key={index} className="text-[12.5px] leading-snug text-rose-800">
                • {error}
              </li>
            ))}
          </ul>
        </div>
      </div>
    </div>
  )
}

export { StatusBadge }
