import {
  AlertTriangle,
  Check,
  Clock,
  Minus,
  RefreshCw,
  ShieldCheck,
  X,
} from 'lucide-react'

import { Card, CardBody, CardHeader } from '../ui/Card'
import { Badge } from '../ui/Badge'
import { SUCCESS_GATE_CONDITIONS, escalationReasonLabel } from '../../lib/status'
import { formatDuration, humanise } from '../../lib/format'

/**
 * The workflow's boundary controls, as the backend recorded them.
 *
 * Shows the six success-gate conditions, the retry and attempt counts against
 * their configured limits, and the escalation reason when a request was parked.
 * Everything here comes from the stored execution — nothing is inferred.
 */
export function SuccessGatePanel({ gate, className = '' }) {
  if (!gate || Object.keys(gate).length === 0) return null

  const met = SUCCESS_GATE_CONDITIONS.filter((condition) => gate[condition.key])
  const passed = met.length === SUCCESS_GATE_CONDITIONS.length

  return (
    <Card className={className}>
      <CardHeader
        title="Success gate"
        description={
          passed
            ? 'All six conditions are satisfied'
            : `${met.length} of ${SUCCESS_GATE_CONDITIONS.length} conditions satisfied`
        }
        icon={ShieldCheck}
        action={
          <Badge tone={passed ? 'success' : 'warning'} size="sm">
            {passed ? 'Passed' : 'Not met'}
          </Badge>
        }
      />
      <CardBody>
        <ul className="space-y-1.5">
          {SUCCESS_GATE_CONDITIONS.map((condition) => {
            const satisfied = Boolean(gate[condition.key])
            return (
              <li key={condition.key} className="flex items-center gap-2">
                <span
                  className={`grid h-4 w-4 shrink-0 place-items-center rounded-full ${
                    satisfied
                      ? 'bg-emerald-100 text-emerald-700'
                      : 'bg-slate-100 text-slate-400'
                  }`}
                >
                  {satisfied ? <Check size={11} /> : <Minus size={11} />}
                </span>
                <span
                  className={`text-[13px] ${
                    satisfied ? 'text-slate-700' : 'text-slate-400'
                  }`}
                >
                  {condition.label}
                </span>
              </li>
            )
          })}
        </ul>
        <p className="mt-3 border-t border-slate-100 pt-2.5 text-[11.5px] leading-snug text-slate-500">
          A request can only be marked completed when every condition above
          holds. An unevaluated condition counts as unmet.
        </p>
      </CardBody>
    </Card>
  )
}

/** Retry, attempt and duration counts against their configured ceilings. */
export function ExecutionBudgetPanel({ request, execution, className = '' }) {
  if (!request) return null

  const budget = execution?.budget ?? {}
  const retries = budget.retries ?? []

  const rows = [
    {
      label: 'Processing attempts',
      value: request.attempt_count ?? 0,
      limit: budget.max_attempts,
      icon: RefreshCw,
    },
    {
      label: 'Retries used',
      value: request.retry_count ?? 0,
      limit: budget.max_retries_per_step,
      limitLabel: 'per step',
      icon: RefreshCw,
    },
    {
      label: 'Engine time',
      value: formatDuration(request.total_execution_ms ?? 0),
      limit: budget.max_total_execution_ms
        ? formatDuration(budget.max_total_execution_ms)
        : null,
      icon: Clock,
    },
  ]

  if ((request.no_op_count ?? 0) > 0) {
    rows.push({
      label: 'No-op runs',
      value: request.no_op_count,
      icon: Minus,
      hint: 'Triggered with nothing left to do',
    })
  }

  return (
    <Card className={className}>
      <CardHeader
        title="Execution budget"
        description="Consumption against the configured limits"
        icon={Clock}
      />
      <CardBody>
        <dl className="space-y-2">
          {rows.map((row) => (
            <div key={row.label}>
              <div className="flex items-baseline justify-between gap-3">
                <dt className="text-[13px] text-slate-500">{row.label}</dt>
                <dd className="tnum text-[13.5px] font-medium text-slate-800">
                  {row.value}
                  {row.limit ? (
                    <span className="ml-1 text-[11.5px] font-normal text-slate-400">
                      / {row.limit} {row.limitLabel ?? ''}
                    </span>
                  ) : null}
                </dd>
              </div>
              {row.hint ? (
                <p className="text-[11.5px] text-slate-400">{row.hint}</p>
              ) : null}
            </div>
          ))}
        </dl>

        {retries.length > 0 ? (
          <div className="mt-3 border-t border-slate-100 pt-2.5">
            <p className="mb-1.5 text-[11.5px] font-semibold uppercase tracking-wide text-slate-500">
              Retry log
            </p>
            <ul className="space-y-1.5">
              {retries.map((record, index) => (
                <li
                  key={index}
                  className="rounded border border-amber-200 bg-amber-50/60 px-2 py-1.5"
                >
                  <p className="text-[12px] font-medium text-amber-900">
                    {humanise(record.step)} · attempt {record.attempt}
                  </p>
                  <p className="mt-0.5 break-words text-[11.5px] leading-snug text-amber-900/80">
                    {record.error}
                  </p>
                  <p className="mt-0.5 text-[11px] text-amber-700">
                    {record.failure_class} · waited {record.waited_ms} ms
                  </p>
                </li>
              ))}
            </ul>
          </div>
        ) : null}
      </CardBody>
    </Card>
  )
}

/** Why a request was parked, shown prominently when it was. */
export function EscalationBanner({ request, className = '' }) {
  if (!request?.escalation_reason) return null

  return (
    <Card className={`border-rose-200 bg-rose-50/60 ${className}`}>
      <CardBody>
        <div className="flex items-start gap-2.5">
          <AlertTriangle
            size={17}
            className="mt-0.5 shrink-0 text-rose-600"
            aria-hidden="true"
          />
          <div className="min-w-0">
            <div className="flex flex-wrap items-center gap-2">
              <p className="text-[13.5px] font-semibold text-rose-900">
                Escalated for review
              </p>
              <Badge tone="danger" size="sm">
                {escalationReasonLabel(request.escalation_reason)}
              </Badge>
            </div>
            {request.escalation_detail ? (
              <p className="mt-1 text-[12.5px] leading-snug text-rose-900/85">
                {request.escalation_detail}
              </p>
            ) : null}
            <p className="mt-2 text-[11.5px] leading-snug text-rose-700">
              The workflow stopped here deliberately rather than issuing a
              document it could not stand behind. A sales employee can correct
              the cause and re-run it.
            </p>
          </div>
        </div>
      </CardBody>
    </Card>
  )
}

/** The checker tool's findings, when it rejected a document. */
export function CheckerFindings({ report, className = '' }) {
  if (!report || report.passed) return null

  return (
    <Card className={`border-rose-200 ${className}`}>
      <CardHeader
        title="Independent verification findings"
        description="Where the checker's own recalculation disagreed with the document"
        icon={X}
      />
      <CardBody>
        <ul className="space-y-2">
          {(report.findings ?? []).map((finding, index) => (
            <li
              key={index}
              className="rounded-md border border-rose-200 bg-rose-50/60 px-3 py-2"
            >
              <div className="flex flex-wrap items-center gap-2">
                <Badge tone="danger" size="sm">
                  {humanise(finding.check)}
                </Badge>
                {finding.sku ? (
                  <span className="font-mono text-[11.5px] text-slate-600">
                    {finding.sku}
                  </span>
                ) : null}
              </div>
              <p className="mt-1 text-[12.5px] leading-snug text-rose-900">
                {finding.detail}
              </p>
              {finding.expected || finding.actual ? (
                <p className="tnum mt-1 text-[11.5px] text-rose-800">
                  expected <span className="font-medium">{finding.expected}</span>
                  {' · '}
                  found <span className="font-medium">{finding.actual}</span>
                </p>
              ) : null}
            </li>
          ))}
        </ul>
        {report.checks_run?.length ? (
          <p className="mt-3 border-t border-slate-100 pt-2.5 text-[11.5px] leading-snug text-slate-500">
            Checks run: {report.checks_run.map(humanise).join(', ')}.
          </p>
        ) : null}
      </CardBody>
    </Card>
  )
}
