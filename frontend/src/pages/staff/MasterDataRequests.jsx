import { useState } from 'react'
import {
  Building2,
  Check,
  Package,
  RefreshCw,
  ShieldQuestion,
  Undo2,
  X,
} from 'lucide-react'

import { useAuth } from '../../context/AuthContext'
import { useToast } from '../../context/ToastContext'
import { useAsync } from '../../hooks/useAsync'
import * as masterDataApi from '../../api/masterData'
import { PageHeader } from '../../components/layout/PageHeader'
import { Button } from '../../components/ui/Button'
import { Card, DetailList, DetailRow, StatCard } from '../../components/ui/Card'
import { Badge, StatusBadge } from '../../components/ui/Badge'
import { Textarea } from '../../components/ui/Field'
import { Modal } from '../../components/ui/Modal'
import {
  EmptyState,
  NoResultsState,
  Pagination,
  Table,
} from '../../components/ui/Table'
import { FilterSelect, Toolbar } from '../../components/ui/Toolbar'
import { formatDateTime, formatMoney, formatRelative, humanise } from '../../lib/format'
import {
  MASTER_DATA_ENTITY_OPTIONS,
  MASTER_DATA_STATUS_OPTIONS,
  masterDataEntityLabel,
  masterDataStatusInfo,
  tierInfo,
} from '../../lib/status'

/** Fields shown first, in this order; anything else follows alphabetically. */
const FIELD_ORDER = [
  'company_name',
  'contact_name',
  'email',
  'phone',
  'tier',
  'credit_limit',
  'tax_id',
  'sku',
  'name',
  'category',
  'unit',
  'unit_price',
  'cost_price',
  'tax_rate',
  'stock_quantity',
  'reserved_quantity',
  'reorder_level',
  'lead_time_days',
  'max_discount_percent',
  'status',
  'description',
  'notes',
]

const MONEY_FIELDS = new Set(['credit_limit', 'unit_price', 'cost_price'])
const PERCENT_FIELDS = new Set(['tax_rate', 'max_discount_percent'])

const FIELD_LABELS = {
  company_name: 'Company name',
  contact_name: 'Contact name',
  tax_id: 'Tax ID / GSTIN',
  sku: 'SKU',
  name: 'Product name',
  unit_price: 'Unit price',
  cost_price: 'Cost price',
  tax_rate: 'Tax rate',
  stock_quantity: 'In stock',
  reserved_quantity: 'Reserved',
  reorder_level: 'Reorder level',
  lead_time_days: 'Lead time',
  max_discount_percent: 'Max discount',
  billing_address: 'Billing address',
}

function fieldLabel(key) {
  return FIELD_LABELS[key] ?? humanise(key)
}

function formatValue(key, value) {
  if (value === null || value === undefined || value === '') return '—'
  if (key === 'tier') return tierInfo(value).label
  if (key === 'lead_time_days') return `${value} day(s)`
  if (MONEY_FIELDS.has(key)) return formatMoney(value)
  if (PERCENT_FIELDS.has(key)) return `${value}%`
  if (key === 'billing_address' && typeof value === 'object') {
    return [value.line1, value.city, value.state, value.postal_code]
      .filter(Boolean)
      .join(', ')
  }
  if (typeof value === 'object') return JSON.stringify(value)
  return String(value)
}

/**
 * The proposed record, field by field.
 *
 * The payload is whatever the create endpoint accepts, so it is rendered
 * generically rather than against a fixed list - a field added to the customer
 * or product schema shows up here without this page changing.
 */
function ProposedRecord({ payload }) {
  const keys = Object.keys(payload ?? {}).filter(
    (key) => payload[key] !== null && payload[key] !== undefined && payload[key] !== ''
  )
  const ordered = [
    ...FIELD_ORDER.filter((key) => keys.includes(key)),
    ...keys.filter((key) => !FIELD_ORDER.includes(key)).sort(),
  ]

  return (
    <DetailList>
      {ordered.map((key) => (
        <DetailRow
          key={key}
          label={fieldLabel(key)}
          value={formatValue(key, payload[key])}
          mono={key === 'sku' || key === 'email'}
        />
      ))}
    </DetailList>
  )
}

export function MasterDataRequests() {
  const { isManager } = useAuth()
  const toast = useToast()

  const [status, setStatus] = useState('PENDING')
  const [entityType, setEntityType] = useState(undefined)
  const [page, setPage] = useState(1)

  const [reviewing, setReviewing] = useState(null)
  const [comments, setComments] = useState('')
  const [commentError, setCommentError] = useState(null)
  const [busy, setBusy] = useState(null) // null | 'approve' | 'refuse' | 'withdraw'

  const requests = useAsync(
    () =>
      masterDataApi.listRequests({
        page,
        page_size: 20,
        status,
        entity_type: entityType,
      }),
    [page, status, entityType]
  )

  const rows = requests.data?.items ?? []
  const pendingOnPage = rows.filter((row) => row.status === 'PENDING')
  const activeFilters = [status !== 'PENDING' ? status : null, entityType].filter(
    Boolean
  ).length

  function clearFilters() {
    setStatus('PENDING')
    setEntityType(undefined)
    setPage(1)
  }

  function openReview(row) {
    setReviewing(row)
    setComments('')
    setCommentError(null)
  }

  async function decide(approve) {
    // The backend refuses a blank reason on a refusal; say so here rather than
    // making the round trip to be told.
    if (!approve && !comments.trim()) {
      setCommentError('Give a reason, so the employee knows what to change.')
      return
    }
    setBusy(approve ? 'approve' : 'refuse')
    try {
      const result = await masterDataApi.decide(reviewing.id, { approve, comments })
      const created = result.customer ?? result.product
      if (approve) {
        toast.success(
          `${humanise(masterDataEntityLabel(reviewing.entity_type))} added`,
          created?.code ?? created?.sku ?? reviewing.label
        )
      } else {
        toast.success('Request refused', `${reviewing.requested_by_name} has been told.`)
      }
      setReviewing(null)
      requests.reload()
    } catch (error) {
      toast.fromError(error, 'Could not record the decision')
    } finally {
      setBusy(null)
    }
  }

  async function withdraw(row) {
    setBusy('withdraw')
    try {
      await masterDataApi.withdraw(row.id)
      toast.success('Request withdrawn', row.label)
      setReviewing(null)
      requests.reload()
    } catch (error) {
      toast.fromError(error, 'Could not withdraw the request')
    } finally {
      setBusy(null)
    }
  }

  return (
    <>
      <PageHeader
        title={isManager ? 'Master data requests' : 'My add requests'}
        description={
          isManager
            ? 'Customers and products sales employees have asked to add. Approving creates the record.'
            : 'Customers and products you have asked a manager to approve. Nothing is created until they do.'
        }
        actions={
          <Button variant="secondary" icon={RefreshCw} onClick={requests.reload}>
            Refresh
          </Button>
        }
      />

      <div className="mb-4 grid gap-4 sm:grid-cols-3">
        <StatCard
          label="Awaiting approval"
          value={
            status === 'PENDING'
              ? (requests.data?.meta?.total ?? 0)
              : pendingOnPage.length
          }
          icon={ShieldQuestion}
          tone="amber"
          loading={requests.loading}
          hint={isManager ? 'Yours to decide' : 'With a manager'}
        />
        <StatCard
          label="Customers proposed"
          value={rows.filter((row) => row.entity_type === 'CUSTOMER').length}
          icon={Building2}
          tone="navy"
          loading={requests.loading}
          hint="On this page"
        />
        <StatCard
          label="Products proposed"
          value={rows.filter((row) => row.entity_type === 'PRODUCT').length}
          icon={Package}
          tone="slate"
          loading={requests.loading}
          hint="On this page"
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
            options={MASTER_DATA_STATUS_OPTIONS}
            placeholder="All statuses"
            label="Status"
          />
          <FilterSelect
            value={entityType}
            onChange={(value) => {
              setEntityType(value)
              setPage(1)
            }}
            options={MASTER_DATA_ENTITY_OPTIONS}
            placeholder="Customers and products"
            label="Type"
          />
          <span className="ml-auto text-[12.5px] text-slate-500">
            {requests.loading
              ? 'Loading…'
              : `${requests.data?.meta?.total ?? 0} request(s)`}
          </span>
        </Toolbar>

        <Table
          columns={[
            {
              key: 'record',
              header: 'Proposed record',
              render: (row) => (
                <div className="max-w-72">
                  <p className="truncate text-[13px] font-medium text-slate-800">
                    {row.label}
                  </p>
                  <p className="font-mono text-[11.5px] text-slate-500">
                    {row.reference}
                  </p>
                </div>
              ),
            },
            {
              key: 'entity_type',
              header: 'Type',
              render: (row) => (
                <Badge tone={row.entity_type === 'CUSTOMER' ? 'info' : 'neutral'} size="sm">
                  {row.entity_type === 'CUSTOMER' ? 'Customer' : 'Product'}
                </Badge>
              ),
            },
            {
              key: 'requested_by',
              header: 'Requested by',
              render: (row) => (
                <div className="max-w-48">
                  <p className="truncate text-[12.5px] text-slate-700">
                    {row.requested_by_name}
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
                <StatusBadge info={masterDataStatusInfo(row.status)} size="sm" />
              ),
            },
            {
              key: 'outcome',
              header: 'Outcome',
              render: (row) =>
                row.status === 'PENDING' ? (
                  <span className="text-[12px] text-slate-400">not decided</span>
                ) : (
                  <div className="max-w-56">
                    <p className="truncate text-[12.5px] text-slate-700">
                      {row.created_entity_label ?? row.decision_comments ?? '—'}
                    </p>
                    {row.decided_by_name ? (
                      <p className="truncate text-[11.5px] text-slate-500">
                        by {row.decided_by_name}
                      </p>
                    ) : null}
                  </div>
                ),
            },
            {
              key: 'actions',
              header: '',
              align: 'right',
              render: (row) => (
                <Button
                  variant={
                    row.status === 'PENDING' && isManager ? 'primary' : 'secondary'
                  }
                  size="sm"
                  onClick={(event) => {
                    event.stopPropagation()
                    openReview(row)
                  }}
                >
                  {row.status === 'PENDING' && isManager ? 'Review' : 'Open'}
                </Button>
              ),
            },
          ]}
          rows={rows}
          loading={requests.loading}
          error={requests.error}
          onRowClick={openReview}
          empty={
            activeFilters > 0 ? (
              <NoResultsState onClear={clearFilters} />
            ) : (
              <EmptyState
                icon={ShieldQuestion}
                title={isManager ? 'Nothing waiting' : 'No requests yet'}
                description={
                  isManager
                    ? 'When a sales employee asks to add a customer or product, it appears here.'
                    : 'Use “Add customer” or “Add product” and your request will appear here.'
                }
              />
            )
          }
        />

        <Pagination meta={requests.data?.meta} onPageChange={setPage} />
      </Card>

      <p className="mt-3 flex items-start gap-1.5 text-[12px] text-slate-500">
        <ShieldQuestion size={13} className="mt-0.5 shrink-0" aria-hidden="true" />
        {isManager
          ? 'Approving creates the record under your authority: the audit trail names both the employee who asked and you.'
          : 'A sales manager must approve a new customer or product before it exists in the system.'}
      </p>

      <Modal
        open={Boolean(reviewing)}
        onClose={busy ? undefined : () => setReviewing(null)}
        title={reviewing ? reviewing.label : ''}
        description={
          reviewing
            ? `Proposed ${masterDataEntityLabel(reviewing.entity_type)} · ${reviewing.reference}`
            : ''
        }
        size="lg"
        footer={
          reviewing?.status === 'PENDING' && isManager ? (
            <>
              <Button
                variant="secondary"
                icon={X}
                onClick={() => decide(false)}
                loading={busy === 'refuse'}
                disabled={busy === 'approve'}
              >
                Refuse
              </Button>
              <Button
                icon={Check}
                onClick={() => decide(true)}
                loading={busy === 'approve'}
                disabled={busy === 'refuse'}
              >
                Approve and create
              </Button>
            </>
          ) : reviewing?.status === 'PENDING' ? (
            <>
              <Button variant="secondary" onClick={() => setReviewing(null)}>
                Close
              </Button>
              <Button
                variant="danger"
                icon={Undo2}
                onClick={() => withdraw(reviewing)}
                loading={busy === 'withdraw'}
              >
                Withdraw
              </Button>
            </>
          ) : (
            <Button variant="secondary" onClick={() => setReviewing(null)}>
              Close
            </Button>
          )
        }
      >
        {reviewing ? (
          <div className="space-y-4">
            <div className="rounded-md border border-slate-200 bg-slate-50/60 px-3.5 py-3">
              <DetailList>
                <DetailRow label="Requested by" value={reviewing.requested_by_name} />
                <DetailRow label="Raised" value={formatDateTime(reviewing.created_at)} />
                <DetailRow
                  label="Status"
                  value={masterDataStatusInfo(reviewing.status).label}
                />
                {reviewing.reason ? (
                  <DetailRow label="Reason given" value={reviewing.reason} />
                ) : null}
              </DetailList>
            </div>

            <div>
              <h3 className="mb-1.5 text-[12.5px] font-medium uppercase tracking-wide text-slate-500">
                The record as submitted
              </h3>
              <ProposedRecord payload={reviewing.payload} />
            </div>

            {reviewing.status === 'PENDING' && isManager ? (
              <Textarea
                label="Comments"
                value={comments}
                error={commentError}
                rows={2}
                maxLength={1000}
                placeholder="Required when refusing; optional when approving."
                onChange={(event) => {
                  setComments(event.target.value)
                  setCommentError(null)
                }}
                hint="Sent to the employee who raised the request."
              />
            ) : null}

            {reviewing.status !== 'PENDING' ? (
              <div className="rounded-md border border-slate-200 px-3.5 py-3">
                <DetailList>
                  <DetailRow label="Decided by" value={reviewing.decided_by_name} />
                  <DetailRow
                    label="Decided"
                    value={
                      reviewing.decided_at
                        ? formatDateTime(reviewing.decided_at)
                        : '—'
                    }
                  />
                  <DetailRow label="Comments" value={reviewing.decision_comments} />
                  {reviewing.created_entity_label ? (
                    <DetailRow
                      label="Created as"
                      value={reviewing.created_entity_label}
                    />
                  ) : null}
                </DetailList>
              </div>
            ) : null}
          </div>
        ) : null}
      </Modal>
    </>
  )
}
