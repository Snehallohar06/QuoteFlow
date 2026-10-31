import {
  AlertTriangle,
  Ban,
  Check,
  ClipboardCheck,
  Download,
  FileCheck2,
  Loader2,
  Minus,
  Send,
  ShieldCheck,
} from 'lucide-react'

import { REQUEST_STATUS } from '../../lib/status'

/**
 * The end-to-end process, as a vertical timeline.
 *
 * The nine stages below are the business process; the middle five are backed
 * one-to-one by steps the workflow engine actually recorded, which is why this
 * component takes the latest execution as well as the request. Stage state is
 * derived, never guessed:
 *
 *   complete  the step ran and succeeded, or the milestone is reached
 *   current   the request is sitting at this stage right now
 *   failed    the step reported FAILED, or the request was rejected here
 *   skipped   the step did not need to run (auto-approved: no manager stage)
 *   pending   not reached yet
 */

const STATE_STYLES = {
  complete: {
    dot: 'bg-emerald-500 text-white ring-emerald-100',
    line: 'bg-emerald-300',
    title: 'text-slate-800',
    icon: Check,
  },
  current: {
    dot: 'bg-brand-600 text-white ring-brand-100',
    line: 'bg-slate-200',
    title: 'text-brand-700 font-semibold',
    icon: Loader2,
  },
  failed: {
    dot: 'bg-rose-500 text-white ring-rose-100',
    line: 'bg-slate-200',
    title: 'text-rose-700 font-semibold',
    icon: AlertTriangle,
  },
  skipped: {
    dot: 'bg-slate-200 text-slate-500 ring-slate-100',
    line: 'bg-slate-200',
    title: 'text-slate-500',
    icon: Minus,
  },
  pending: {
    dot: 'bg-white text-slate-300 ring-slate-100 border border-slate-200',
    line: 'bg-slate-200',
    title: 'text-slate-400',
    icon: Minus,
  },
  cancelled: {
    dot: 'bg-slate-400 text-white ring-slate-100',
    line: 'bg-slate-200',
    title: 'text-slate-500',
    icon: Ban,
  },
}

/** Find a recorded step by name in the latest execution. */
function findStep(execution, key) {
  return execution?.steps?.find((step) => step.step === key) ?? null
}

function stateFromStep(step, { reachedStage }) {
  if (!step) return reachedStage ? 'current' : 'pending'
  if (step.status === 'FAILED') return 'failed'
  if (step.status === 'SKIPPED') return 'skipped'
  return 'complete'
}

/**
 * Build the nine stages for a request.
 *
 * @param request   the quotation request
 * @param execution the most recent workflow execution (may be null)
 * @param quotation the issued quotation, when loaded (may be null)
 * @param verification result of the public verify call, when run (may be null)
 */
export function buildStages({ request, execution, quotation, verification }) {
  if (!request) return []

  const status = request.status
  const cancelled = status === REQUEST_STATUS.CANCELLED
  const rejected = status === REQUEST_STATUS.REJECTED
  const submitted = Boolean(request.submitted_at)
  const validationFailed = status === REQUEST_STATUS.VALIDATION_FAILED
  const awaitingApproval = status === REQUEST_STATUS.PENDING_APPROVAL
  const approved = status === REQUEST_STATUS.APPROVED
  const modificationRequested = status === REQUEST_STATUS.MODIFICATION_REQUESTED
  const hasQuotation = Boolean(request.quotation_id)
  const neededApproval = Boolean(request.approval_id)
  const completed = status === REQUEST_STATUS.COMPLETED
  const escalated = status === REQUEST_STATUS.ESCALATED

  const engineReached = submitted && !cancelled

  const stages = [
    {
      key: 'request',
      label: 'Customer Request',
      icon: Send,
      state: submitted ? 'complete' : status === REQUEST_STATUS.DRAFT ? 'current' : 'complete',
      detail: submitted
        ? `${request.items?.length ?? 0} line(s) submitted`
        : 'Draft — not yet submitted',
    },
    {
      key: 'VALIDATE_REQUEST',
      label: 'Input Validation',
      icon: ClipboardCheck,
      step: findStep(execution, 'VALIDATE_REQUEST'),
    },
    {
      key: 'CHECK_AVAILABILITY',
      label: 'Product Verification',
      icon: ClipboardCheck,
      step: findStep(execution, 'CHECK_AVAILABILITY'),
    },
    {
      key: 'CALCULATE_PRICING',
      label: 'Price Calculation',
      icon: ClipboardCheck,
      step: findStep(execution, 'CALCULATE_PRICING'),
    },
    {
      key: 'EVALUATE_DISCOUNT_RULES',
      label: 'Business Rule Validation',
      icon: ClipboardCheck,
      step: findStep(execution, 'EVALUATE_DISCOUNT_RULES'),
    },
  ]

  // Fill in the engine-backed stages from the recorded steps.
  for (const stage of stages.slice(1)) {
    stage.state = stateFromStep(stage.step, { reachedStage: engineReached })
    stage.detail = stage.step?.message ?? null
    if (stage.step?.errors?.length) {
      stage.errors = stage.step.errors
    }
    if (stage.step) {
      stage.duration = stage.step.duration_ms
    }
  }

  // Manager approval: only part of the journey when a rule escalated it.
  let approvalState = 'pending'
  let approvalDetail = 'Not required — within policy'
  if (validationFailed) {
    approvalState = 'pending'
    approvalDetail = 'Not reached — validation failed'
  } else if (rejected) {
    approvalState = 'failed'
    approvalDetail = 'Rejected by the sales manager'
  } else if (modificationRequested) {
    approvalState = 'failed'
    approvalDetail = 'Returned for modification'
  } else if (awaitingApproval) {
    approvalState = 'current'
    approvalDetail = `${request.exceptions?.length ?? 0} exception(s) awaiting a decision`
  } else if (approved && neededApproval) {
    approvalState = 'complete'
    approvalDetail = 'Approved by the sales manager'
  } else if ((approved || completed) && neededApproval) {
    approvalState = 'complete'
    approvalDetail = 'Approved by the sales manager'
  } else if ((approved || completed) && !neededApproval) {
    approvalState = 'skipped'
    approvalDetail = 'Auto-approved — no exceptions raised'
  } else if (escalated) {
    approvalState = 'failed'
    approvalDetail = 'Parked for a human'
  }

  stages.push({
    key: 'approval',
    label: 'Manager Approval',
    icon: ClipboardCheck,
    state: cancelled ? 'cancelled' : approvalState,
    detail: approvalDetail,
  })

  // Both of these are real recorded steps now, so the timeline reads the
  // trace rather than inferring the stage from the request's fields.
  const generationStep = findStep(execution, 'GENERATE_DOCUMENT')
  stages.push({
    key: 'GENERATE_DOCUMENT',
    label: 'Quotation Generation',
    icon: FileCheck2,
    step: generationStep,
    state: generationStep
      ? stateFromStep(generationStep, { reachedStage: engineReached })
      : hasQuotation
        ? 'complete'
        : 'pending',
    detail:
      generationStep?.message ??
      (hasQuotation
        ? quotation?.quotation_number
          ? `Issued as ${quotation.quotation_number}`
          : 'Quotation issued'
        : 'Not issued'),
    errors: generationStep?.errors?.length ? generationStep.errors : undefined,
    duration: generationStep?.duration_ms,
  })

  const verifyStep = findStep(execution, 'VERIFY_DOCUMENT')
  // A live verification the user just ran overrides the stored step, so the
  // stage reflects the most recent evidence.
  const verifyState = verification
    ? verification.valid
      ? 'complete'
      : 'failed'
    : verifyStep
      ? stateFromStep(verifyStep, { reachedStage: engineReached })
      : 'pending'

  stages.push({
    key: 'VERIFY_DOCUMENT',
    label: 'Independent Verification',
    icon: ShieldCheck,
    step: verifyStep,
    state: verifyState,
    detail: verification
      ? verification.valid
        ? `Integrity digest confirmed${
            verification.expired ? ' — but the quotation has expired' : ''
          }`
        : 'Verification failed: the stored amounts do not match the digest'
      : (verifyStep?.message ??
        (hasQuotation
          ? 'Awaiting verification'
          : 'Awaiting a quotation')),
    errors: verifyStep?.errors?.length ? verifyStep.errors : undefined,
    duration: verifyStep?.duration_ms,
  })

  stages.push({
    key: 'delivery',
    label: 'Customer Delivery',
    icon: Download,
    state: !hasQuotation
      ? 'pending'
      : (quotation?.download_count ?? 0) > 0
        ? 'complete'
        : completed
          ? 'current'
          : 'pending',
    detail: !hasQuotation
      ? 'Awaiting a quotation'
      : (quotation?.download_count ?? 0) > 0
        ? `Downloaded ${quotation.download_count} time(s)`
        : 'Ready to download',
  })

  if (cancelled) {
    for (const stage of stages) {
      if (stage.state === 'pending' || stage.state === 'current') {
        stage.state = 'cancelled'
        if (stage.key !== 'request') stage.detail = 'Request cancelled'
      }
    }
  }

  return stages
}

export function WorkflowTimeline({
  request,
  execution,
  quotation,
  verification,
  compact = false,
  className = '',
}) {
  const stages = buildStages({ request, execution, quotation, verification })
  if (stages.length === 0) return null

  return (
    <ol className={`relative ${className}`}>
      {stages.map((stage, index) => {
        const style = STATE_STYLES[stage.state] ?? STATE_STYLES.pending
        const Icon = style.icon
        const isLast = index === stages.length - 1

        return (
          <li key={stage.key} className="relative flex gap-3 pb-4 last:pb-0">
            {!isLast ? (
              <span
                className={`absolute left-[13px] top-7 h-[calc(100%-1.75rem)] w-0.5 ${style.line}`}
                aria-hidden="true"
              />
            ) : null}

            <span
              className={`relative z-10 grid h-7 w-7 shrink-0 place-items-center rounded-full ring-4 ${style.dot}`}
            >
              <Icon
                size={14}
                className={stage.state === 'current' ? 'animate-spin' : ''}
                aria-hidden="true"
              />
            </span>

            <div className="min-w-0 flex-1 pt-0.5">
              <div className="flex flex-wrap items-baseline gap-x-2">
                <p className={`text-[13.5px] ${style.title}`}>{stage.label}</p>
                {stage.duration !== undefined && stage.duration !== null && !compact ? (
                  <span className="tnum text-[11.5px] text-slate-400">
                    {stage.duration} ms
                  </span>
                ) : null}
              </div>

              {stage.detail && !compact ? (
                <p className="mt-0.5 text-[12.5px] leading-snug text-slate-500">
                  {stage.detail}
                </p>
              ) : null}

              {stage.errors?.length && !compact ? (
                <ul className="mt-1.5 space-y-1">
                  {stage.errors.map((error, errorIndex) => (
                    <li
                      key={errorIndex}
                      className="rounded border border-rose-200 bg-rose-50 px-2 py-1.5 text-[12px] leading-snug text-rose-700"
                    >
                      {error}
                    </li>
                  ))}
                </ul>
              ) : null}
            </div>
          </li>
        )
      })}
    </ol>
  )
}

/** A horizontal progress strip for list rows and cards. */
export function WorkflowProgress({ request, execution, className = '' }) {
  const stages = buildStages({ request, execution })
  const done = stages.filter((stage) => stage.state === 'complete').length
  const failed = stages.some((stage) => stage.state === 'failed')
  const total = stages.length

  return (
    <div className={className}>
      <div className="flex items-center gap-1">
        {stages.map((stage) => {
          const tone =
            stage.state === 'complete'
              ? 'bg-emerald-400'
              : stage.state === 'current'
                ? 'bg-brand-500'
                : stage.state === 'failed'
                  ? 'bg-rose-400'
                  : stage.state === 'skipped'
                    ? 'bg-slate-300'
                    : 'bg-slate-200'
          return (
            <span
              key={stage.key}
              title={`${stage.label}: ${stage.state}`}
              className={`h-1.5 flex-1 rounded-full ${tone}`}
            />
          )
        })}
      </div>
      <p className="mt-1 text-[11.5px] text-slate-500">
        {failed ? 'Halted' : `Stage ${Math.min(done + 1, total)} of ${total}`}
      </p>
    </div>
  )
}
