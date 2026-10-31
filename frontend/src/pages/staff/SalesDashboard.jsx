import { useNavigate } from 'react-router-dom'
import {
  ArrowRight,
  Boxes,
  Building2,
  ClipboardCheck,
  ClipboardList,
  FileText,
  PackageX,
  RefreshCw,
  TriangleAlert,
} from 'lucide-react'

import { useAsync } from '../../hooks/useAsync'
import * as analyticsApi from '../../api/analytics'
import * as requestsApi from '../../api/requests'
import * as approvalsApi from '../../api/approvals'
import * as productsApi from '../../api/products'
import { PageHeader } from '../../components/layout/PageHeader'
import { Button } from '../../components/ui/Button'
import { Card, CardBody, CardHeader, StatCard } from '../../components/ui/Card'
import { Badge, StatusBadge } from '../../components/ui/Badge'
import { EmptyState, Table } from '../../components/ui/Table'
import { formatMoney, formatPercent, formatRelative } from '../../lib/format'
import { REQUEST_STATUS, approvalStatusInfo, requestStatusInfo } from '../../lib/status'

export function SalesDashboard() {
  const navigate = useNavigate()

  const overview = useAsync(() => analyticsApi.getOverview(30), [])
  const queue = useAsync(
    () => requestsApi.listRequests({ page_size: 8, status: REQUEST_STATUS.PENDING_APPROVAL }),
    []
  )
  const failed = useAsync(
    () =>
      requestsApi.listRequests({
        page_size: 6,
        status: REQUEST_STATUS.VALIDATION_FAILED,
      }),
    []
  )
  const approvals = useAsync(() => approvalsApi.listApprovals({ page_size: 5, status: 'PENDING' }), [])
  const lowStock = useAsync(
    () => productsApi.listProducts({ page_size: 100, status: 'ACTIVE' }),
    []
  )

  const stats = overview.data
  const lowStockItems = (lowStock.data?.items ?? []).filter(
    (product) =>
      product.reorder_level > 0 && product.available_quantity <= product.reorder_level
  )

  function reloadAll() {
    overview.reload()
    queue.reload()
    failed.reload()
    approvals.reload()
    lowStock.reload()
  }

  return (
    <>
      <PageHeader
        title="Sales operations"
        description="Processing queue, exceptions and master data across the last 30 days."
        actions={
          <>
            <Button variant="secondary" icon={RefreshCw} onClick={reloadAll}>
              Refresh
            </Button>
            <Button icon={ClipboardList} onClick={() => navigate('/requests')}>
              All requests
            </Button>
          </>
        }
      />

      <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
        <StatCard
          label="Requests (30 days)"
          value={stats?.total_requests ?? 0}
          icon={ClipboardList}
          tone="navy"
          loading={overview.loading}
          hint={`${stats?.open_requests ?? 0} still open`}
        />
        <StatCard
          label="Awaiting approval"
          value={stats?.pending_approvals ?? 0}
          icon={ClipboardCheck}
          tone="amber"
          loading={overview.loading}
          hint={
            stats?.overdue_approvals
              ? `${stats.overdue_approvals} past SLA`
              : 'All within SLA'
          }
        />
        <StatCard
          label="Quotations issued"
          value={stats?.quotations_issued ?? 0}
          icon={FileText}
          tone="emerald"
          loading={overview.loading}
          hint={`${formatPercent(stats?.automation_rate_percent ?? 0)} automated`}
        />
        <StatCard
          label="Quoted value"
          value={formatMoney(stats?.quoted_value ?? 0)}
          icon={Boxes}
          tone="blue"
          loading={overview.loading}
          hint={`avg ${formatMoney(stats?.average_quotation_value ?? 0)}`}
        />
      </div>

      <div className="mt-4 grid gap-4 lg:grid-cols-3">
        <Card className="lg:col-span-2">
          <CardHeader
            title="Awaiting manager approval"
            description="Requests the rule engine escalated and that are not yet decided"
            icon={ClipboardCheck}
            action={
              <Button
                variant="ghost"
                size="sm"
                iconRight={ArrowRight}
                onClick={() => navigate('/approvals')}
              >
                Approval queue
              </Button>
            }
          />
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
                    <p className="mt-0.5 truncate text-[12px] text-slate-500">
                      {row.customer_name}
                    </p>
                  </div>
                ),
              },
              {
                key: 'exceptions',
                header: 'Why escalated',
                render: (row) => (
                  <div className="flex flex-wrap gap-1">
                    {(row.exceptions ?? []).slice(0, 2).map((exception, index) => (
                      <Badge key={index} tone="warning" size="sm">
                        {exception.type === 'DISCOUNT_LIMIT_EXCEEDED'
                          ? 'Discount'
                          : exception.type === 'ORDER_VALUE_THRESHOLD'
                            ? 'Order value'
                            : exception.type === 'CREDIT_LIMIT_EXCEEDED'
                              ? 'Credit'
                              : 'Stock'}
                      </Badge>
                    ))}
                    {(row.exceptions?.length ?? 0) > 2 ? (
                      <Badge tone="neutral" size="sm">
                        +{row.exceptions.length - 2}
                      </Badge>
                    ) : null}
                  </div>
                ),
              },
              {
                key: 'age',
                header: 'Submitted',
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
            ]}
            rows={queue.data?.items ?? []}
            loading={queue.loading}
            error={queue.error}
            onRowClick={(row) => navigate(`/requests/${row.id}`)}
            empty={
              <EmptyState
                icon={ClipboardCheck}
                title="Nothing waiting"
                description="Every escalated request has been decided."
              />
            }
          />
        </Card>

        <div className="space-y-4">
          <Card>
            <CardHeader
              title="Needs intervention"
              description="Requests that failed validation"
              icon={TriangleAlert}
              action={
                <Button
                  variant="ghost"
                  size="sm"
                  iconRight={ArrowRight}
                  onClick={() => navigate('/exceptions')}
                >
                  Manage
                </Button>
              }
            />
            <CardBody padded={false}>
              {failed.loading ? (
                <div className="space-y-2 px-4 py-4">
                  {[0, 1].map((index) => (
                    <div key={index} className="h-9 animate-pulse rounded bg-slate-100" />
                  ))}
                </div>
              ) : (failed.data?.items ?? []).length === 0 ? (
                <EmptyState
                  icon={TriangleAlert}
                  title="No failures"
                  description="No requests are currently blocked on validation."
                />
              ) : (
                <ul className="divide-y divide-slate-100">
                  {failed.data.items.map((request) => (
                    <li
                      key={request.id}
                      role="button"
                      tabIndex={0}
                      onClick={() => navigate(`/requests/${request.id}`)}
                      onKeyDown={(event) => {
                        if (event.key === 'Enter') navigate(`/requests/${request.id}`)
                      }}
                      className="cursor-pointer px-4 py-2.5 transition hover:bg-rose-50/40 sm:px-5"
                    >
                      <div className="flex items-center justify-between gap-2">
                        <p className="font-mono text-[12.5px] font-medium text-slate-800">
                          {request.request_number}
                        </p>
                        <StatusBadge
                          info={requestStatusInfo(request.status, request)}
                          size="sm"
                          showIcon={false}
                        />
                      </div>
                      <p className="mt-0.5 line-clamp-2 text-[12px] leading-snug text-slate-500">
                        {request.validation_errors?.[0] ?? 'Validation failed.'}
                      </p>
                    </li>
                  ))}
                </ul>
              )}
            </CardBody>
          </Card>

          <Card>
            <CardHeader
              title="Low stock"
              description="At or below reorder level"
              icon={PackageX}
              action={
                <Button
                  variant="ghost"
                  size="sm"
                  iconRight={ArrowRight}
                  onClick={() => navigate('/products')}
                >
                  Products
                </Button>
              }
            />
            <CardBody padded={false}>
              {lowStock.loading ? (
                <div className="space-y-2 px-4 py-4">
                  {[0, 1].map((index) => (
                    <div key={index} className="h-8 animate-pulse rounded bg-slate-100" />
                  ))}
                </div>
              ) : lowStockItems.length === 0 ? (
                <EmptyState
                  icon={Boxes}
                  title="Stock levels healthy"
                  description="No active product is at its reorder level."
                />
              ) : (
                <ul className="divide-y divide-slate-100">
                  {lowStockItems.slice(0, 5).map((product) => (
                    <li
                      key={product.id}
                      className="flex items-center justify-between gap-3 px-4 py-2.5 sm:px-5"
                    >
                      <div className="min-w-0">
                        <p className="truncate text-[12.5px] font-medium text-slate-800">
                          {product.name}
                        </p>
                        <p className="font-mono text-[11px] text-slate-500">
                          {product.sku}
                        </p>
                      </div>
                      <div className="shrink-0 text-right">
                        <p className="tnum text-[12.5px] font-semibold text-amber-700">
                          {product.available_quantity}
                        </p>
                        <p className="text-[11px] text-slate-400">
                          reorder at {product.reorder_level}
                        </p>
                      </div>
                    </li>
                  ))}
                </ul>
              )}
            </CardBody>
          </Card>

          <Card>
            <CardHeader title="Quick actions" />
            <CardBody className="space-y-2">
              <Button
                variant="secondary"
                icon={Building2}
                className="w-full justify-start"
                onClick={() => navigate('/customers')}
              >
                Manage customers
              </Button>
              <Button
                variant="secondary"
                icon={Boxes}
                className="w-full justify-start"
                onClick={() => navigate('/products')}
              >
                Manage products
              </Button>
              <Button
                variant="secondary"
                icon={ClipboardList}
                className="w-full justify-start"
                onClick={() => navigate('/requests/new/for-customer')}
              >
                Raise a request for a customer
              </Button>
            </CardBody>
          </Card>
        </div>
      </div>

      {approvals.data?.items?.length ? (
        <Card className="mt-4">
          <CardHeader
            title="Recent approval decisions"
            description="The latest manager decisions on escalated requests"
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
                header: 'Decision',
                render: (row) => (
                  <StatusBadge info={approvalStatusInfo(row.status)} size="sm" />
                ),
              },
              {
                key: 'requested_amount',
                header: 'Amount',
                align: 'right',
                render: (row) => (
                  <span className="tnum">{formatMoney(row.requested_amount)}</span>
                ),
              },
              {
                key: 'created_at',
                header: 'Raised',
                render: (row) => (
                  <span className="text-[12.5px] text-slate-500">
                    {formatRelative(row.created_at)}
                  </span>
                ),
              },
            ]}
            rows={approvals.data.items}
            loading={approvals.loading}
            error={approvals.error}
            onRowClick={(row) => navigate(`/approvals/${row.id}`)}
            empty={<EmptyState title="No approvals yet" />}
          />
        </Card>
      ) : null}
    </>
  )
}
