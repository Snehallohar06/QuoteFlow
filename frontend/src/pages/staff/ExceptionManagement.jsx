import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import {
  CheckCircle2,
  ClipboardCheck,
  RefreshCw,
  TriangleAlert,
} from 'lucide-react'

import { useToast } from '../../context/ToastContext'
import { useAsync } from '../../hooks/useAsync'
import * as requestsApi from '../../api/requests'
import { PageHeader } from '../../components/layout/PageHeader'
import { Button } from '../../components/ui/Button'
import { Card, CardBody, CardHeader, StatCard } from '../../components/ui/Card'
import { Badge, StatusBadge } from '../../components/ui/Badge'
import { EmptyState, ErrorState, Table } from '../../components/ui/Table'
import { formatMoney, formatRelative } from '../../lib/format'
import { REQUEST_STATUS, exceptionInfo, requestStatusInfo } from '../../lib/status'

/**
 * Exception management.
 *
 * Collects the requests that are not moving on their own and gives staff the
 * one action that can unblock them: re-running the workflow after the
 * underlying data has been corrected. Nothing here bypasses a rule — a re-run
 * follows the same pipeline as a fresh submission, so a request only clears if
 * it genuinely passes now.
 */
export function ExceptionManagement() {
  const toast = useToast()
  const navigate = useNavigate()

  const [reprocessing, setReprocessing] = useState(null)

  const failed = useAsync(
    () =>
      requestsApi.listRequests({
        status: REQUEST_STATUS.VALIDATION_FAILED,
        page_size: 50,
      }),
    []
  )
  const escalated = useAsync(
    () =>
      requestsApi.listRequests({
        status: REQUEST_STATUS.PENDING_APPROVAL,
        page_size: 50,
      }),
    []
  )
  const returned = useAsync(
    () =>
      requestsApi.listRequests({
        status: REQUEST_STATUS.MODIFICATION_REQUESTED,
        page_size: 50,
      }),
    []
  )

  function reloadAll() {
    failed.reload()
    escalated.reload()
    returned.reload()
  }

  async function reprocess(request, event) {
    event?.stopPropagation()
    setReprocessing(request.id)
    try {
      const result = await requestsApi.reprocessRequest(request.id)
      if (result.outcome === 'AUTO_APPROVED') {
        toast.success(
          `${request.request_number} cleared`,
          'The request now passes and a quotation has been issued.'
        )
      } else if (result.outcome === 'PENDING_APPROVAL') {
        toast.info(
          `${request.request_number} escalated`,
          'It passes validation now but needs a manager decision.'
        )
      } else {
        toast.warning(
          `${request.request_number} still failing`,
          result.validation_errors?.[0] ?? 'The same issue remains.'
        )
      }
      reloadAll()
    } catch (error) {
      toast.fromError(error, 'Could not reprocess the request')
    } finally {
      setReprocessing(null)
    }
  }

  const failedRows = failed.data?.items ?? []
  const escalatedRows = escalated.data?.items ?? []
  const returnedRows = returned.data?.items ?? []

  return (
    <>
      <PageHeader
        title="Exception management"
        description="Requests that are blocked, escalated or sent back. Fix the underlying data, then re-run the workflow."
        actions={
          <Button variant="secondary" icon={RefreshCw} onClick={reloadAll}>
            Refresh
          </Button>
        }
      />

      <div className="grid gap-4 sm:grid-cols-3">
        <StatCard
          label="Failed validation"
          value={failed.data?.meta?.total ?? 0}
          icon={TriangleAlert}
          tone={failedRows.length > 0 ? 'rose' : 'slate'}
          loading={failed.loading}
          hint="Blocked — needs a data fix"
        />
        <StatCard
          label="Awaiting approval"
          value={escalated.data?.meta?.total ?? 0}
          icon={ClipboardCheck}
          tone="amber"
          loading={escalated.loading}
          hint="With a sales manager"
        />
        <StatCard
          label="Returned to customer"
          value={returned.data?.meta?.total ?? 0}
          icon={TriangleAlert}
          tone="slate"
          loading={returned.loading}
          hint="Awaiting a resubmission"
        />
      </div>

      <Card className="mt-4">
        <CardHeader
          title="Failed validation"
          description="The rule engine refused these outright. Correct the cause, then re-run."
          icon={TriangleAlert}
        />
        {failed.error ? (
          <ErrorState error={failed.error} onRetry={failed.reload} />
        ) : (
          <Table
            columns={[
              {
                key: 'request_number',
                header: 'Request',
                render: (row) => (
                  <div>
                    <p className="font-mono text-[12.5px] font-medium text-slate-800">
                      {row.request_number}
                    </p>
                    <p className="text-[11.5px] text-slate-500">
                      {row.customer_name} · {formatRelative(row.updated_at)}
                    </p>
                  </div>
                ),
              },
              {
                key: 'reason',
                header: 'Why it failed',
                render: (row) => (
                  <ul className="max-w-xl space-y-0.5">
                    {(row.validation_errors ?? []).slice(0, 2).map((error, index) => (
                      <li
                        key={index}
                        className="text-[12.5px] leading-snug text-rose-700"
                      >
                        {error}
                      </li>
                    ))}
                    {(row.validation_errors?.length ?? 0) > 2 ? (
                      <li className="text-[11.5px] text-slate-500">
                        +{row.validation_errors.length - 2} more
                      </li>
                    ) : null}
                  </ul>
                ),
              },
              {
                key: 'amount',
                header: 'Amount',
                align: 'right',
                render: (row) =>
                  row.pricing ? (
                    <span className="tnum text-[12.5px] text-slate-700">
                      {formatMoney(row.pricing.final_amount, {
                        currency: row.pricing.currency,
                      })}
                    </span>
                  ) : (
                    <span className="text-[12px] text-slate-400">not priced</span>
                  ),
              },
              {
                key: 'actions',
                header: '',
                align: 'right',
                render: (row) => (
                  <Button
                    variant="secondary"
                    size="sm"
                    icon={RefreshCw}
                    loading={reprocessing === row.id}
                    onClick={(event) => reprocess(row, event)}
                  >
                    Re-run
                  </Button>
                ),
              },
            ]}
            rows={failedRows}
            loading={failed.loading}
            onRowClick={(row) => navigate(`/requests/${row.id}`)}
            empty={
              <EmptyState
                icon={CheckCircle2}
                title="Nothing is blocked"
                description="No request is currently failing validation."
              />
            }
          />
        )}
      </Card>

      <Card className="mt-4">
        <CardHeader
          title="Escalated to a manager"
          description="These passed validation but breached a business rule"
          icon={ClipboardCheck}
          action={
            <Button
              variant="ghost"
              size="sm"
              onClick={() => navigate('/approvals')}
            >
              Approval queue
            </Button>
          }
        />
        {escalated.error ? (
          <ErrorState error={escalated.error} onRetry={escalated.reload} />
        ) : (
          <Table
            columns={[
              {
                key: 'request_number',
                header: 'Request',
                render: (row) => (
                  <div>
                    <p className="font-mono text-[12.5px] font-medium text-slate-800">
                      {row.request_number}
                    </p>
                    <p className="text-[11.5px] text-slate-500">{row.customer_name}</p>
                  </div>
                ),
              },
              {
                key: 'exceptions',
                header: 'Rule exceptions',
                render: (row) => (
                  <div className="flex max-w-xl flex-col gap-1">
                    {(row.exceptions ?? []).map((exception, index) => (
                      <div key={index} className="flex items-start gap-1.5">
                        <Badge
                          tone={exceptionInfo(exception.type).tone}
                          size="sm"
                          className="mt-0.5 shrink-0"
                        >
                          {exceptionInfo(exception.type).label}
                        </Badge>
                        <span className="text-[12px] leading-snug text-slate-600">
                          {exception.message}
                        </span>
                      </div>
                    ))}
                  </div>
                ),
              },
              {
                key: 'waiting',
                header: 'Waiting',
                render: (row) => (
                  <span className="text-[12.5px] text-slate-500">
                    {formatRelative(row.submitted_at ?? row.created_at)}
                  </span>
                ),
              },
              {
                key: 'amount',
                header: 'Amount',
                align: 'right',
                render: (row) => (
                  <span className="tnum font-medium text-slate-800">
                    {row.pricing
                      ? formatMoney(row.pricing.final_amount, {
                          currency: row.pricing.currency,
                        })
                      : '—'}
                  </span>
                ),
              },
              {
                key: 'actions',
                header: '',
                align: 'right',
                render: (row) =>
                  row.approval_id ? (
                    <Button
                      variant="secondary"
                      size="sm"
                      onClick={(event) => {
                        event.stopPropagation()
                        navigate(`/approvals/${row.approval_id}`)
                      }}
                    >
                      Open task
                    </Button>
                  ) : null,
              },
            ]}
            rows={escalatedRows}
            loading={escalated.loading}
            onRowClick={(row) => navigate(`/requests/${row.id}`)}
            empty={
              <EmptyState
                icon={CheckCircle2}
                title="Nothing escalated"
                description="Every request is either quoted or closed."
              />
            }
          />
        )}
      </Card>

      {returnedRows.length > 0 ? (
        <Card className="mt-4">
          <CardHeader
            title="Returned to the customer"
            description="A manager asked for changes; waiting on a resubmission"
          />
          <Table
            columns={[
              {
                key: 'request_number',
                header: 'Request',
                render: (row) => (
                  <span className="font-mono text-[12.5px] font-medium text-slate-800">
                    {row.request_number}
                  </span>
                ),
              },
              { key: 'customer_name', header: 'Customer' },
              {
                key: 'status',
                header: 'Status',
                render: (row) => (
                  <StatusBadge info={requestStatusInfo(row.status, row)} size="sm" />
                ),
              },
              {
                key: 'note',
                header: "Manager's note",
                render: (row) => (
                  <span className="block max-w-md text-[12.5px] leading-snug text-slate-600">
                    {row.status_history?.filter((entry) => entry.note).at(-1)?.note ??
                      '—'}
                  </span>
                ),
              },
              {
                key: 'waiting',
                header: 'Returned',
                render: (row) => (
                  <span className="text-[12.5px] text-slate-500">
                    {formatRelative(row.updated_at)}
                  </span>
                ),
              },
            ]}
            rows={returnedRows}
            loading={returned.loading}
            error={returned.error}
            onRowClick={(row) => navigate(`/requests/${row.id}`)}
            empty={<EmptyState title="Nothing returned" />}
          />
        </Card>
      ) : null}

      <Card className="mt-4 border-brand-200 bg-brand-50/50">
        <CardBody>
          <div className="flex items-start gap-2.5">
            <RefreshCw
              size={16}
              className="mt-0.5 shrink-0 text-brand-600"
              aria-hidden="true"
            />
            <div>
              <p className="text-[13px] font-medium text-brand-900">
                What "re-run" does
              </p>
              <p className="mt-1 text-[12.5px] leading-relaxed text-brand-900/80">
                The request goes back through the same six-step pipeline as a fresh
                submission: validation, stock check, pricing, discount rules, approval
                routing and finalisation. It is useful after a price change, a stock
                receipt or reactivating a product — but it cannot override a rule. If
                the cause has not been fixed, the request fails again with the same
                reason.
              </p>
            </div>
          </div>
        </CardBody>
      </Card>
    </>
  )
}
