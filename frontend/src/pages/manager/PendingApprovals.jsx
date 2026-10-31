import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { ClipboardCheck, Clock, RefreshCw, TriangleAlert } from 'lucide-react'

import { useAuth } from '../../context/AuthContext'
import { useAsync } from '../../hooks/useAsync'
import * as approvalsApi from '../../api/approvals'
import { PageHeader } from '../../components/layout/PageHeader'
import { Button } from '../../components/ui/Button'
import { Card, StatCard } from '../../components/ui/Card'
import { Badge, StatusBadge } from '../../components/ui/Badge'
import { Checkbox } from '../../components/ui/Field'
import {
  EmptyState,
  NoResultsState,
  Pagination,
  Table,
} from '../../components/ui/Table'
import { FilterSelect, Toolbar } from '../../components/ui/Toolbar'
import { formatMoney, formatPercent, formatRelative } from '../../lib/format'
import { APPROVAL_STATUS_OPTIONS, approvalStatusInfo, exceptionInfo } from '../../lib/status'

export function PendingApprovals() {
  const { isManager } = useAuth()
  const navigate = useNavigate()

  const [status, setStatus] = useState('PENDING')
  const [overdueOnly, setOverdueOnly] = useState(false)
  const [page, setPage] = useState(1)

  const approvals = useAsync(
    () =>
      approvalsApi.listApprovals({
        page,
        page_size: 20,
        status,
        overdue_only: overdueOnly || undefined,
      }),
    [page, status, overdueOnly]
  )

  const rows = approvals.data?.items ?? []
  const pendingRows = rows.filter((row) => row.status === 'PENDING')
  const overdueCount = pendingRows.filter(
    (row) => row.sla_due_at && new Date(row.sla_due_at) < new Date()
  ).length
  const totalValue = pendingRows.reduce(
    (sum, row) => sum + Number(row.requested_amount ?? 0),
    0
  )

  const activeFilters = [status !== 'PENDING' ? status : null, overdueOnly].filter(
    Boolean
  ).length

  function clearFilters() {
    setStatus('PENDING')
    setOverdueOnly(false)
    setPage(1)
  }

  return (
    <>
      <PageHeader
        title={isManager ? 'Pending approvals' : 'Approval queue'}
        description={
          isManager
            ? 'Requests the rule engine escalated. Open one to see the full pricing and decide.'
            : 'Monitor escalated requests. Only a sales manager can record a decision.'
        }
        actions={
          <Button variant="secondary" icon={RefreshCw} onClick={approvals.reload}>
            Refresh
          </Button>
        }
      />

      <div className="mb-4 grid gap-4 sm:grid-cols-3">
        <StatCard
          label="Open tasks"
          value={
            status === 'PENDING' ? (approvals.data?.meta?.total ?? 0) : pendingRows.length
          }
          icon={ClipboardCheck}
          tone="amber"
          loading={approvals.loading}
          hint="Awaiting a decision"
        />
        <StatCard
          label="Past SLA"
          value={overdueCount}
          icon={Clock}
          tone={overdueCount > 0 ? 'rose' : 'slate'}
          loading={approvals.loading}
          hint={overdueCount > 0 ? 'Needs attention today' : 'All within target'}
        />
        <StatCard
          label="Value on hold"
          value={formatMoney(totalValue)}
          icon={TriangleAlert}
          tone="navy"
          loading={approvals.loading}
          hint="Across the open tasks on this page"
        />
      </div>

      <Card>
        <Toolbar activeCount={activeFilters} onClear={clearFilters}>
          <FilterSelect
            value={status}
            onChange={(value) => {
              setStatus(value)
              setPage(1)
            }}
            options={APPROVAL_STATUS_OPTIONS}
            placeholder="All statuses"
            label="Status"
          />
          <Checkbox
            label="Past SLA only"
            checked={overdueOnly}
            onChange={(event) => {
              setOverdueOnly(event.target.checked)
              setPage(1)
            }}
            className="ml-1"
          />
          <span className="ml-auto text-[12.5px] text-slate-500">
            {approvals.loading
              ? 'Loading…'
              : `${approvals.data?.meta?.total ?? 0} task(s)`}
          </span>
        </Toolbar>

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
                  <p className="mt-0.5 text-[12px] text-slate-500">
                    raised {formatRelative(row.created_at)}
                  </p>
                </div>
              ),
            },
            {
              key: 'customer_name',
              header: 'Customer',
              render: (row) => (
                <span className="block max-w-48 truncate text-[13px] text-slate-800">
                  {row.customer_name}
                </span>
              ),
            },
            {
              key: 'exceptions',
              header: 'Why it escalated',
              render: (row) => (
                <div className="flex max-w-64 flex-wrap gap-1">
                  {(row.exceptions ?? []).map((exception, index) => (
                    <Badge
                      key={index}
                      tone={exceptionInfo(exception.type).tone}
                      size="sm"
                    >
                      {exceptionInfo(exception.type).label}
                    </Badge>
                  ))}
                </div>
              ),
            },
            {
              key: 'requested_discount_percent',
              header: 'Discount',
              align: 'right',
              render: (row) => (
                <span className="tnum text-[13px] font-medium text-amber-700">
                  {formatPercent(row.requested_discount_percent)}
                </span>
              ),
            },
            {
              key: 'requested_amount',
              header: 'Amount',
              align: 'right',
              render: (row) => (
                <span className="tnum font-medium text-slate-800">
                  {formatMoney(row.requested_amount)}
                </span>
              ),
            },
            {
              key: 'sla_due_at',
              header: 'SLA',
              render: (row) => {
                if (row.status !== 'PENDING') {
                  return (
                    <span className="text-[12.5px] text-slate-400">
                      decided {formatRelative(row.decided_at)}
                    </span>
                  )
                }
                const overdue = row.sla_due_at && new Date(row.sla_due_at) < new Date()
                return (
                  <span
                    className={`text-[12.5px] ${
                      overdue ? 'font-medium text-rose-600' : 'text-slate-500'
                    }`}
                  >
                    {overdue ? 'Overdue' : `due ${formatRelative(row.sla_due_at)}`}
                  </span>
                )
              },
            },
            {
              key: 'status',
              header: 'Status',
              render: (row) => (
                <StatusBadge info={approvalStatusInfo(row.status)} size="sm" />
              ),
            },
            {
              key: 'actions',
              header: '',
              align: 'right',
              render: (row) => (
                <Button
                  variant={row.status === 'PENDING' && isManager ? 'primary' : 'secondary'}
                  size="sm"
                  onClick={(event) => {
                    event.stopPropagation()
                    navigate(`/approvals/${row.id}`)
                  }}
                >
                  {row.status === 'PENDING' && isManager ? 'Review' : 'Open'}
                </Button>
              ),
            },
          ]}
          rows={rows}
          loading={approvals.loading}
          error={approvals.error}
          onRowClick={(row) => navigate(`/approvals/${row.id}`)}
          empty={
            activeFilters > 0 ? (
              <NoResultsState onClear={clearFilters} />
            ) : (
              <EmptyState
                icon={ClipboardCheck}
                title="The queue is clear"
                description="Every escalated request has been decided. New ones appear here automatically."
              />
            )
          }
        />

        <Pagination meta={approvals.data?.meta} onPageChange={setPage} />
      </Card>
    </>
  )
}
