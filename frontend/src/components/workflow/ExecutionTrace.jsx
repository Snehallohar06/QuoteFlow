import { useState } from 'react'
import { ChevronDown, ChevronRight } from 'lucide-react'

import { StatusBadge } from '../ui/Badge'
import {
  STEP_LABELS,
  outcomeInfo,
  stepStatusInfo,
} from '../../lib/status'
import { formatDateTime, formatDuration, humanise } from '../../lib/format'

/** Renders a step's `output` dict without assuming which keys it holds. */
function OutputTable({ output }) {
  const entries = Object.entries(output ?? {})
  if (entries.length === 0) {
    return <p className="text-[12.5px] italic text-slate-400">No output recorded.</p>
  }

  return (
    <dl className="grid gap-x-6 gap-y-1.5 sm:grid-cols-2">
      {entries.map(([key, value]) => (
        <div key={key} className="flex items-baseline justify-between gap-3">
          <dt className="shrink-0 text-[12px] text-slate-500">{humanise(key)}</dt>
          <dd className="tnum min-w-0 break-words text-right text-[12.5px] font-medium text-slate-700">
            <Value value={value} />
          </dd>
        </div>
      ))}
    </dl>
  )
}

function Value({ value }) {
  if (value === null || value === undefined) return <span className="text-slate-400">—</span>
  if (typeof value === 'boolean') return value ? 'Yes' : 'No'
  if (Array.isArray(value)) {
    if (value.length === 0) return <span className="text-slate-400">none</span>
    // Arrays of objects (the rule trace, shortfall lines) get their own block.
    if (typeof value[0] === 'object') {
      return (
        <span className="text-slate-500">
          {value.length} record{value.length === 1 ? '' : 's'}
        </span>
      )
    }
    return value.join(', ')
  }
  if (typeof value === 'object') {
    return <span className="text-slate-500">object</span>
  }
  return String(value)
}

/** The nested rule trace from EVALUATE_DISCOUNT_RULES, when present. */
function RuleTrace({ rules }) {
  if (!Array.isArray(rules) || rules.length === 0) return null

  return (
    <div className="mt-3 overflow-x-auto scrollbar-thin">
      <table className="w-full min-w-[560px] text-[12px]">
        <thead>
          <tr className="border-b border-slate-200 text-left text-[11px] uppercase tracking-wide text-slate-500">
            <th className="py-1.5 pr-3 font-semibold">SKU</th>
            <th className="py-1.5 pr-3 text-right font-semibold">Qty</th>
            <th className="py-1.5 pr-3 text-right font-semibold">Requested</th>
            <th className="py-1.5 pr-3 text-right font-semibold">Band</th>
            <th className="py-1.5 pr-3 text-right font-semibold">Bonus</th>
            <th className="py-1.5 pr-3 text-right font-semibold">Ceiling</th>
            <th className="py-1.5 font-semibold">Verdict</th>
          </tr>
        </thead>
        <tbody className="divide-y divide-slate-100">
          {rules.map((rule, index) => (
            <tr key={`${rule.sku}-${index}`}>
              <td className="py-1.5 pr-3 font-medium text-slate-700">{rule.sku}</td>
              <td className="tnum py-1.5 pr-3 text-right text-slate-600">
                {rule.quantity}
              </td>
              <td className="tnum py-1.5 pr-3 text-right text-slate-600">
                {rule.requested_percent}%
              </td>
              <td className="tnum py-1.5 pr-3 text-right text-slate-600">
                {rule.base_tier_percent}%
              </td>
              <td className="tnum py-1.5 pr-3 text-right text-slate-600">
                +{rule.tier_bonus_percent}%
              </td>
              <td className="tnum py-1.5 pr-3 text-right font-medium text-slate-700">
                {rule.max_allowed_percent}%
              </td>
              <td className="py-1.5">
                <span
                  className={`text-[11.5px] font-medium ${
                    rule.verdict === 'ALLOWED'
                      ? 'text-emerald-700'
                      : rule.verdict === 'NEEDS_APPROVAL'
                        ? 'text-amber-700'
                        : 'text-rose-700'
                  }`}
                >
                  {humanise(rule.verdict)}
                </span>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}

function StepRow({ step, defaultOpen }) {
  const [open, setOpen] = useState(Boolean(defaultOpen))
  const info = stepStatusInfo(step.status)
  const label = STEP_LABELS[step.step] ?? humanise(step.step)
  const rules = step.output?.rules

  return (
    <li className="border-b border-slate-100 last:border-0">
      <button
        type="button"
        onClick={() => setOpen((value) => !value)}
        className="flex w-full items-center gap-2.5 px-4 py-2.5 text-left transition hover:bg-slate-50 sm:px-5"
        aria-expanded={open}
      >
        {open ? (
          <ChevronDown size={15} className="shrink-0 text-slate-400" aria-hidden="true" />
        ) : (
          <ChevronRight size={15} className="shrink-0 text-slate-400" aria-hidden="true" />
        )}

        <span className="min-w-0 flex-1">
          <span className="flex flex-wrap items-center gap-2">
            <span className="text-[13.5px] font-medium text-slate-800">{label}</span>
            <StatusBadge info={info} size="sm" />
          </span>
          {step.message ? (
            <span className="mt-0.5 block truncate text-[12.5px] text-slate-500">
              {step.message}
            </span>
          ) : null}
        </span>

        <span className="tnum shrink-0 text-[11.5px] text-slate-400">
          {formatDuration(step.duration_ms)}
        </span>
      </button>

      {open ? (
        <div className="border-t border-slate-100 bg-slate-50/60 px-4 py-3 sm:px-5 sm:pl-12">
          {step.errors?.length ? (
            <ul className="mb-3 space-y-1.5">
              {step.errors.map((error, index) => (
                <li
                  key={index}
                  className="rounded border border-rose-200 bg-rose-50 px-2.5 py-1.5 text-[12.5px] leading-snug text-rose-700"
                >
                  {error}
                </li>
              ))}
            </ul>
          ) : null}

          <OutputTable
            output={Object.fromEntries(
              Object.entries(step.output ?? {}).filter(([key]) => key !== 'rules')
            )}
          />
          <RuleTrace rules={rules} />

          <p className="mt-3 text-[11.5px] text-slate-400">
            Started {formatDateTime(step.started_at)}
          </p>
        </div>
      ) : null}
    </li>
  )
}

/**
 * One workflow execution, step by step.
 *
 * This is the stored audit trail of the rule engine, not a reconstruction, so
 * the figures shown here are exactly what the engine computed at the time.
 */
export function ExecutionTrace({ execution, defaultOpenFailed = true }) {
  if (!execution) return null
  const info = outcomeInfo(execution.outcome)

  return (
    <div>
      <div className="flex flex-wrap items-center justify-between gap-3 border-b border-slate-200 bg-slate-50/60 px-4 py-3 sm:px-5">
        <div className="flex flex-wrap items-center gap-2">
          <StatusBadge info={info} />
          <span className="text-[12.5px] text-slate-500">
            {humanise(execution.trigger)} · engine v{execution.engine_version}
          </span>
        </div>
        <div className="flex items-center gap-3 text-[12px] text-slate-500">
          <span className="tnum">{formatDuration(execution.duration_ms)} total</span>
          <span>{formatDateTime(execution.started_at)}</span>
        </div>
      </div>

      <ul>
        {execution.steps?.map((step, index) => (
          <StepRow
            key={`${step.step}-${index}`}
            step={step}
            defaultOpen={defaultOpenFailed && step.status === 'FAILED'}
          />
        ))}
      </ul>
    </div>
  )
}
