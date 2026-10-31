import { useState } from 'react'
import { Link, useNavigate, useParams } from 'react-router-dom'
import {
  ArrowRight,
  Ban,
  ClipboardCheck,
  Download,
  FileSearch,
  FileText,
  History,
  PencilLine,
  RefreshCw,
  Send,
  StickyNote,
  User,
} from 'lucide-react'

import { useAuth } from '../../context/AuthContext'
import { useToast } from '../../context/ToastContext'
import { useAsync } from '../../hooks/useAsync'
import * as requestsApi from '../../api/requests'
import * as quotationsApi from '../../api/quotations'
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
import { ConfirmDialog, Modal } from '../../components/ui/Modal'
import { Textarea } from '../../components/ui/Field'
import { ErrorState, PageLoader } from '../../components/ui/Table'
import { WorkflowTimeline } from '../../components/workflow/WorkflowTimeline'
import {
  CheckerFindings,
  EscalationBanner,
  ExecutionBudgetPanel,
  SuccessGatePanel,
} from '../../components/workflow/BoundaryPanel'
import { ExecutionTrace } from '../../components/workflow/ExecutionTrace'
import {
  ExceptionList,
  LineItemsTable,
  PricingSummary,
  ValidationErrors,
} from '../../components/workflow/PricingBreakdown'
import { formatDate, formatDateTime, formatMoney, humanise } from '../../lib/format'
import {
  canCancelRequest,
  canEditRequest,
  isEscalated,
  requestStatusInfo,
} from '../../lib/status'

/**
 * The full picture of one request: status, priced lines, rule verdicts and the
 * workflow trace.
 *
 * This is the page the spec's "display the current status at every stage"
 * requirement lands on. The timeline is derived from the stored execution, so it
 * reflects what the engine actually did rather than an assumed happy path.
 */
export function RequestDetail() {
  const { id } = useParams()
  const { isStaff, isCustomer } = useAuth()
  const toast = useToast()
  const navigate = useNavigate()

  const request = useAsync(() => requestsApi.getRequest(id), [id])
  const executions = useAsync(() => requestsApi.listExecutions(id), [id])

  const [cancelOpen, setCancelOpen] = useState(false)
  const [cancelReason, setCancelReason] = useState('')
  const [notesOpen, setNotesOpen] = useState(false)
  const [internalNotes, setInternalNotes] = useState('')
  const [busy, setBusy] = useState(null)

  const data = request.data
  const latestExecution = executions.data?.[0] ?? null

  // Only loaded when a quotation exists, to populate the last timeline stages.
  const quotation = useAsync(
    () =>
      data?.quotation_id
        ? quotationsApi.getQuotation(data.quotation_id)
        : Promise.resolve(null),
    [data?.quotation_id]
  )

  function reloadAll() {
    request.reload()
    executions.reload()
  }

  async function onSubmit() {
    setBusy('submit')
    try {
      const result = await requestsApi.submitRequest(id)
      if (result.outcome === 'AUTO_APPROVED') {
        toast.success('Approved automatically', 'The quotation is ready to download.')
      } else if (result.outcome === 'PENDING_APPROVAL') {
        toast.info(
          'Sent for approval',
          `${result.exceptions.length} exception(s) need a manager's decision.`
        )
      } else {
        toast.warning(
          'Validation failed',
          result.validation_errors?.[0] ?? 'The request could not be processed.'
        )
      }
      reloadAll()
    } catch (error) {
      toast.fromError(error, 'Could not submit the request')
    } finally {
      setBusy(null)
    }
  }

  async function onReprocess() {
    setBusy('reprocess')
    try {
      const result = await requestsApi.reprocessRequest(id)
      toast.success(
        'Workflow re-run',
        `Outcome: ${humanise(result.outcome)}.`
      )
      reloadAll()
    } catch (error) {
      toast.fromError(error, 'Could not reprocess the request')
    } finally {
      setBusy(null)
    }
  }

  async function onCancel() {
    setBusy('cancel')
    try {
      await requestsApi.cancelRequest(id, cancelReason || undefined)
      toast.success('Request cancelled')
      setCancelOpen(false)
      setCancelReason('')
      reloadAll()
    } catch (error) {
      toast.fromError(error, 'Could not cancel the request')
    } finally {
      setBusy(null)
    }
  }

  async function onSaveNotes() {
    setBusy('notes')
    try {
      await requestsApi.setInternalNotes(id, internalNotes)
      toast.success('Internal notes saved')
      setNotesOpen(false)
      request.reload()
    } catch (error) {
      toast.fromError(error, 'Could not save the notes')
    } finally {
      setBusy(null)
    }
  }

  if (request.loading && !data) return <PageLoader label="Loading request" />
  if (request.error) {
    return (
      <Card>
        <ErrorState error={request.error} onRetry={request.reload} />
      </Card>
    )
  }
  if (!data) return null

  const statusInfo = requestStatusInfo(data.status, data)
  const currency = data.pricing?.currency ?? 'INR'

  return (
    <>
      <PageHeader
        title={data.request_number}
        description={`${data.customer_name} · ${data.customer_code}`}
        breadcrumbs={[
          { label: 'Requests', to: '/requests' },
          { label: data.request_number },
        ]}
        meta={
          <div className="flex flex-wrap items-center gap-1.5">
            <StatusBadge info={statusInfo} size="lg" />
            {isEscalated(data) ? <Badge tone="warning">Escalated</Badge> : null}
            {data.revision > 0 ? (
              <Badge tone="neutral">Revision {data.revision}</Badge>
            ) : null}
          </div>
        }
        actions={
          <>
            <Button variant="secondary" icon={RefreshCw} onClick={reloadAll}>
              Refresh
            </Button>

            {canEditRequest(data) ? (
              <>
                <Button
                  variant="secondary"
                  icon={PencilLine}
                  onClick={() =>
                    navigate('/requests/new', {
                      state: { editRequestId: data.id },
                    })
                  }
                >
                  Edit lines
                </Button>
                <Button
                  icon={Send}
                  loading={busy === 'submit'}
                  onClick={onSubmit}
                >
                  {data.status === 'DRAFT' ? 'Submit' : 'Resubmit'}
                </Button>
              </>
            ) : null}

            {isStaff &&
            !['APPROVED', 'REJECTED', 'CANCELLED', 'PENDING_APPROVAL'].includes(
              data.status
            ) ? (
              <Button
                variant="secondary"
                icon={RefreshCw}
                loading={busy === 'reprocess'}
                onClick={onReprocess}
              >
                Re-run workflow
              </Button>
            ) : null}

            {data.approval_id && isStaff ? (
              <Button
                variant="navy"
                icon={ClipboardCheck}
                onClick={() => navigate(`/approvals/${data.approval_id}`)}
              >
                Open approval
              </Button>
            ) : null}

            {data.quotation_id ? (
              <Button
                icon={FileText}
                onClick={() => navigate(`/quotations/${data.quotation_id}`)}
              >
                View quotation
              </Button>
            ) : null}

            {canCancelRequest(data) ? (
              <Button variant="ghost" icon={Ban} onClick={() => setCancelOpen(true)}>
                Cancel
              </Button>
            ) : null}
          </>
        }
      />

      <EscalationBanner request={data} className="mb-4" />

      {data.validation_errors?.length ? (
        <ValidationErrors errors={data.validation_errors} className="mb-4" />
      ) : null}

      {latestExecution?.steps?.some(
        (step) => step.step === 'VERIFY_DOCUMENT' && step.status === 'FAILED'
      ) ? (
        <CheckerFindings
          report={
            latestExecution.steps.find(
              (step) => step.step === 'VERIFY_DOCUMENT'
            )?.output
          }
          className="mb-4"
        />
      ) : null}

      {data.status === 'MODIFICATION_REQUESTED' ? (
        <Card className="mb-4 border-amber-200 bg-amber-50/60">
          <CardBody>
            <div className="flex items-start gap-2.5">
              <PencilLine
                size={16}
                className="mt-0.5 shrink-0 text-amber-600"
                aria-hidden="true"
              />
              <div>
                <p className="text-[13px] font-semibold text-amber-900">
                  The sales manager has asked for changes
                </p>
                <p className="mt-1 text-[12.5px] leading-snug text-amber-900/85">
                  {data.status_history?.filter((entry) => entry.note).at(-1)?.note ??
                    'Review the request and resubmit it.'}
                </p>
                {isCustomer ? (
                  <p className="mt-2 text-[11.5px] text-amber-700">
                    Edit the lines and resubmit — this will count as revision{' '}
                    {data.revision + 1}.
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
              title="Priced lines"
              description={
                data.pricing
                  ? 'Every figure below was computed by the backend pricing engine'
                  : 'This request has not been priced yet'
              }
            />
            <LineItemsTable items={data.items} currency={currency} />
            <div className="border-t border-slate-200">
              <PricingSummary pricing={data.pricing} />
            </div>
          </Card>

          {data.exceptions?.length ? (
            <Card>
              <CardHeader
                title="Rule exceptions"
                description="Why this request needs a manager's decision"
              />
              <CardBody>
                <ExceptionList exceptions={data.exceptions} />
              </CardBody>
            </Card>
          ) : null}

          <Card>
            <CardHeader
              title="Workflow execution"
              description="The step-by-step trace recorded by the rule engine"
              icon={FileSearch}
              action={
                executions.data?.length > 1 ? (
                  <Badge tone="neutral" size="sm">
                    {executions.data.length} runs
                  </Badge>
                ) : null
              }
            />
            {executions.loading ? (
              <div className="px-4 py-6 sm:px-5">
                <div className="space-y-2">
                  {[0, 1, 2].map((index) => (
                    <div key={index} className="h-9 animate-pulse rounded bg-slate-100" />
                  ))}
                </div>
              </div>
            ) : executions.error ? (
              <ErrorState error={executions.error} onRetry={executions.reload} />
            ) : !executions.data?.length ? (
              <CardBody>
                <p className="text-[13px] text-slate-500">
                  No workflow run recorded yet. Submitting the request runs the pipeline.
                </p>
              </CardBody>
            ) : (
              <div className="divide-y divide-slate-200">
                {executions.data.map((execution) => (
                  <ExecutionTrace key={execution.id} execution={execution} />
                ))}
              </div>
            )}
          </Card>
        </div>

        <div className="space-y-4">
          <Card>
            <CardHeader title="Process stage" icon={ArrowRight} />
            <CardBody>
              <WorkflowTimeline
                request={data}
                execution={latestExecution}
                quotation={quotation.data}
              />
            </CardBody>
          </Card>

          <SuccessGatePanel gate={latestExecution?.gate} />

          <ExecutionBudgetPanel request={data} execution={latestExecution} />

          <Card>
            <CardHeader title="Request details" icon={User} />
            <CardBody>
              <DetailList>
                <DetailRow label="Request number" value={data.request_number} mono />
                <DetailRow label="Customer" value={data.customer_name} />
                <DetailRow label="Customer code" value={data.customer_code} mono />
                <DetailRow
                  label="Raised by"
                  value={humanise(data.created_by_role)}
                />
                <DetailRow label="Created" value={formatDateTime(data.created_at)} />
                <DetailRow
                  label="Submitted"
                  value={
                    data.submitted_at ? formatDateTime(data.submitted_at) : 'Not yet'
                  }
                />
                {data.decided_at ? (
                  <DetailRow label="Decided" value={formatDateTime(data.decided_at)} />
                ) : null}
                {data.expected_delivery_date ? (
                  <DetailRow
                    label="Required by"
                    value={formatDate(data.expected_delivery_date)}
                  />
                ) : null}
                {data.pricing ? (
                  <DetailRow
                    label="Final amount"
                    value={formatMoney(data.pricing.final_amount, { currency })}
                  />
                ) : null}
              </DetailList>
            </CardBody>
          </Card>

          {data.customer_notes ? (
            <Card>
              <CardHeader title="Customer notes" icon={StickyNote} />
              <CardBody>
                <p className="whitespace-pre-wrap text-[13px] leading-relaxed text-slate-600">
                  {data.customer_notes}
                </p>
              </CardBody>
            </Card>
          ) : null}

          {isStaff ? (
            <Card>
              <CardHeader
                title="Internal notes"
                description="Never shown to the customer"
                icon={StickyNote}
                action={
                  <Button
                    variant="ghost"
                    size="sm"
                    icon={PencilLine}
                    onClick={() => {
                      setInternalNotes(data.internal_notes ?? '')
                      setNotesOpen(true)
                    }}
                  >
                    Edit
                  </Button>
                }
              />
              <CardBody>
                {data.internal_notes ? (
                  <p className="whitespace-pre-wrap text-[13px] leading-relaxed text-slate-600">
                    {data.internal_notes}
                  </p>
                ) : (
                  <p className="text-[13px] italic text-slate-400">
                    No internal notes on this request.
                  </p>
                )}
              </CardBody>
            </Card>
          ) : null}

          <Card>
            <CardHeader title="Status history" icon={History} />
            <CardBody>
              <ol className="space-y-3">
                {(data.status_history ?? []).map((entry, index) => (
                  <li key={index} className="flex gap-2.5">
                    <span className="mt-1.5 h-1.5 w-1.5 shrink-0 rounded-full bg-slate-300" />
                    <div className="min-w-0">
                      <p className="text-[12.5px] font-medium text-slate-700">
                        {requestStatusInfo(entry.to_status).label}
                        {entry.from_status ? (
                          <span className="font-normal text-slate-400">
                            {' '}
                            from {requestStatusInfo(entry.from_status).label}
                          </span>
                        ) : null}
                      </p>
                      {entry.note ? (
                        <p className="mt-0.5 text-[12px] leading-snug text-slate-500">
                          {entry.note}
                        </p>
                      ) : null}
                      <p className="mt-0.5 text-[11px] text-slate-400">
                        {formatDateTime(entry.at)}
                        {entry.actor_name ? ` · ${entry.actor_name}` : ''}
                      </p>
                    </div>
                  </li>
                ))}
              </ol>
            </CardBody>
          </Card>

          {data.quotation_id ? (
            <Card className="border-emerald-200 bg-emerald-50/50">
              <CardBody>
                <div className="flex items-start gap-2.5">
                  <Download
                    size={16}
                    className="mt-0.5 shrink-0 text-emerald-600"
                    aria-hidden="true"
                  />
                  <div>
                    <p className="text-[13px] font-semibold text-emerald-900">
                      Quotation issued
                    </p>
                    <p className="mt-1 text-[12.5px] leading-snug text-emerald-900/80">
                      The verified document is ready to download.
                    </p>
                    <Link
                      to={`/quotations/${data.quotation_id}`}
                      className="mt-2 inline-flex items-center gap-1 text-[12.5px] font-medium text-emerald-800 underline-offset-2 hover:underline"
                    >
                      Open the quotation
                      <ArrowRight size={13} aria-hidden="true" />
                    </Link>
                  </div>
                </div>
              </CardBody>
            </Card>
          ) : null}
        </div>
      </div>

      <ConfirmDialog
        open={cancelOpen}
        onClose={() => setCancelOpen(false)}
        onConfirm={onCancel}
        title="Cancel this request?"
        message={`${data.request_number} will be closed and can no longer be processed. Any open approval task is withdrawn. This cannot be undone.`}
        confirmLabel="Cancel request"
        cancelLabel="Keep it open"
        loading={busy === 'cancel'}
      >
        <Textarea
          label="Reason (optional)"
          value={cancelReason}
          rows={2}
          maxLength={500}
          placeholder="Project postponed, ordered elsewhere…"
          onChange={(event) => setCancelReason(event.target.value)}
        />
      </ConfirmDialog>

      <Modal
        open={notesOpen}
        onClose={() => setNotesOpen(false)}
        title="Internal notes"
        description="Visible to sales staff and managers only."
        footer={
          <>
            <Button variant="secondary" onClick={() => setNotesOpen(false)}>
              Cancel
            </Button>
            <Button loading={busy === 'notes'} onClick={onSaveNotes}>
              Save notes
            </Button>
          </>
        }
      >
        <Textarea
          label="Notes"
          value={internalNotes}
          rows={6}
          maxLength={2000}
          onChange={(event) => setInternalNotes(event.target.value)}
          hint={`${internalNotes.length}/2000`}
        />
      </Modal>
    </>
  )
}
