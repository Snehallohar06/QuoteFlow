import { useMemo, useState } from 'react'
import { useNavigate, useParams } from 'react-router-dom'
import {
  AlertTriangle,
  Building2,
  CheckCircle2,
  Clock,
  FileSearch,
  Info,
  PencilLine,
  Wallet,
  XCircle,
} from 'lucide-react'

import { useAuth } from '../../context/AuthContext'
import { useToast } from '../../context/ToastContext'
import { useAsync } from '../../hooks/useAsync'
import * as approvalsApi from '../../api/approvals'
import * as settingsApi from '../../api/settings'
import { PageHeader } from '../../components/layout/PageHeader'
import { Button } from '../../components/ui/Button'
import {
  Card,
  CardBody,
  CardHeader,
  DetailList,
  DetailRow,
} from '../../components/ui/Card'
import { Badge, StatusBadge } from '../../components/ui/Badge'
import { Input, Textarea } from '../../components/ui/Field'
import { Modal } from '../../components/ui/Modal'
import { ErrorState, PageLoader } from '../../components/ui/Table'
import { ExecutionTrace } from '../../components/workflow/ExecutionTrace'
import {
  ExceptionList,
  LineItemsTable,
  PricingSummary,
} from '../../components/workflow/PricingBreakdown'
import { formatDateTime, formatMoney, formatPercent, formatRelative } from '../../lib/format'
import { approvalStatusInfo, customerStatusInfo, tierInfo } from '../../lib/status'

/**
 * The manager decision screen.
 *
 * Everything needed for a decision is on one page: the customer, the priced
 * lines with requested vs allowed discount, the totals, the rule verdicts and
 * the engine's own trace. The three actions post to the real approval endpoint;
 * a rejection or a modification request requires a comment, which the backend
 * also enforces.
 */
export function ApprovalDetail() {
  const { id } = useParams()
  const { isManager } = useAuth()
  const toast = useToast()
  const navigate = useNavigate()

  const approval = useAsync(() => approvalsApi.getApproval(id), [id])
  const policy = useAsync(() => settingsApi.getDiscountPolicy(), [])

  const [dialog, setDialog] = useState(null) // 'APPROVE' | 'REJECT' | 'REQUEST_MODIFICATION'
  const [comments, setComments] = useState('')
  const [override, setOverride] = useState('')
  const [useOverride, setUseOverride] = useState(false)
  const [errors, setErrors] = useState({})
  const [pending, setPending] = useState(false)

  const data = approval.data
  const task = data?.approval
  const request = data?.request
  const customer = data?.customer

  const absoluteMax = policy.data?.absolute_max_discount_percent

  /** What the totals become if the override is applied to every line. */
  const overridePreview = useMemo(() => {
    if (!useOverride || override === '' || !request?.items) return null
    const percent = Number(override)
    if (Number.isNaN(percent)) return null

    const taxRateDefault = policy.data?.tax_policy?.rate_percent ?? 0
    let subtotal = 0
    let discount = 0
    let tax = 0
    for (const line of request.items) {
      const gross = line.unit_price * line.quantity
      const lineDiscount = (gross * percent) / 100
      const taxable = gross - lineDiscount
      const rate = line.tax_rate ?? taxRateDefault
      subtotal += gross
      discount += lineDiscount
      tax += (taxable * rate) / 100
    }
    const taxable = subtotal - discount
    return { subtotal, discount, taxable, tax, total: taxable + tax }
  }, [useOverride, override, request, policy.data])

  function openDialog(decision) {
    setDialog(decision)
    setComments('')
    setOverride('')
    setUseOverride(false)
    setErrors({})
  }

  function validateDecision() {
    const next = {}
    if (dialog !== 'APPROVE' && !comments.trim()) {
      next.comments =
        'A comment is required so the customer understands the decision.'
    }
    if (dialog === 'APPROVE' && useOverride) {
      if (override === '') {
        next.override = 'Enter the discount you are authorising.'
      } else {
        const value = Number(override)
        if (Number.isNaN(value) || value < 0 || value > 100) {
          next.override = 'Enter a percentage between 0 and 100.'
        } else if (absoluteMax !== undefined && value > absoluteMax) {
          next.override = `Company policy caps any approval at ${formatPercent(absoluteMax)}.`
        }
      }
    }
    setErrors(next)
    return Object.keys(next).length === 0
  }

  async function submitDecision() {
    if (!validateDecision()) return

    setPending(true)
    try {
      const result = await approvalsApi.decide(id, {
        decision: dialog,
        comments: comments.trim() || undefined,
        override_discount_percent:
          dialog === 'APPROVE' && useOverride ? Number(override) : undefined,
      })

      if (dialog === 'APPROVE') {
        toast.success(
          `${task.request_number} approved`,
          result.quotation_id
            ? 'The quotation has been generated and is ready for the customer.'
            : 'The decision was recorded.'
        )
        if (result.quotation_id) {
          navigate(`/quotations/${result.quotation_id}`)
          return
        }
      } else if (dialog === 'REJECT') {
        toast.success(`${task.request_number} rejected`, 'The customer has been notified.')
      } else {
        toast.success(
          `Changes requested on ${task.request_number}`,
          'The customer can now edit and resubmit.'
        )
      }

      setDialog(null)
      approval.reload()
    } catch (error) {
      // The backend refuses an approval whose request went stale, and reopens
      // the task. Surface that rather than pretending the decision stuck.
      toast.fromError(error, 'The decision could not be recorded')
      if (error.details?.validation_errors) {
        setErrors({
          comments: `The request no longer passes validation: ${error.details.validation_errors[0]}`,
        })
      }
      approval.reload()
    } finally {
      setPending(false)
    }
  }

  if (approval.loading && !data) return <PageLoader label="Loading approval" />
  if (approval.error) {
    return (
      <Card>
        <ErrorState error={approval.error} onRetry={approval.reload} />
      </Card>
    )
  }
  if (!data) return null

  const isOpen = task.status === 'PENDING'
  const overdue = task.sla_due_at && new Date(task.sla_due_at) < new Date()
  const currency = request?.pricing?.currency ?? 'INR'
  const maxRequested = Math.max(
    ...(request?.items ?? []).map((line) => line.applied_discount_percent ?? 0),
    0
  )
  const maxAllowed = Math.max(
    ...(request?.items ?? []).map((line) => line.max_allowed_discount_percent ?? 0),
    0
  )

  return (
    <>
      <PageHeader
        title={`Approval · ${task.request_number}`}
        description={`${task.customer_name} — raised ${formatRelative(task.created_at)}`}
        breadcrumbs={[
          { label: 'Approvals', to: '/approvals' },
          { label: task.request_number },
        ]}
        meta={
          <div className="flex flex-wrap items-center gap-1.5">
            <StatusBadge info={approvalStatusInfo(task.status)} size="lg" />
            {isOpen && overdue ? <Badge tone="danger">Past SLA</Badge> : null}
          </div>
        }
        actions={
          <Button
            variant="secondary"
            icon={FileSearch}
            onClick={() => navigate(`/requests/${task.request_id}`)}
          >
            Full request
          </Button>
        }
      />

      {!isOpen ? (
        <Card className="mb-4 border-slate-300 bg-slate-50">
          <CardBody>
            <div className="flex items-start gap-2.5">
              <Info
                size={16}
                className="mt-0.5 shrink-0 text-slate-500"
                aria-hidden="true"
              />
              <div>
                <p className="text-[13px] font-semibold text-slate-800">
                  This task has already been resolved
                </p>
                <p className="mt-1 text-[12.5px] leading-snug text-slate-600">
                  {approvalStatusInfo(task.status).label} by{' '}
                  {task.decided_by_name ?? 'a sales manager'} on{' '}
                  {formatDateTime(task.decided_at)}.
                  {task.override_discount_percent !== null &&
                  task.override_discount_percent !== undefined
                    ? ` An override of ${formatPercent(task.override_discount_percent)} was applied.`
                    : ''}
                </p>
                {task.comments ? (
                  <p className="mt-2 rounded border border-slate-200 bg-white px-2.5 py-2 text-[12.5px] italic leading-snug text-slate-600">
                    “{task.comments}”
                  </p>
                ) : null}
              </div>
            </div>
          </CardBody>
        </Card>
      ) : null}

      <div className="grid gap-4 lg:grid-cols-[1fr_340px]">
        <div className="space-y-4">
          <Card>
            <CardHeader
              title="What is being asked"
              description="The discount requested against the ceiling the policy allows"
            />
            <CardBody>
              <div className="grid gap-4 sm:grid-cols-3">
                <div className="rounded-md bg-amber-50 px-3 py-2.5 ring-1 ring-amber-200">
                  <p className="text-[11.5px] font-medium uppercase tracking-wide text-amber-800">
                    Discount requested
                  </p>
                  <p className="tnum mt-1 text-[22px] font-semibold leading-none text-amber-900">
                    {formatPercent(maxRequested)}
                  </p>
                </div>
                <div className="rounded-md bg-slate-50 px-3 py-2.5 ring-1 ring-slate-200">
                  <p className="text-[11.5px] font-medium uppercase tracking-wide text-slate-500">
                    Policy allows
                  </p>
                  <p className="tnum mt-1 text-[22px] font-semibold leading-none text-slate-800">
                    {formatPercent(maxAllowed)}
                  </p>
                </div>
                <div className="rounded-md bg-navy-50 px-3 py-2.5 ring-1 ring-navy-200">
                  <p className="text-[11.5px] font-medium uppercase tracking-wide text-navy-700">
                    Final amount
                  </p>
                  <p className="tnum mt-1 text-[22px] font-semibold leading-none text-navy-800">
                    {formatMoney(task.requested_amount, { currency })}
                  </p>
                </div>
              </div>
            </CardBody>
          </Card>

          <Card>
            <CardHeader
              title="Validation results"
              description="The rule verdicts that sent this request for review"
              icon={AlertTriangle}
            />
            <CardBody>
              <ExceptionList exceptions={task.exceptions} />
              {!task.exceptions?.length ? (
                <p className="text-[13px] text-slate-500">
                  No exceptions recorded on this task.
                </p>
              ) : null}
            </CardBody>
          </Card>

          <Card>
            <CardHeader
              title="Product and pricing detail"
              description="Unit prices, quantities, discount and tax per line"
            />
            <LineItemsTable items={request?.items ?? []} currency={currency} />
            <div className="border-t border-slate-200">
              <PricingSummary pricing={request?.pricing} />
            </div>
          </Card>

          {data.latest_execution ? (
            <Card>
              <CardHeader
                title="Workflow trace"
                description="What the rule engine computed and decided"
                icon={FileSearch}
              />
              <ExecutionTrace execution={data.latest_execution} />
            </Card>
          ) : null}
        </div>

        <div className="space-y-4">
          {isOpen && isManager ? (
            <Card className="border-brand-200">
              <CardHeader
                title="Your decision"
                description="Each action posts to the backend and updates the request"
              />
              <CardBody className="space-y-2">
                <Button
                  variant="success"
                  size="lg"
                  icon={CheckCircle2}
                  className="w-full justify-center"
                  onClick={() => openDialog('APPROVE')}
                >
                  Approve
                </Button>
                <Button
                  variant="secondary"
                  icon={PencilLine}
                  className="w-full justify-center"
                  onClick={() => openDialog('REQUEST_MODIFICATION')}
                >
                  Request modification
                </Button>
                <Button
                  variant="danger"
                  icon={XCircle}
                  className="w-full justify-center"
                  onClick={() => openDialog('REJECT')}
                >
                  Reject
                </Button>
                <p className="pt-1 text-[11.5px] leading-snug text-slate-500">
                  Approving re-runs the pricing pipeline and issues the quotation.
                  Rejecting or requesting changes returns the request to the customer
                  with your comment.
                </p>
              </CardBody>
            </Card>
          ) : isOpen && !isManager ? (
            <Card className="border-amber-200 bg-amber-50/60">
              <CardBody>
                <p className="text-[13px] font-semibold text-amber-900">
                  Awaiting a manager
                </p>
                <p className="mt-1 text-[12.5px] leading-snug text-amber-900/80">
                  You can review everything here, but only a sales manager can record the
                  decision.
                </p>
              </CardBody>
            </Card>
          ) : null}

          <Card>
            <CardHeader title="Customer" icon={Building2} />
            <CardBody>
              {customer ? (
                <>
                  <p className="text-[14px] font-semibold text-navy-800">
                    {customer.company_name}
                  </p>
                  <p className="font-mono text-[11.5px] text-slate-500">
                    {customer.code}
                  </p>
                  <div className="mt-2 flex flex-wrap gap-1.5">
                    <Badge tone={tierInfo(customer.tier).tone} size="sm">
                      {tierInfo(customer.tier).label} tier
                    </Badge>
                    <Badge tone={customerStatusInfo(customer.status).tone} size="sm">
                      {customerStatusInfo(customer.status).label}
                    </Badge>
                  </div>

                  <DetailList className="mt-3">
                    <DetailRow label="Contact" value={customer.contact_name} />
                    <DetailRow label="Email" value={customer.email} />
                    <DetailRow label="Phone" value={customer.phone} />
                  </DetailList>

                  <div className="mt-3 rounded-md bg-slate-50 px-3 py-2.5">
                    <p className="flex items-center gap-1.5 text-[11.5px] font-medium uppercase tracking-wide text-slate-500">
                      <Wallet size={12} aria-hidden="true" />
                      Credit position
                    </p>
                    <DetailList className="mt-1">
                      <DetailRow
                        label="Limit"
                        value={
                          customer.credit_limit > 0
                            ? formatMoney(customer.credit_limit)
                            : 'Not set'
                        }
                      />
                      <DetailRow
                        label="Outstanding"
                        value={formatMoney(customer.outstanding_amount)}
                      />
                      <DetailRow
                        label="Available"
                        value={
                          <span
                            className={
                              customer.available_credit < Number(task.requested_amount)
                                ? 'text-rose-600'
                                : undefined
                            }
                          >
                            {formatMoney(customer.available_credit)}
                          </span>
                        }
                      />
                    </DetailList>
                  </div>

                  <Button
                    variant="ghost"
                    size="sm"
                    className="mt-2 w-full justify-center"
                    onClick={() => navigate(`/customers/${customer.id}`)}
                  >
                    Open customer profile
                  </Button>
                </>
              ) : (
                <p className="text-[13px] text-slate-500">
                  The customer record could not be loaded.
                </p>
              )}
            </CardBody>
          </Card>

          <Card>
            <CardHeader title="Task details" icon={Clock} />
            <CardBody>
              <DetailList>
                <DetailRow label="Request" value={task.request_number} mono />
                <DetailRow label="Raised" value={formatDateTime(task.created_at)} />
                <DetailRow
                  label="SLA due"
                  value={
                    <span className={overdue && isOpen ? 'text-rose-600' : undefined}>
                      {formatDateTime(task.sla_due_at)}
                    </span>
                  }
                />
                <DetailRow
                  label="Discount asked"
                  value={formatPercent(task.requested_discount_percent)}
                />
                <DetailRow
                  label="Amount"
                  value={formatMoney(task.requested_amount, { currency })}
                />
              </DetailList>
            </CardBody>
          </Card>

          {data.recent_quotations?.length ? (
            <Card>
              <CardHeader
                title="Recent quotations"
                description="Previous documents for this customer"
              />
              <CardBody padded={false}>
                <ul className="divide-y divide-slate-100">
                  {data.recent_quotations.map((quotation) => (
                    <li
                      key={quotation.id}
                      role="button"
                      tabIndex={0}
                      onClick={() => navigate(`/quotations/${quotation.id}`)}
                      onKeyDown={(event) => {
                        if (event.key === 'Enter')
                          navigate(`/quotations/${quotation.id}`)
                      }}
                      className="flex cursor-pointer items-center justify-between gap-3 px-4 py-2.5 transition hover:bg-brand-50/50 sm:px-5"
                    >
                      <div className="min-w-0">
                        <p className="font-mono text-[12px] font-medium text-slate-800">
                          {quotation.quotation_number}
                        </p>
                        <p className="text-[11px] text-slate-500">
                          {formatRelative(quotation.issued_at)}
                        </p>
                      </div>
                      <span className="tnum shrink-0 text-[12.5px] font-medium text-slate-700">
                        {formatMoney(quotation.pricing.final_amount, {
                          currency: quotation.pricing.currency,
                        })}
                      </span>
                    </li>
                  ))}
                </ul>
              </CardBody>
            </Card>
          ) : null}
        </div>
      </div>

      {/* ---- Decision dialog -------------------------------------------- */}
      <Modal
        open={Boolean(dialog)}
        onClose={pending ? undefined : () => setDialog(null)}
        title={
          dialog === 'APPROVE'
            ? `Approve ${task.request_number}?`
            : dialog === 'REJECT'
              ? `Reject ${task.request_number}?`
              : `Request changes on ${task.request_number}?`
        }
        description={
          dialog === 'APPROVE'
            ? 'The pricing pipeline is re-run and a verified quotation is issued to the customer.'
            : dialog === 'REJECT'
              ? 'The request is closed. The customer is notified with your comment.'
              : 'The request returns to the customer, who can edit and resubmit it.'
        }
        footer={
          <>
            <Button
              variant="secondary"
              onClick={() => setDialog(null)}
              disabled={pending}
            >
              Cancel
            </Button>
            <Button
              variant={
                dialog === 'APPROVE'
                  ? 'success'
                  : dialog === 'REJECT'
                    ? 'danger'
                    : 'primary'
              }
              loading={pending}
              onClick={submitDecision}
            >
              {dialog === 'APPROVE'
                ? 'Approve and issue'
                : dialog === 'REJECT'
                  ? 'Reject request'
                  : 'Request changes'}
            </Button>
          </>
        }
      >
        <div className="space-y-4">
          {dialog === 'APPROVE' ? (
            <>
              <div className="rounded-md bg-slate-50 px-3 py-2.5">
                <p className="text-[12.5px] text-slate-600">
                  Approving as requested applies{' '}
                  <span className="font-semibold text-slate-800">
                    {formatPercent(maxRequested)}
                  </span>{' '}
                  and issues a quotation for{' '}
                  <span className="font-semibold text-slate-800">
                    {formatMoney(task.requested_amount, { currency })}
                  </span>
                  .
                </p>
              </div>

              <label className="flex items-start gap-2.5">
                <input
                  type="checkbox"
                  checked={useOverride}
                  onChange={(event) => {
                    setUseOverride(event.target.checked)
                    setErrors({})
                  }}
                  className="mt-0.5 h-4 w-4 rounded border-slate-300 text-brand-600 focus:ring-2 focus:ring-brand-500"
                />
                <span>
                  <span className="text-[13.5px] font-medium text-slate-800">
                    Apply a different discount instead
                  </span>
                  <span className="mt-0.5 block text-[12px] leading-snug text-slate-500">
                    Your figure replaces the requested discount on every line, and the
                    quotation is repriced.
                  </span>
                </span>
              </label>

              {useOverride ? (
                <>
                  <Input
                    label="Discount to authorise"
                    type="number"
                    min={0}
                    max={100}
                    step="0.5"
                    value={override}
                    error={errors.override}
                    prefix="%"
                    onChange={(event) => setOverride(event.target.value)}
                    hint={
                      absoluteMax !== undefined
                        ? `Policy permits up to ${formatPercent(absoluteMax)} with approval`
                        : undefined
                    }
                    className="sm:max-w-48"
                  />

                  {overridePreview ? (
                    <div className="rounded-md border border-brand-200 bg-brand-50/60 px-3 py-2.5">
                      <p className="text-[11.5px] font-semibold uppercase tracking-wide text-brand-800">
                        Repriced totals
                      </p>
                      <dl className="mt-1.5 space-y-1">
                        <div className="flex justify-between gap-4 text-[12.5px]">
                          <dt className="text-slate-600">Subtotal</dt>
                          <dd className="tnum font-medium text-slate-800">
                            {formatMoney(overridePreview.subtotal, { currency })}
                          </dd>
                        </div>
                        <div className="flex justify-between gap-4 text-[12.5px]">
                          <dt className="text-slate-600">Discount</dt>
                          <dd className="tnum font-medium text-emerald-700">
                            −{formatMoney(overridePreview.discount, { currency })}
                          </dd>
                        </div>
                        <div className="flex justify-between gap-4 text-[12.5px]">
                          <dt className="text-slate-600">Tax</dt>
                          <dd className="tnum font-medium text-slate-800">
                            {formatMoney(overridePreview.tax, { currency })}
                          </dd>
                        </div>
                        <div className="flex justify-between gap-4 border-t border-brand-200 pt-1.5 text-[13px]">
                          <dt className="font-semibold text-navy-800">New total</dt>
                          <dd className="tnum font-semibold text-navy-800">
                            {formatMoney(overridePreview.total, { currency })}
                          </dd>
                        </div>
                      </dl>
                      <p className="mt-2 text-[11px] leading-snug text-brand-900/70">
                        An estimate. The backend recomputes every figure when the
                        quotation is issued.
                      </p>
                    </div>
                  ) : null}
                </>
              ) : null}

              <Textarea
                label="Approval comment (optional)"
                value={comments}
                rows={3}
                maxLength={2000}
                placeholder="Strategic account; volume justifies the discount."
                onChange={(event) => setComments(event.target.value)}
              />
            </>
          ) : (
            <Textarea
              label={
                dialog === 'REJECT'
                  ? 'Reason for rejection'
                  : 'What needs to change'
              }
              value={comments}
              rows={4}
              maxLength={2000}
              required
              error={errors.comments}
              placeholder={
                dialog === 'REJECT'
                  ? 'Margin is too thin at this discount. Resubmit at 5% or less.'
                  : 'Please split this across two deliveries and resubmit.'
              }
              onChange={(event) => {
                setComments(event.target.value)
                if (errors.comments) setErrors({})
              }}
              hint={
                errors.comments
                  ? undefined
                  : 'The customer sees this comment, so be specific.'
              }
            />
          )}
        </div>
      </Modal>
    </>
  )
}
