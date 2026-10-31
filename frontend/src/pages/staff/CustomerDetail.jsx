import { useNavigate, useParams } from 'react-router-dom'
import {
  Building2,
  ClipboardList,
  FileText,
  Mail,
  MapPin,
  Phone,
  PlusCircle,
  Wallet,
} from 'lucide-react'

import { useAsync } from '../../hooks/useAsync'
import * as customersApi from '../../api/customers'
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
  StatCard,
} from '../../components/ui/Card'
import { Badge, StatusBadge } from '../../components/ui/Badge'
import { EmptyState, ErrorState, PageLoader, Table } from '../../components/ui/Table'
import { RankedBars } from '../../components/ui/ChartTooltip'
import { formatDate, formatDateTime, formatMoney, formatRelative } from '../../lib/format'
import {
  customerStatusInfo,
  quotationStatusInfo,
  requestStatusInfo,
  tierInfo,
} from '../../lib/status'

export function CustomerDetail() {
  const { id } = useParams()
  const navigate = useNavigate()

  const summary = useAsync(() => customersApi.getCustomerSummary(id), [id])
  const requests = useAsync(
    () => requestsApi.listRequests({ customer_id: id, page_size: 10 }),
    [id]
  )
  const quotations = useAsync(
    () => quotationsApi.listQuotations({ customer_id: id, page_size: 10 }),
    [id]
  )

  const data = summary.data
  const customer = data?.customer

  if (summary.loading && !data) return <PageLoader label="Loading customer" />
  if (summary.error) {
    return (
      <Card>
        <ErrorState error={summary.error} onRetry={summary.reload} />
      </Card>
    )
  }
  if (!customer) return null

  const statusRows = Object.entries(data.requests_by_status ?? {})
    .map(([status, count]) => ({
      key: status,
      label: requestStatusInfo(status).label,
      value: count,
    }))
    .sort((a, b) => b.value - a.value)

  const address = customer.billing_address

  return (
    <>
      <PageHeader
        title={customer.company_name}
        description={`${customer.code} · ${customer.contact_name}`}
        breadcrumbs={[
          { label: 'Customers', to: '/customers' },
          { label: customer.code },
        ]}
        meta={
          <div className="flex flex-wrap items-center gap-1.5">
            <Badge tone={tierInfo(customer.tier).tone} size="lg">
              {tierInfo(customer.tier).label} tier
            </Badge>
            <Badge tone={customerStatusInfo(customer.status).tone} size="lg">
              {customerStatusInfo(customer.status).label}
            </Badge>
          </div>
        }
        actions={
          <Button
            icon={PlusCircle}
            onClick={() =>
              navigate('/requests/new/for-customer', {
                state: { customerId: customer.id },
              })
            }
          >
            Raise a request
          </Button>
        }
      />

      <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
        <StatCard
          label="Total requests"
          value={data.total_requests}
          icon={ClipboardList}
          tone="navy"
          loading={summary.loading}
        />
        <StatCard
          label="Quotations issued"
          value={data.total_quotations}
          icon={FileText}
          tone="emerald"
          loading={summary.loading}
        />
        <StatCard
          label="Quoted value"
          value={formatMoney(data.quoted_value)}
          icon={Wallet}
          tone="blue"
          loading={summary.loading}
          hint="All time"
        />
        <StatCard
          label="Credit available"
          value={
            customer.credit_limit > 0
              ? formatMoney(customer.available_credit)
              : 'No limit'
          }
          icon={Wallet}
          tone={
            customer.credit_limit > 0 && customer.available_credit <= 0
              ? 'rose'
              : 'slate'
          }
          loading={summary.loading}
          hint={
            customer.credit_limit > 0
              ? `${formatMoney(customer.outstanding_amount)} outstanding`
              : 'Credit check disabled'
          }
        />
      </div>

      <div className="mt-4 grid gap-4 lg:grid-cols-[1fr_320px]">
        <div className="space-y-4">
          <Card>
            <CardHeader
              title="Recent requests"
              description="This customer's most recent quotation requests"
              icon={ClipboardList}
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
                      <p className="text-[11.5px] text-slate-500">
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
                  key: 'lines',
                  header: 'Lines',
                  align: 'right',
                  render: (row) => (
                    <span className="tnum">
                      {row.pricing?.line_count ?? row.items?.length ?? 0}
                    </span>
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
                      <span className="text-[12px] text-slate-400">—</span>
                    ),
                },
              ]}
              rows={requests.data?.items ?? []}
              loading={requests.loading}
              error={requests.error}
              onRowClick={(row) => navigate(`/requests/${row.id}`)}
              empty={
                <EmptyState
                  icon={ClipboardList}
                  title="No requests yet"
                  description="This customer has not submitted a quotation request."
                />
              }
            />
          </Card>

          <Card>
            <CardHeader
              title="Quotations issued"
              description="Documents this customer has received"
              icon={FileText}
            />
            <Table
              columns={[
                {
                  key: 'quotation_number',
                  header: 'Quotation',
                  render: (row) => (
                    <div>
                      <p className="font-mono text-[12.5px] font-medium text-slate-800">
                        {row.quotation_number}
                      </p>
                      <p className="text-[11.5px] text-slate-500">
                        issued {formatDate(row.issued_at)}
                      </p>
                    </div>
                  ),
                },
                {
                  key: 'status',
                  header: 'Status',
                  render: (row) => (
                    <StatusBadge info={quotationStatusInfo(row.status)} size="sm" />
                  ),
                },
                {
                  key: 'valid_until',
                  header: 'Valid until',
                  render: (row) => (
                    <span className="text-[12.5px] text-slate-600">
                      {formatDate(row.valid_until)}
                    </span>
                  ),
                },
                {
                  key: 'amount',
                  header: 'Amount',
                  align: 'right',
                  render: (row) => (
                    <span className="tnum font-medium text-slate-800">
                      {formatMoney(row.pricing.final_amount, {
                        currency: row.pricing.currency,
                      })}
                    </span>
                  ),
                },
              ]}
              rows={quotations.data?.items ?? []}
              loading={quotations.loading}
              error={quotations.error}
              onRowClick={(row) => navigate(`/quotations/${row.id}`)}
              empty={
                <EmptyState
                  icon={FileText}
                  title="No quotations yet"
                  description="Approved requests will produce quotations here."
                />
              }
            />
          </Card>
        </div>

        <div className="space-y-4">
          <Card>
            <CardHeader title="Account" icon={Building2} />
            <CardBody>
              <DetailList>
                <DetailRow label="Customer code" value={customer.code} mono />
                <DetailRow label="Company" value={customer.company_name} />
                <DetailRow label="Contact" value={customer.contact_name} />
                <DetailRow
                  label="Tier"
                  value={
                    <Badge tone={tierInfo(customer.tier).tone} size="sm">
                      {tierInfo(customer.tier).label}
                    </Badge>
                  }
                />
                <DetailRow
                  label="Credit limit"
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
                {customer.tax_id ? (
                  <DetailRow label="Tax ID" value={customer.tax_id} mono />
                ) : null}
                <DetailRow label="Registered" value={formatDate(customer.created_at)} />
                {data.last_request_at ? (
                  <DetailRow
                    label="Last request"
                    value={formatDateTime(data.last_request_at)}
                  />
                ) : null}
              </DetailList>
            </CardBody>
          </Card>

          <Card>
            <CardHeader title="Contact" />
            <CardBody className="space-y-2">
              <p className="flex items-center gap-2 text-[13px] text-slate-700">
                <Mail size={14} className="shrink-0 text-slate-400" aria-hidden="true" />
                <a
                  href={`mailto:${customer.email}`}
                  className="truncate underline-offset-2 hover:text-brand-700 hover:underline"
                >
                  {customer.email}
                </a>
              </p>
              <p className="flex items-center gap-2 text-[13px] text-slate-700">
                <Phone size={14} className="shrink-0 text-slate-400" aria-hidden="true" />
                {customer.phone}
              </p>
              {address ? (
                <p className="flex items-start gap-2 text-[13px] leading-snug text-slate-700">
                  <MapPin
                    size={14}
                    className="mt-0.5 shrink-0 text-slate-400"
                    aria-hidden="true"
                  />
                  <span>
                    {[
                      address.line1,
                      address.line2,
                      [address.city, address.postal_code].filter(Boolean).join(' '),
                      [address.state, address.country].filter(Boolean).join(', '),
                    ]
                      .filter(Boolean)
                      .map((line, index) => (
                        <span key={index} className="block">
                          {line}
                        </span>
                      ))}
                  </span>
                </p>
              ) : null}
            </CardBody>
          </Card>

          {statusRows.length > 0 ? (
            <Card>
              <CardHeader
                title="Request outcomes"
                description="Where this customer's requests ended up"
              />
              <CardBody>
                <RankedBars rows={statusRows} />
              </CardBody>
            </Card>
          ) : null}

          {customer.notes ? (
            <Card>
              <CardHeader title="Internal notes" />
              <CardBody>
                <p className="whitespace-pre-wrap text-[13px] leading-relaxed text-slate-600">
                  {customer.notes}
                </p>
              </CardBody>
            </Card>
          ) : null}
        </div>
      </div>
    </>
  )
}
