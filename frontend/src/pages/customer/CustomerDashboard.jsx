import { Link, useNavigate } from 'react-router-dom'
import {
  ArrowRight,
  ClipboardList,
  Clock,
  FileText,
  PlusCircle,
  Wallet,
} from 'lucide-react'

import { useAuth } from '../../context/AuthContext'
import { useAsync } from '../../hooks/useAsync'
import * as requestsApi from '../../api/requests'
import * as quotationsApi from '../../api/quotations'
import * as settingsApi from '../../api/settings'
import { PageHeader } from '../../components/layout/PageHeader'
import { Button } from '../../components/ui/Button'
import { Card, CardBody, CardHeader, StatCard } from '../../components/ui/Card'
import { StatusBadge } from '../../components/ui/Badge'
import { EmptyState, ErrorState, Table } from '../../components/ui/Table'
import {
  formatDate,
  formatMoney,
  formatPercent,
  formatRelative,
} from '../../lib/format'
import {
  REQUEST_STATUS,
  quotationStatusInfo,
  requestStatusInfo,
} from '../../lib/status'

export function CustomerDashboard() {
  const { user, customer } = useAuth()
  const navigate = useNavigate()

  const requests = useAsync(() => requestsApi.listRequests({ page_size: 50 }), [])
  const quotations = useAsync(() => quotationsApi.listQuotations({ page_size: 5 }), [])
  const policy = useAsync(() => settingsApi.getDiscountPolicy(), [])

  const items = requests.data?.items ?? []
  const counts = items.reduce((acc, request) => {
    acc[request.status] = (acc[request.status] ?? 0) + 1
    return acc
  }, {})

  const openCount =
    (counts[REQUEST_STATUS.SUBMITTED] ?? 0) +
    (counts[REQUEST_STATUS.UNDER_VALIDATION] ?? 0) +
    (counts[REQUEST_STATUS.PRICED] ?? 0) +
    (counts[REQUEST_STATUS.PENDING_APPROVAL] ?? 0)

  const needsAttention = items.filter((request) =>
    [REQUEST_STATUS.VALIDATION_FAILED, REQUEST_STATUS.MODIFICATION_REQUESTED].includes(
      request.status
    )
  )

  const liveQuotations = (quotations.data?.items ?? []).filter(
    (quotation) => quotation.status === 'ISSUED' || quotation.status === 'ACCEPTED'
  )

  const firstName = user?.full_name?.split(' ')[0] ?? 'there'

  return (
    <>
      <PageHeader
        title={`Welcome back, ${firstName}`}
        description={
          customer
            ? `${customer.company_name} · ${customer.code} · ${customer.tier} tier`
            : 'Your quotation activity at a glance.'
        }
        actions={
          <>
            <Button variant="secondary" icon={ClipboardList} onClick={() => navigate('/requests')}>
              My requests
            </Button>
            <Button icon={PlusCircle} onClick={() => navigate('/requests/new')}>
              New request
            </Button>
          </>
        }
      />

      <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
        <StatCard
          label="Total requests"
          value={requests.data?.meta?.total ?? 0}
          icon={ClipboardList}
          tone="navy"
          loading={requests.loading}
          hint="All time"
        />
        <StatCard
          label="In progress"
          value={openCount}
          icon={Clock}
          tone="amber"
          loading={requests.loading}
          hint={
            counts[REQUEST_STATUS.PENDING_APPROVAL]
              ? `${counts[REQUEST_STATUS.PENDING_APPROVAL]} awaiting approval`
              : 'Being processed'
          }
        />
        <StatCard
          label="Quotations received"
          value={quotations.data?.meta?.total ?? 0}
          icon={FileText}
          tone="emerald"
          loading={quotations.loading}
          hint={`${liveQuotations.length} currently valid`}
        />
        <StatCard
          label="Credit available"
          value={
            customer?.credit_limit > 0
              ? formatMoney(customer.available_credit)
              : 'Not set'
          }
          icon={Wallet}
          tone="blue"
          hint={
            customer?.credit_limit > 0
              ? `of ${formatMoney(customer.credit_limit)}`
              : 'No credit limit applied'
          }
        />
      </div>

      {needsAttention.length > 0 ? (
        <Card className="mt-4 border-amber-200 bg-amber-50/50">
          <CardBody>
            <p className="text-[13.5px] font-semibold text-amber-900">
              {needsAttention.length === 1
                ? 'One request needs your attention'
                : `${needsAttention.length} requests need your attention`}
            </p>
            <ul className="mt-2 space-y-1.5">
              {needsAttention.slice(0, 3).map((request) => (
                <li key={request.id} className="flex flex-wrap items-center gap-2">
                  <Link
                    to={`/requests/${request.id}`}
                    className="font-mono text-[12.5px] font-medium text-brand-700 underline-offset-2 hover:underline"
                  >
                    {request.request_number}
                  </Link>
                  <StatusBadge
                    info={requestStatusInfo(request.status, request)}
                    size="sm"
                  />
                  <span className="text-[12.5px] text-amber-900/80">
                    {request.validation_errors?.[0] ??
                      'The sales manager has asked for changes.'}
                  </span>
                </li>
              ))}
            </ul>
          </CardBody>
        </Card>
      ) : null}

      <div className="mt-4 grid gap-4 lg:grid-cols-3">
        <Card className="lg:col-span-2">
          <CardHeader
            title="Recent requests"
            description="Your most recent quotation requests and where they are"
            icon={ClipboardList}
            action={
              <Button
                variant="ghost"
                size="sm"
                iconRight={ArrowRight}
                onClick={() => navigate('/requests')}
              >
                View all
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
                    <p className="mt-0.5 text-[12px] text-slate-500">
                      {row.pricing?.line_count ?? row.items?.length ?? 0} line(s) ·{' '}
                      {formatRelative(row.created_at)}
                    </p>
                  </div>
                ),
              },
              {
                key: 'status',
                header: 'Status',
                render: (row) => (
                  <StatusBadge info={requestStatusInfo(row.status, row)} size="sm" />
                ),
              },
              {
                key: 'amount',
                header: 'Amount',
                align: 'right',
                render: (row) =>
                  row.pricing ? (
                    <span className="tnum font-medium text-slate-800">
                      {formatMoney(row.pricing.final_amount, {
                        currency: row.pricing.currency,
                      })}
                    </span>
                  ) : (
                    <span className="text-slate-400">—</span>
                  ),
              },
            ]}
            rows={items.slice(0, 6)}
            loading={requests.loading}
            error={requests.error}
            onRowClick={(row) => navigate(`/requests/${row.id}`)}
            empty={
              <EmptyState
                icon={ClipboardList}
                title="No requests yet"
                description="Browse the catalogue and submit your first quotation request."
                action={
                  <Button icon={PlusCircle} onClick={() => navigate('/requests/new')}>
                    Create a request
                  </Button>
                }
              />
            }
          />
        </Card>

        <div className="space-y-4">
          <Card>
            <CardHeader
              title="Latest quotations"
              icon={FileText}
              action={
                <Button
                  variant="ghost"
                  size="sm"
                  iconRight={ArrowRight}
                  onClick={() => navigate('/quotations')}
                >
                  All
                </Button>
              }
            />
            <CardBody padded={false}>
              {quotations.error ? (
                <ErrorState error={quotations.error} onRetry={quotations.reload} />
              ) : quotations.loading ? (
                <div className="space-y-2 px-4 py-4">
                  {[0, 1, 2].map((index) => (
                    <div
                      key={index}
                      className="h-10 animate-pulse rounded bg-slate-100"
                    />
                  ))}
                </div>
              ) : (quotations.data?.items ?? []).length === 0 ? (
                <EmptyState
                  icon={FileText}
                  title="No quotations yet"
                  description="An approved request produces a quotation you can download."
                />
              ) : (
                <ul className="divide-y divide-slate-100">
                  {quotations.data.items.map((quotation) => (
                    <li key={quotation.id}>
                      <Link
                        to={`/quotations/${quotation.id}`}
                        className="flex items-center gap-3 px-4 py-2.5 transition hover:bg-brand-50/50 sm:px-5"
                      >
                        <div className="min-w-0 flex-1">
                          <p className="font-mono text-[12.5px] font-medium text-slate-800">
                            {quotation.quotation_number}
                          </p>
                          <p className="mt-0.5 text-[11.5px] text-slate-500">
                            Valid until {formatDate(quotation.valid_until)}
                          </p>
                        </div>
                        <div className="shrink-0 text-right">
                          <p className="tnum text-[13px] font-semibold text-navy-800">
                            {formatMoney(quotation.pricing.final_amount, {
                              currency: quotation.pricing.currency,
                            })}
                          </p>
                          <StatusBadge
                            info={quotationStatusInfo(quotation.status)}
                            size="sm"
                            showIcon={false}
                            className="mt-0.5"
                          />
                        </div>
                      </Link>
                    </li>
                  ))}
                </ul>
              )}
            </CardBody>
          </Card>

          <Card>
            <CardHeader
              title="Your discount entitlement"
              description="Maximum discount you may request, by order quantity"
            />
            <CardBody>
              {policy.loading ? (
                <div className="space-y-2">
                  {[0, 1, 2, 3].map((index) => (
                    <div key={index} className="h-6 animate-pulse rounded bg-slate-100" />
                  ))}
                </div>
              ) : policy.error ? (
                <p className="text-[13px] text-slate-500">
                  Could not load the discount policy.
                </p>
              ) : (
                <>
                  <ul className="space-y-1.5">
                    {policy.data.tiers.map((tier) => {
                      const bonus =
                        policy.data.tier_bonus_percent?.[customer?.tier ?? 'STANDARD'] ?? 0
                      return (
                        <li
                          key={tier.min_quantity}
                          className="flex items-baseline justify-between gap-3 text-[13px]"
                        >
                          <span className="text-slate-600">
                            {tier.max_quantity
                              ? `${tier.min_quantity}–${tier.max_quantity} units`
                              : `${tier.min_quantity}+ units`}
                          </span>
                          <span className="tnum font-medium text-slate-800">
                            {formatPercent(tier.max_discount_percent + bonus)}
                          </span>
                        </li>
                      )
                    })}
                  </ul>
                  {customer?.tier && customer.tier !== 'STANDARD' ? (
                    <p className="mt-3 rounded bg-brand-50 px-2.5 py-2 text-[12px] leading-snug text-brand-800">
                      Includes your{' '}
                      <span className="font-semibold">{customer.tier}</span> tier bonus of{' '}
                      {formatPercent(
                        policy.data.tier_bonus_percent?.[customer.tier] ?? 0
                      )}
                      .
                    </p>
                  ) : null}
                  <p className="mt-2 text-[11.5px] leading-snug text-slate-500">
                    Requesting more than this sends the quotation to a sales manager for
                    approval.
                  </p>
                </>
              )}
            </CardBody>
          </Card>
        </div>
      </div>
    </>
  )
}
