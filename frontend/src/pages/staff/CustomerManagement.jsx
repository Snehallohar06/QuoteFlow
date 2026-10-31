import { useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import {
  Building2,
  PencilLine,
  Plus,
  RefreshCw,
  ShieldBan,
  ShieldQuestion,
} from 'lucide-react'

import { useAuth } from '../../context/AuthContext'
import { useToast } from '../../context/ToastContext'
import { useAsync } from '../../hooks/useAsync'
import { useDebounce } from '../../hooks/useDebounce'
import * as customersApi from '../../api/customers'
import * as masterDataApi from '../../api/masterData'
import { PageHeader } from '../../components/layout/PageHeader'
import { Button } from '../../components/ui/Button'
import { Card } from '../../components/ui/Card'
import { Badge } from '../../components/ui/Badge'
import { Input, Select, Textarea } from '../../components/ui/Field'
import { Modal } from '../../components/ui/Modal'
import {
  EmptyState,
  NoResultsState,
  Pagination,
  Table,
} from '../../components/ui/Table'
import { FilterSelect, SearchInput, Toolbar } from '../../components/ui/Toolbar'
import { formatMoney } from '../../lib/format'
import {
  CUSTOMER_STATUS_OPTIONS,
  CUSTOMER_TIERS,
  customerStatusInfo,
  tierInfo,
} from '../../lib/status'

const TIER_OPTIONS = CUSTOMER_TIERS.map((tier) => ({
  value: tier,
  label: tierInfo(tier).label,
}))

const BLANK = {
  company_name: '',
  contact_name: '',
  email: '',
  phone: '',
  tier: 'STANDARD',
  credit_limit: '0',
  tax_id: '',
  notes: '',
  line1: '',
  city: '',
  state: '',
  postal_code: '',
}

export function CustomerManagement() {
  const { isManager } = useAuth()
  const toast = useToast()
  const navigate = useNavigate()

  const [search, setSearch] = useState('')
  const [status, setStatus] = useState(undefined)
  const [tier, setTier] = useState(undefined)
  const [page, setPage] = useState(1)

  const [editing, setEditing] = useState(null) // null | 'new' | customer
  const [form, setForm] = useState(BLANK)
  // Only a manager may create a customer outright. An employee's "add" submits
  // the same payload to the master-data queue, where a manager approves it.
  const [reason, setReason] = useState('')
  const [errors, setErrors] = useState({})
  const [saving, setSaving] = useState(false)
  const [statusBusy, setStatusBusy] = useState(null)

  const debouncedSearch = useDebounce(search)

  const customers = useAsync(
    () =>
      customersApi.listCustomers({
        page,
        page_size: 20,
        search: debouncedSearch || undefined,
        status,
        tier,
      }),
    [page, debouncedSearch, status, tier]
  )

  const activeFilters = [debouncedSearch, status, tier].filter(Boolean).length

  function clearFilters() {
    setSearch('')
    setStatus(undefined)
    setTier(undefined)
    setPage(1)
  }

  function set(field, value) {
    setForm((current) => ({ ...current, [field]: value }))
  }

  const needsApproval = editing === 'new' && !isManager

  function openNew() {
    setForm(BLANK)
    setReason('')
    setErrors({})
    setEditing('new')
  }

  function openEdit(customer) {
    setForm({
      company_name: customer.company_name,
      contact_name: customer.contact_name,
      email: customer.email,
      phone: customer.phone,
      tier: customer.tier,
      credit_limit: String(customer.credit_limit),
      tax_id: customer.tax_id ?? '',
      notes: customer.notes ?? '',
      line1: customer.billing_address?.line1 ?? '',
      city: customer.billing_address?.city ?? '',
      state: customer.billing_address?.state ?? '',
      postal_code: customer.billing_address?.postal_code ?? '',
    })
    setErrors({})
    setEditing(customer)
  }

  function validate() {
    const next = {}
    if (!form.company_name.trim()) next.company_name = 'Enter the company name.'
    if (!form.contact_name.trim()) next.contact_name = 'Enter a contact name.'
    if (!form.email.trim()) next.email = 'Enter an email address.'
    else if (!/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(form.email.trim()))
      next.email = 'Enter a valid email address.'
    if (!form.phone.trim()) next.phone = 'Enter a contact number.'
    else if (form.phone.trim().length < 6) next.phone = 'That number looks too short.'
    if (form.credit_limit !== '' && Number(form.credit_limit) < 0)
      next.credit_limit = 'A credit limit cannot be negative.'
    setErrors(next)
    return Object.keys(next).length === 0
  }

  async function save() {
    if (!validate()) return
    setSaving(true)
    try {
      const address =
        form.line1 || form.city
          ? {
              line1: form.line1,
              city: form.city,
              state: form.state,
              postal_code: form.postal_code,
              country: 'India',
            }
          : undefined

      const payload = {
        company_name: form.company_name.trim(),
        contact_name: form.contact_name.trim(),
        email: form.email.trim().toLowerCase(),
        phone: form.phone.trim(),
        tier: form.tier,
        credit_limit: form.credit_limit === '' ? 0 : Number(form.credit_limit),
        tax_id: form.tax_id.trim() || undefined,
        notes: form.notes.trim() || undefined,
        billing_address: address,
      }

      if (needsApproval) {
        const raised = await masterDataApi.submitCustomer(payload, reason)
        toast.success(
          'Sent to a manager',
          `${raised.reference} — ${raised.label} will be added once approved.`
        )
      } else if (editing === 'new') {
        const created = await customersApi.createCustomer(payload)
        toast.success('Customer created', `${created.code} — ${created.company_name}`)
      } else {
        await customersApi.updateCustomer(editing.id, payload)
        toast.success('Customer updated', editing.code)
      }
      setEditing(null)
      customers.reload()
    } catch (error) {
      const fieldErrors = error.fieldErrors ?? {}
      if (Object.keys(fieldErrors).length > 0) setErrors(fieldErrors)
      toast.fromError(error, 'Could not save the customer')
    } finally {
      setSaving(false)
    }
  }

  async function changeStatus(customer, newStatus) {
    setStatusBusy(customer.id)
    try {
      await customersApi.setCustomerStatus(customer.id, newStatus)
      toast.success(
        'Status updated',
        `${customer.code} is now ${customerStatusInfo(newStatus).label.toLowerCase()}.`
      )
      customers.reload()
    } catch (error) {
      toast.fromError(error, 'Could not change the status')
    } finally {
      setStatusBusy(null)
    }
  }

  return (
    <>
      <PageHeader
        title="Customer management"
        description="Tiers drive discount entitlements; credit limits drive the credit-exposure rule."
        actions={
          <>
            <Button variant="secondary" icon={RefreshCw} onClick={customers.reload}>
              Refresh
            </Button>
            <Button icon={Plus} onClick={openNew}>
              Add customer
            </Button>
          </>
        }
      />

      {isManager ? null : (
        <p className="mb-4 flex items-start gap-1.5 rounded-md border border-amber-200 bg-amber-50 px-3 py-2 text-[12.5px] text-amber-900">
          <ShieldQuestion size={14} className="mt-0.5 shrink-0" aria-hidden="true" />
          <span>
            A sales manager approves new customers. What you add here is sent to
            them and created once they approve it —{' '}
            <Link to="/master-data-requests" className="font-medium underline">
              see your requests
            </Link>
            .
          </span>
        </p>
      )}

      <Card>
        <Toolbar activeCount={activeFilters} onClear={clearFilters}>
          <SearchInput
            value={search}
            onChange={(value) => {
              setSearch(value)
              setPage(1)
            }}
            placeholder="Search by company, contact, code or email"
            className="w-full sm:w-80"
          />
          <FilterSelect
            value={status}
            onChange={(value) => {
              setStatus(value)
              setPage(1)
            }}
            options={CUSTOMER_STATUS_OPTIONS}
            placeholder="All statuses"
            label="Status"
          />
          <FilterSelect
            value={tier}
            onChange={(value) => {
              setTier(value)
              setPage(1)
            }}
            options={TIER_OPTIONS}
            placeholder="All tiers"
            label="Tier"
          />
          <span className="ml-auto text-[12.5px] text-slate-500">
            {customers.loading
              ? 'Loading…'
              : `${customers.data?.meta?.total ?? 0} customer(s)`}
          </span>
        </Toolbar>

        <Table
          columns={[
            {
              key: 'company',
              header: 'Customer',
              render: (row) => (
                <div className="max-w-64">
                  <p className="truncate text-[13px] font-medium text-slate-800">
                    {row.company_name}
                  </p>
                  <p className="font-mono text-[11.5px] text-slate-500">{row.code}</p>
                </div>
              ),
            },
            {
              key: 'contact',
              header: 'Contact',
              render: (row) => (
                <div className="max-w-56">
                  <p className="truncate text-[12.5px] text-slate-700">
                    {row.contact_name}
                  </p>
                  <p className="truncate text-[11.5px] text-slate-500">{row.email}</p>
                </div>
              ),
            },
            {
              key: 'tier',
              header: 'Tier',
              render: (row) => (
                <Badge tone={tierInfo(row.tier).tone} size="sm">
                  {tierInfo(row.tier).label}
                </Badge>
              ),
            },
            {
              key: 'credit',
              header: 'Credit',
              align: 'right',
              render: (row) =>
                row.credit_limit > 0 ? (
                  <div>
                    <p className="tnum text-[12.5px] font-medium text-slate-800">
                      {formatMoney(row.available_credit)}
                    </p>
                    <p className="tnum text-[11px] text-slate-500">
                      of {formatMoney(row.credit_limit)}
                    </p>
                  </div>
                ) : (
                  <span className="text-[12px] text-slate-400">no limit</span>
                ),
            },
            {
              key: 'status',
              header: 'Status',
              render: (row) => (
                <Badge tone={customerStatusInfo(row.status).tone} size="sm">
                  {customerStatusInfo(row.status).label}
                </Badge>
              ),
            },
            {
              key: 'actions',
              header: '',
              align: 'right',
              render: (row) => (
                <div className="flex items-center justify-end gap-1">
                  <Button
                    variant="ghost"
                    size="icon-sm"
                    aria-label={`Edit ${row.code}`}
                    onClick={(event) => {
                      event.stopPropagation()
                      openEdit(row)
                    }}
                  >
                    <PencilLine size={15} className="text-slate-500" />
                  </Button>
                  {isManager ? (
                    <select
                      value={row.status}
                      disabled={statusBusy === row.id}
                      onClick={(event) => event.stopPropagation()}
                      onChange={(event) => changeStatus(row, event.target.value)}
                      aria-label={`Status for ${row.code}`}
                      className="h-7.5 rounded border border-slate-300 bg-white px-1.5 text-[11.5px] text-slate-600 focus:outline-none focus:ring-2 focus:ring-brand-500"
                    >
                      {CUSTOMER_STATUS_OPTIONS.map((option) => (
                        <option key={option.value} value={option.value}>
                          {option.label}
                        </option>
                      ))}
                    </select>
                  ) : null}
                </div>
              ),
            },
          ]}
          rows={customers.data?.items ?? []}
          loading={customers.loading}
          error={customers.error}
          onRowClick={(row) => navigate(`/customers/${row.id}`)}
          empty={
            activeFilters > 0 ? (
              <NoResultsState onClear={clearFilters} />
            ) : (
              <EmptyState
                icon={Building2}
                title="No customers yet"
                description="Add a customer, or let them register themselves."
                action={
                  <Button icon={Plus} onClick={openNew}>
                    Add customer
                  </Button>
                }
              />
            )
          }
        />

        <Pagination meta={customers.data?.meta} onPageChange={setPage} />
      </Card>

      {isManager ? (
        <p className="mt-3 flex items-start gap-1.5 text-[12px] text-slate-500">
          <ShieldBan size={13} className="mt-0.5 shrink-0" aria-hidden="true" />
          Blocking a customer stops new requests immediately and fails any already in
          flight. Putting one on hold has the same effect until they are reactivated.
        </p>
      ) : null}

      <Modal
        open={Boolean(editing)}
        onClose={saving ? undefined : () => setEditing(null)}
        title={
          needsApproval
            ? 'Request a new customer'
            : editing === 'new'
              ? 'Add a customer'
              : `Edit ${editing?.code ?? ''}`
        }
        description={
          needsApproval
            ? 'A sales manager reviews these details and the customer is created once they approve.'
            : 'The tier sets their discount bonus; the credit limit drives the credit-exposure check.'
        }
        size="lg"
        footer={
          <>
            <Button
              variant="secondary"
              onClick={() => setEditing(null)}
              disabled={saving}
            >
              Cancel
            </Button>
            <Button loading={saving} onClick={save}>
              {needsApproval
                ? 'Send for approval'
                : editing === 'new'
                  ? 'Add customer'
                  : 'Save changes'}
            </Button>
          </>
        }
      >
        <div className="space-y-4">
          <div className="grid gap-4 sm:grid-cols-2">
            <Input
              label="Company name"
              value={form.company_name}
              error={errors.company_name}
              required
              onChange={(event) => set('company_name', event.target.value)}
            />
            <Input
              label="Contact name"
              value={form.contact_name}
              error={errors.contact_name}
              required
              onChange={(event) => set('contact_name', event.target.value)}
            />
          </div>

          <div className="grid gap-4 sm:grid-cols-2">
            <Input
              label="Email"
              type="email"
              value={form.email}
              error={errors.email}
              required
              onChange={(event) => set('email', event.target.value)}
            />
            <Input
              label="Phone"
              value={form.phone}
              error={errors.phone}
              required
              onChange={(event) => set('phone', event.target.value)}
            />
          </div>

          <div className="grid gap-4 sm:grid-cols-3">
            <Select
              label="Tier"
              value={form.tier}
              options={TIER_OPTIONS}
              onChange={(event) => set('tier', event.target.value)}
              hint="Adds a discount bonus"
            />
            <Input
              label="Credit limit"
              type="number"
              min="0"
              step="1000"
              value={form.credit_limit}
              error={errors.credit_limit}
              prefix="₹"
              hint="0 disables the check"
              onChange={(event) => set('credit_limit', event.target.value)}
            />
            <Input
              label="Tax ID / GSTIN"
              value={form.tax_id}
              error={errors.tax_id}
              onChange={(event) => set('tax_id', event.target.value)}
            />
          </div>

          <fieldset className="rounded-md border border-slate-200 px-3.5 pb-3.5 pt-2">
            <legend className="px-1 text-[12px] font-medium text-slate-500">
              Billing address — printed on their quotations
            </legend>
            <div className="space-y-3">
              <Input
                label="Address"
                value={form.line1}
                onChange={(event) => set('line1', event.target.value)}
              />
              <div className="grid gap-3 sm:grid-cols-3">
                <Input
                  label="City"
                  value={form.city}
                  onChange={(event) => set('city', event.target.value)}
                />
                <Input
                  label="State"
                  value={form.state}
                  onChange={(event) => set('state', event.target.value)}
                />
                <Input
                  label="Postal code"
                  value={form.postal_code}
                  onChange={(event) => set('postal_code', event.target.value)}
                />
              </div>
            </div>
          </fieldset>

          <Input
            label="Internal notes"
            value={form.notes}
            maxLength={1000}
            placeholder="Payment history, account manager, special terms…"
            onChange={(event) => set('notes', event.target.value)}
          />

          {needsApproval ? (
            <Textarea
              label="Why this customer is needed"
              value={reason}
              rows={2}
              maxLength={500}
              placeholder="Context for the manager deciding — how you know them, expected volume…"
              hint="Optional, but it usually saves a round trip."
              onChange={(event) => setReason(event.target.value)}
            />
          ) : null}
        </div>
      </Modal>
    </>
  )
}
