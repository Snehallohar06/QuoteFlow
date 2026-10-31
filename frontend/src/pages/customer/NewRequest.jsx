import { useCallback, useEffect, useMemo, useState } from 'react'
import { useLocation, useNavigate } from 'react-router-dom'
import {
  AlertTriangle,
  CheckCircle2,
  ClipboardList,
  Info,
  Minus,
  Package,
  Plus,
  Save,
  Send,
  Trash2,
  TriangleAlert,
} from 'lucide-react'

import { useAuth } from '../../context/AuthContext'
import { useToast } from '../../context/ToastContext'
import { useAsync } from '../../hooks/useAsync'
import { useDebounce } from '../../hooks/useDebounce'
import * as productsApi from '../../api/products'
import * as customersApi from '../../api/customers'
import * as requestsApi from '../../api/requests'
import * as settingsApi from '../../api/settings'
import { PageHeader } from '../../components/layout/PageHeader'
import { Button } from '../../components/ui/Button'
import { Card, CardBody, CardHeader } from '../../components/ui/Card'
import { Badge } from '../../components/ui/Badge'
import { Input, Select, Textarea } from '../../components/ui/Field'
import { EmptyState, PageLoader, Spinner } from '../../components/ui/Table'
import { SearchInput } from '../../components/ui/Toolbar'
import { formatMoney, formatPercent } from '../../lib/format'

/**
 * Build or edit a quotation request.
 *
 * Three entry points, all via router state:
 *   { addProduct }      the catalogue handed over a product to start with
 *   { customerId }      staff raising a request for a named customer
 *   { editRequestId }   editing a draft, or one returned for modification
 *
 * Client-side validation mirrors a rule the backend also enforces, so a form
 * that passes should submit cleanly. The backend stays the authority: its
 * verdict — including the discount ceiling it actually applied — is what the
 * user is shown afterwards.
 */

function emptyLine(product) {
  return {
    product_id: product.id,
    sku: product.sku,
    name: product.name,
    unit: product.unit ?? 'pcs',
    unit_price: product.unit_price,
    available_quantity: product.available_quantity ?? 0,
    lead_time_days: product.lead_time_days ?? 0,
    max_discount_percent: product.max_discount_percent ?? null,
    quantity: 1,
    requested_discount_percent: 0,
    notes: '',
  }
}

/**
 * The discount ceiling for a quantity, derived from the live policy.
 *
 * A preview only, so the customer can see where the limit falls before
 * submitting; the authoritative figure comes back from the workflow.
 */
function ceilingFor(policy, quantity, customerTier, productMax) {
  if (!policy) return null
  const band = policy.tiers.find(
    (tier) =>
      quantity >= tier.min_quantity &&
      (tier.max_quantity === null || quantity <= tier.max_quantity)
  )
  if (!band) return 0
  const bonus = policy.tier_bonus_percent?.[customerTier ?? 'STANDARD'] ?? 0
  let ceiling = band.max_discount_percent + bonus
  if (productMax !== null && productMax !== undefined) {
    ceiling = Math.min(ceiling, productMax)
  }
  return Math.min(ceiling, policy.absolute_max_discount_percent)
}

function LineRow({ line, index, policy, customerTier, onChange, onRemove, error }) {
  const ceiling = ceilingFor(
    policy,
    line.quantity,
    customerTier,
    line.max_discount_percent
  )
  const overCeiling = ceiling !== null && line.requested_discount_percent > ceiling
  const shortfall = Math.max(line.quantity - line.available_quantity, 0)

  const gross = line.unit_price * line.quantity
  const discount = (gross * line.requested_discount_percent) / 100

  return (
    <div className="border-b border-slate-100 px-4 py-3.5 last:border-0 sm:px-5">
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0">
          <p className="text-[13.5px] font-medium text-slate-800">{line.name}</p>
          <p className="font-mono text-[11.5px] text-slate-500">
            {line.sku} · {formatMoney(line.unit_price)} / {line.unit}
          </p>
        </div>
        <Button
          variant="ghost"
          size="icon-sm"
          onClick={() => onRemove(index)}
          aria-label={`Remove ${line.name}`}
        >
          <Trash2 size={14} className="text-slate-400" />
        </Button>
      </div>

      <div className="mt-3 grid gap-3 sm:grid-cols-[auto_1fr_1fr]">
        {/* Explicit steppers: the native spinners are hidden, and a quantity is
            adjusted far more often than it is typed. */}
        <div>
          <label
            htmlFor={`qty-${index}`}
            className="mb-1.5 block text-[12.5px] font-medium text-slate-700"
          >
            Quantity
          </label>
          <div className="flex items-center">
            <button
              type="button"
              onClick={() => onChange(index, { quantity: Math.max(1, line.quantity - 1) })}
              className="grid h-9.5 w-9 place-items-center rounded-l-md border border-r-0 border-slate-300 bg-white text-slate-500 transition hover:bg-slate-50 disabled:text-slate-300"
              disabled={line.quantity <= 1}
              aria-label="Decrease quantity"
            >
              <Minus size={14} />
            </button>
            <input
              id={`qty-${index}`}
              type="number"
              min={1}
              value={line.quantity}
              onChange={(event) =>
                onChange(index, {
                  quantity: Math.max(1, Number(event.target.value) || 1),
                })
              }
              className="tnum h-9.5 w-16 border-y border-slate-300 bg-white text-center text-sm text-slate-900 focus:z-10 focus:outline-none focus:ring-2 focus:ring-brand-500"
              aria-label={`Quantity for ${line.name}`}
            />
            <button
              type="button"
              onClick={() => onChange(index, { quantity: line.quantity + 1 })}
              className="grid h-9.5 w-9 place-items-center rounded-r-md border border-l-0 border-slate-300 bg-white text-slate-500 transition hover:bg-slate-50"
              aria-label="Increase quantity"
            >
              <Plus size={14} />
            </button>
          </div>
          <p className="mt-1.5 text-[11.5px] text-slate-500">
            {line.available_quantity} available
          </p>
        </div>

        <Input
          label="Requested discount"
          id={`discount-${index}`}
          type="number"
          min={0}
          max={100}
          step="0.5"
          value={line.requested_discount_percent}
          onChange={(event) =>
            onChange(index, {
              requested_discount_percent: Math.min(
                100,
                Math.max(0, Number(event.target.value) || 0)
              ),
            })
          }
          error={error}
          hint={
            ceiling !== null && !overCeiling
              ? `Up to ${formatPercent(ceiling)} is automatic`
              : undefined
          }
          prefix="%"
        />

        <Input
          label="Line note (optional)"
          value={line.notes}
          maxLength={500}
          placeholder="Specification, finish, delivery site…"
          onChange={(event) => onChange(index, { notes: event.target.value })}
        />
      </div>

      <div className="mt-2.5 flex flex-wrap items-center gap-2">
        <span className="tnum text-[12.5px] text-slate-600">
          {formatMoney(gross)}
          {discount > 0 ? (
            <>
              {' '}
              − {formatMoney(discount)} ={' '}
              <span className="font-medium text-slate-800">
                {formatMoney(gross - discount)}
              </span>
              <span className="ml-1 text-slate-400">before tax</span>
            </>
          ) : (
            <span className="ml-1 text-slate-400">before tax</span>
          )}
        </span>

        {overCeiling ? (
          <Badge tone="warning" size="sm" icon={TriangleAlert}>
            Above the {formatPercent(ceiling)} ceiling — needs approval
          </Badge>
        ) : null}

        {shortfall > 0 ? (
          <Badge tone="warning" size="sm">
            {shortfall} would be backordered
            {line.lead_time_days ? ` (${line.lead_time_days}d)` : ''}
          </Badge>
        ) : null}
      </div>
    </div>
  )
}

export function NewRequest() {
  const { customer, isCustomer, isStaff } = useAuth()
  const toast = useToast()
  const navigate = useNavigate()
  const location = useLocation()

  const editRequestId = location.state?.editRequestId ?? null
  const seedProduct = location.state?.addProduct ?? null
  const seedCustomerId = location.state?.customerId ?? null

  const [lines, setLines] = useState([])
  const [customerId, setCustomerId] = useState(seedCustomerId ?? '')
  const [expectedDate, setExpectedDate] = useState('')
  const [notes, setNotes] = useState('')
  const [errors, setErrors] = useState({})
  const [formError, setFormError] = useState(null)
  const [submitting, setSubmitting] = useState(false)
  const [savingDraft, setSavingDraft] = useState(false)
  const [productSearch, setProductSearch] = useState('')
  const [loadingExisting, setLoadingExisting] = useState(Boolean(editRequestId))
  const [existing, setExisting] = useState(null)

  const debouncedProductSearch = useDebounce(productSearch)

  const policy = useAsync(() => settingsApi.getDiscountPolicy(), [])
  const products = useAsync(
    () =>
      productsApi.listCatalogue({
        page_size: 20,
        search: debouncedProductSearch || undefined,
      }),
    [debouncedProductSearch]
  )
  const customers = useAsync(
    () =>
      isStaff ? customersApi.listCustomers({ page_size: 100 }) : Promise.resolve(null),
    [isStaff]
  )

  const addProduct = useCallback(
    (product, { silent = false } = {}) => {
      setLines((current) => {
        // The backend rejects duplicate product lines, so bump the quantity on
        // the existing line rather than adding a second one.
        const existingIndex = current.findIndex(
          (line) => line.product_id === product.id
        )
        if (existingIndex >= 0) {
          const next = [...current]
          next[existingIndex] = {
            ...next[existingIndex],
            quantity: next[existingIndex].quantity + 1,
          }
          if (!silent) {
            toast.info('Quantity increased', `${product.sku} is already on this request.`)
          }
          return next
        }
        return [...current, emptyLine(product)]
      })
    },
    [toast]
  )

  /**
   * Load an existing request for editing.
   *
   * The stored lines carry everything the form needs except current stock, so
   * the availability endpoint fills that in — it is the one stock lookup a
   * customer is allowed to make.
   */
  useEffect(() => {
    if (!editRequestId) return
    let cancelled = false

    async function load() {
      try {
        const request = await requestsApi.getRequest(editRequestId)
        if (cancelled) return

        let availability = {}
        try {
          const checked = await productsApi.checkAvailability(
            request.items.map((item) => ({
              product_id: item.product_id,
              quantity: item.quantity,
            }))
          )
          availability = Object.fromEntries(
            checked.lines.map((line) => [line.product_id, line])
          )
        } catch {
          /* Stock is a nicety here; the line still edits without it. */
        }
        if (cancelled) return

        setExisting(request)
        setCustomerId(request.customer_id)
        setNotes(request.customer_notes ?? '')
        setExpectedDate(
          request.expected_delivery_date
            ? request.expected_delivery_date.slice(0, 10)
            : ''
        )
        setLines(
          request.items.map((item) => ({
            product_id: item.product_id,
            sku: item.sku,
            name: item.name,
            unit: item.unit,
            unit_price: item.unit_price,
            available_quantity:
              availability[item.product_id]?.available_quantity ??
              item.availability?.available_quantity ??
              0,
            lead_time_days:
              availability[item.product_id]?.lead_time_days ??
              item.availability?.lead_time_days ??
              0,
            // The stored line keeps the computed ceiling, not the product cap;
            // leaving this null lets the policy preview recompute it.
            max_discount_percent: null,
            quantity: item.quantity,
            requested_discount_percent: item.requested_discount_percent,
            notes: item.notes ?? '',
          }))
        )
      } catch (error) {
        if (!cancelled) {
          toast.fromError(error, 'Could not load the request')
          navigate('/requests', { replace: true })
        }
      } finally {
        if (!cancelled) setLoadingExisting(false)
      }
    }

    load()
    return () => {
      cancelled = true
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [editRequestId])

  // A product handed over from the catalogue page.
  useEffect(() => {
    if (!seedProduct) return
    addProduct(seedProduct, { silent: true })
    // Clear the state so a refresh does not re-add the line.
    navigate(location.pathname, { replace: true, state: null })
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [seedProduct])

  const selectedCustomer = useMemo(() => {
    if (isCustomer) return customer
    return (customers.data?.items ?? []).find((row) => row.id === customerId) ?? null
  }, [isCustomer, customer, customers.data, customerId])

  const customerTier = selectedCustomer?.tier ?? 'STANDARD'

  function updateLine(index, patch) {
    setLines((current) => {
      const next = [...current]
      next[index] = { ...next[index], ...patch }
      return next
    })
    if (errors[`line-${index}`]) {
      setErrors((current) => {
        const next = { ...current }
        delete next[`line-${index}`]
        return next
      })
    }
  }

  function removeLine(index) {
    setLines((current) => current.filter((_, position) => position !== index))
  }

  /** Client-side preview of the totals. The backend recomputes authoritatively. */
  const preview = useMemo(() => {
    const taxRate = policy.data?.tax_policy?.rate_percent ?? 0
    let subtotal = 0
    let discount = 0
    for (const line of lines) {
      const gross = line.unit_price * line.quantity
      subtotal += gross
      discount += (gross * line.requested_discount_percent) / 100
    }
    const taxable = subtotal - discount
    const tax = (taxable * taxRate) / 100
    return {
      subtotal,
      discount,
      taxable,
      tax,
      total: taxable + tax,
      taxRate,
      taxLabel: policy.data?.tax_policy?.name ?? 'Tax',
    }
  }, [lines, policy.data])

  const exceptionsPreview = useMemo(() => {
    const reasons = []
    for (const line of lines) {
      const ceiling = ceilingFor(
        policy.data,
        line.quantity,
        customerTier,
        line.max_discount_percent
      )
      if (ceiling !== null && line.requested_discount_percent > ceiling) {
        reasons.push(
          `${line.sku}: ${formatPercent(line.requested_discount_percent)} exceeds the ${formatPercent(ceiling)} ceiling`
        )
      }
      if (line.quantity > line.available_quantity) {
        reasons.push(
          `${line.sku}: ${line.quantity - line.available_quantity} units short of stock`
        )
      }
    }
    const threshold = policy.data?.approval_policy?.order_value_threshold ?? 0
    if (threshold > 0 && preview.total >= threshold) {
      reasons.push(
        `Order value ${formatMoney(preview.total)} reaches the ${formatMoney(threshold)} review threshold`
      )
    }
    if (
      selectedCustomer?.credit_limit > 0 &&
      selectedCustomer.outstanding_amount + preview.total > selectedCustomer.credit_limit
    ) {
      reasons.push(
        `This would take ${selectedCustomer.code} past their ${formatMoney(selectedCustomer.credit_limit)} credit limit`
      )
    }
    return reasons
  }, [lines, policy.data, customerTier, preview.total, selectedCustomer])

  function validate() {
    const next = {}
    if (isStaff && !customerId) next.customerId = 'Choose the customer this is for.'
    if (lines.length === 0) next.lines = 'Add at least one product.'

    lines.forEach((line, index) => {
      if (line.quantity < 1) next[`line-${index}`] = 'Quantity must be at least 1.'
      const absoluteMax = policy.data?.absolute_max_discount_percent
      if (absoluteMax !== undefined && line.requested_discount_percent > absoluteMax) {
        next[`line-${index}`] =
          `Company policy does not permit more than ${formatPercent(absoluteMax)} under any approval.`
      }
    })

    setErrors(next)
    return Object.keys(next).length === 0
  }

  function itemsPayload() {
    return lines.map((line) => ({
      product_id: line.product_id,
      quantity: line.quantity,
      requested_discount_percent: line.requested_discount_percent,
      notes: line.notes || undefined,
    }))
  }

  function describeOutcome(workflow) {
    const request = workflow.request
    if (workflow.outcome === 'AUTO_APPROVED') {
      toast.success(
        `${request.request_number} approved automatically`,
        'Everything was within policy. Your quotation is ready to download.'
      )
    } else if (workflow.outcome === 'PENDING_APPROVAL') {
      toast.info(
        `${request.request_number} sent for approval`,
        `${workflow.exceptions.length} rule exception(s) need a sales manager's decision.`
      )
    } else {
      toast.warning(
        `${request.request_number} could not be processed`,
        workflow.validation_errors?.[0] ?? 'The request failed validation.'
      )
    }
    navigate(`/requests/${request.id}`)
  }

  function handleError(error) {
    const fieldErrors = error.fieldErrors ?? {}
    if (Object.keys(fieldErrors).length > 0) {
      setFormError('The server rejected the request. Please review the fields.')
      setErrors(fieldErrors)
    } else {
      setFormError(error.message)
    }
    toast.fromError(error, 'Could not save the request')
  }

  async function onSubmit(event) {
    event.preventDefault()
    setFormError(null)
    if (!validate()) {
      setFormError('Please correct the highlighted fields before submitting.')
      return
    }

    setSubmitting(true)
    try {
      if (editRequestId) {
        // Save the edits first, then run the workflow on the stored request.
        await requestsApi.updateRequest(editRequestId, {
          items: itemsPayload(),
          customer_notes: notes || null,
          expected_delivery_date: expectedDate
            ? new Date(expectedDate).toISOString()
            : null,
        })
        const workflow = await requestsApi.submitRequest(editRequestId)
        describeOutcome(workflow)
      } else {
        const result = await requestsApi.createRequest({
          items: itemsPayload(),
          customer_id: isStaff ? customerId : undefined,
          expected_delivery_date: expectedDate
            ? new Date(expectedDate).toISOString()
            : undefined,
          customer_notes: notes || undefined,
          submit: true,
        })
        describeOutcome(result.workflow)
      }
    } catch (error) {
      handleError(error)
    } finally {
      setSubmitting(false)
    }
  }

  async function onSaveDraft() {
    setFormError(null)
    if (isStaff && !customerId) {
      setErrors({ customerId: 'Choose the customer this is for.' })
      return
    }
    if (lines.length === 0) {
      setErrors({ lines: 'Add at least one product.' })
      return
    }

    setSavingDraft(true)
    try {
      if (editRequestId) {
        await requestsApi.updateRequest(editRequestId, {
          items: itemsPayload(),
          customer_notes: notes || null,
          expected_delivery_date: expectedDate
            ? new Date(expectedDate).toISOString()
            : null,
        })
        toast.success(
          `${existing?.request_number ?? 'Request'} saved`,
          'Submit it when you are ready.'
        )
        navigate(`/requests/${editRequestId}`)
      } else {
        const result = await requestsApi.createRequest({
          items: itemsPayload(),
          customer_id: isStaff ? customerId : undefined,
          expected_delivery_date: expectedDate
            ? new Date(expectedDate).toISOString()
            : undefined,
          customer_notes: notes || undefined,
          submit: false,
        })
        toast.success(
          `Draft ${result.request.request_number} saved`,
          'You can edit and submit it later.'
        )
        navigate(`/requests/${result.request.id}`)
      }
    } catch (error) {
      handleError(error)
    } finally {
      setSavingDraft(false)
    }
  }

  if (loadingExisting) return <PageLoader label="Loading the request" />

  const customerOptions = (customers.data?.items ?? []).map((row) => ({
    value: row.id,
    label: `${row.company_name} (${row.code})${
      row.status !== 'ACTIVE' ? ` — ${row.status}` : ''
    }`,
  }))

  const isEdit = Boolean(editRequestId)

  return (
    <>
      <PageHeader
        title={isEdit ? `Edit ${existing?.request_number ?? 'request'}` : 'New quotation request'}
        description={
          isEdit
            ? 'Adjust the lines and resubmit. Resubmitting counts as a new revision and re-runs the full workflow.'
            : 'Add products, set quantities and request discounts. The request is validated and priced the moment you submit it.'
        }
        breadcrumbs={[
          { label: 'Requests', to: '/requests' },
          isEdit
            ? { label: existing?.request_number ?? 'Request', to: `/requests/${editRequestId}` }
            : null,
          { label: isEdit ? 'Edit' : 'New request' },
        ].filter(Boolean)}
      />

      <form onSubmit={onSubmit} noValidate>
        <div className="grid gap-4 lg:grid-cols-[1fr_340px]">
          <div className="space-y-4">
            {isStaff ? (
              <Card>
                <CardHeader
                  title="Customer"
                  description={
                    isEdit
                      ? 'The customer cannot be changed on an existing request'
                      : 'The request will be raised on their behalf'
                  }
                />
                <CardBody>
                  <Select
                    label="Customer"
                    value={customerId}
                    options={customerOptions}
                    placeholder={
                      customers.loading ? 'Loading customers…' : 'Select a customer'
                    }
                    error={errors.customerId}
                    required
                    disabled={isEdit}
                    onChange={(event) => setCustomerId(event.target.value)}
                  />
                  {selectedCustomer ? (
                    <div className="mt-3 flex flex-wrap gap-x-5 gap-y-1 rounded bg-slate-50 px-3 py-2.5 text-[12.5px]">
                      <span className="text-slate-500">
                        Tier{' '}
                        <span className="font-medium text-slate-800">
                          {selectedCustomer.tier}
                        </span>
                      </span>
                      <span className="text-slate-500">
                        Credit limit{' '}
                        <span className="font-medium text-slate-800">
                          {selectedCustomer.credit_limit > 0
                            ? formatMoney(selectedCustomer.credit_limit)
                            : 'none'}
                        </span>
                      </span>
                      <span className="text-slate-500">
                        Outstanding{' '}
                        <span className="font-medium text-slate-800">
                          {formatMoney(selectedCustomer.outstanding_amount)}
                        </span>
                      </span>
                      {selectedCustomer.status !== 'ACTIVE' ? (
                        <Badge tone="danger" size="sm">
                          {selectedCustomer.status}
                        </Badge>
                      ) : null}
                    </div>
                  ) : null}
                </CardBody>
              </Card>
            ) : null}

            <Card>
              <CardHeader
                title="Add products"
                description="Search the catalogue and add the items you need"
                icon={Package}
              />
              <CardBody>
                <SearchInput
                  value={productSearch}
                  onChange={setProductSearch}
                  placeholder="Search by name or SKU"
                />

                <div className="mt-3 max-h-64 overflow-y-auto scrollbar-thin rounded-md border border-slate-200">
                  {products.loading ? (
                    <div className="px-3 py-6 text-center">
                      <Spinner label="Loading products" />
                    </div>
                  ) : (products.data?.items ?? []).length === 0 ? (
                    <p className="px-3 py-6 text-center text-[13px] text-slate-500">
                      No products match that search.
                    </p>
                  ) : (
                    <ul className="divide-y divide-slate-100">
                      {products.data.items.map((product) => {
                        const added = lines.some((line) => line.product_id === product.id)
                        return (
                          <li
                            key={product.id}
                            className="flex items-center gap-3 px-3 py-2"
                          >
                            <div className="min-w-0 flex-1">
                              <p className="truncate text-[13px] font-medium text-slate-800">
                                {product.name}
                              </p>
                              <p className="font-mono text-[11px] text-slate-500">
                                {product.sku} · {formatMoney(product.unit_price)} ·{' '}
                                {product.available_quantity} available
                              </p>
                            </div>
                            <Button
                              type="button"
                              variant={added ? 'ghost' : 'secondary'}
                              size="sm"
                              icon={added ? CheckCircle2 : Plus}
                              onClick={() => addProduct(product)}
                            >
                              {added ? 'Added' : 'Add'}
                            </Button>
                          </li>
                        )
                      })}
                    </ul>
                  )}
                </div>
              </CardBody>
            </Card>

            <Card>
              <CardHeader
                title={`Request lines${lines.length ? ` (${lines.length})` : ''}`}
                description="Set the quantity and the discount you would like for each item"
                icon={ClipboardList}
              />
              {errors.lines ? (
                <div className="mx-4 mt-3 flex items-start gap-2 rounded border border-rose-200 bg-rose-50 px-3 py-2 sm:mx-5">
                  <AlertTriangle
                    size={14}
                    className="mt-0.5 shrink-0 text-rose-600"
                    aria-hidden="true"
                  />
                  <p className="text-[12.5px] text-rose-800">{errors.lines}</p>
                </div>
              ) : null}

              {lines.length === 0 ? (
                <EmptyState
                  icon={Package}
                  title="No products added yet"
                  description="Use the search above to add products to this request."
                />
              ) : (
                <div>
                  {lines.map((line, index) => (
                    <LineRow
                      key={line.product_id}
                      line={line}
                      index={index}
                      policy={policy.data}
                      customerTier={customerTier}
                      onChange={updateLine}
                      onRemove={removeLine}
                      error={errors[`line-${index}`]}
                    />
                  ))}
                </div>
              )}
            </Card>

            <Card>
              <CardHeader
                title="Delivery and notes"
                description="Optional details that appear on the request"
              />
              <CardBody className="space-y-4">
                <Input
                  label="Required by"
                  type="date"
                  value={expectedDate}
                  min={new Date().toISOString().slice(0, 10)}
                  onChange={(event) => setExpectedDate(event.target.value)}
                  hint="When you need the goods on site"
                  className="sm:max-w-56"
                />
                <Textarea
                  label="Notes for the sales team"
                  value={notes}
                  rows={3}
                  maxLength={1000}
                  placeholder="Delivery site, project reference, specifications…"
                  onChange={(event) => setNotes(event.target.value)}
                  hint={`${notes.length}/1000`}
                />
              </CardBody>
            </Card>
          </div>

          {/* Sticky summary: the figures update as the draft changes. */}
          <div className="space-y-4 lg:sticky lg:top-20 lg:self-start">
            <Card>
              <CardHeader title="Estimated totals" />
              <CardBody>
                {lines.length === 0 ? (
                  <p className="text-[13px] text-slate-500">
                    Add a product to see the estimate.
                  </p>
                ) : (
                  <dl className="space-y-1.5">
                    <div className="flex items-baseline justify-between gap-4">
                      <dt className="text-[13px] text-slate-500">Subtotal</dt>
                      <dd className="tnum text-[13.5px] font-medium text-slate-800">
                        {formatMoney(preview.subtotal)}
                      </dd>
                    </div>
                    <div className="flex items-baseline justify-between gap-4">
                      <dt className="text-[13px] text-slate-500">Discount requested</dt>
                      <dd className="tnum text-[13.5px] font-medium text-emerald-700">
                        −{formatMoney(preview.discount)}
                      </dd>
                    </div>
                    <div className="flex items-baseline justify-between gap-4">
                      <dt className="text-[13px] text-slate-500">Taxable amount</dt>
                      <dd className="tnum text-[13.5px] font-medium text-slate-800">
                        {formatMoney(preview.taxable)}
                      </dd>
                    </div>
                    <div className="flex items-baseline justify-between gap-4">
                      <dt className="text-[13px] text-slate-500">
                        {preview.taxLabel} ({formatPercent(preview.taxRate)})
                      </dt>
                      <dd className="tnum text-[13.5px] font-medium text-slate-800">
                        {formatMoney(preview.tax)}
                      </dd>
                    </div>
                    <div className="flex items-baseline justify-between gap-4 border-t border-navy-200 pt-2">
                      <dt className="text-[14px] font-semibold text-navy-800">
                        Estimated total
                      </dt>
                      <dd className="tnum text-[17px] font-semibold text-navy-800">
                        {formatMoney(preview.total)}
                      </dd>
                    </div>
                  </dl>
                )}

                <p className="mt-3 flex items-start gap-1.5 text-[11.5px] leading-snug text-slate-500">
                  <Info size={12} className="mt-0.5 shrink-0" aria-hidden="true" />
                  An estimate based on today's catalogue prices. The backend recalculates
                  every figure when you submit, and that result is authoritative.
                </p>
              </CardBody>
            </Card>

            {exceptionsPreview.length > 0 ? (
              <Card className="border-amber-200 bg-amber-50/60">
                <CardBody>
                  <div className="flex items-start gap-2.5">
                    <TriangleAlert
                      size={16}
                      className="mt-0.5 shrink-0 text-amber-600"
                      aria-hidden="true"
                    />
                    <div className="min-w-0">
                      <p className="text-[13px] font-semibold text-amber-900">
                        This request will need manager approval
                      </p>
                      <ul className="mt-1.5 space-y-1">
                        {exceptionsPreview.map((reason, index) => (
                          <li
                            key={index}
                            className="text-[12px] leading-snug text-amber-900/85"
                          >
                            • {reason}
                          </li>
                        ))}
                      </ul>
                      <p className="mt-2 text-[11.5px] leading-snug text-amber-700">
                        You can still submit it. A sales manager will review and decide.
                      </p>
                    </div>
                  </div>
                </CardBody>
              </Card>
            ) : lines.length > 0 ? (
              <Card className="border-emerald-200 bg-emerald-50/60">
                <CardBody>
                  <div className="flex items-start gap-2.5">
                    <CheckCircle2
                      size={16}
                      className="mt-0.5 shrink-0 text-emerald-600"
                      aria-hidden="true"
                    />
                    <div>
                      <p className="text-[13px] font-semibold text-emerald-900">
                        Within policy
                      </p>
                      <p className="mt-1 text-[12px] leading-snug text-emerald-900/80">
                        Nothing here triggers a manager review, so this should be quoted
                        automatically.
                      </p>
                    </div>
                  </div>
                </CardBody>
              </Card>
            ) : null}

            {formError ? (
              <div
                className="flex items-start gap-2.5 rounded-md border border-rose-200 bg-rose-50 px-3.5 py-3"
                role="alert"
              >
                <AlertTriangle
                  size={15}
                  className="mt-0.5 shrink-0 text-rose-600"
                  aria-hidden="true"
                />
                <p className="text-[13px] leading-snug text-rose-800">{formError}</p>
              </div>
            ) : null}

            <Card>
              <CardBody className="space-y-2">
                <Button
                  type="submit"
                  size="lg"
                  icon={Send}
                  loading={submitting}
                  disabled={lines.length === 0 || savingDraft}
                  className="w-full justify-center"
                >
                  {isEdit ? 'Save and resubmit' : 'Submit request'}
                </Button>
                <Button
                  type="button"
                  variant="secondary"
                  icon={Save}
                  loading={savingDraft}
                  disabled={lines.length === 0 || submitting}
                  onClick={onSaveDraft}
                  className="w-full justify-center"
                >
                  {isEdit ? 'Save without submitting' : 'Save as draft'}
                </Button>
                <Button
                  type="button"
                  variant="ghost"
                  disabled={submitting || savingDraft}
                  onClick={() =>
                    navigate(isEdit ? `/requests/${editRequestId}` : '/requests')
                  }
                  className="w-full justify-center"
                >
                  Cancel
                </Button>
              </CardBody>
            </Card>
          </div>
        </div>
      </form>
    </>
  )
}
