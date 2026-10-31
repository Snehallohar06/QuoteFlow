import { useMemo, useState } from 'react'
import { Link } from 'react-router-dom'
import {
  Boxes,
  PackageMinus,
  PackagePlus,
  PencilLine,
  Plus,
  RefreshCw,
  ShieldQuestion,
  Trash2,
} from 'lucide-react'

import { useAuth } from '../../context/AuthContext'
import { useToast } from '../../context/ToastContext'
import { useAsync } from '../../hooks/useAsync'
import { useDebounce } from '../../hooks/useDebounce'
import * as productsApi from '../../api/products'
import * as masterDataApi from '../../api/masterData'
import { PageHeader } from '../../components/layout/PageHeader'
import { Button } from '../../components/ui/Button'
import { Card } from '../../components/ui/Card'
import { Badge } from '../../components/ui/Badge'
import { Input, Select, Textarea } from '../../components/ui/Field'
import { ConfirmDialog, Modal } from '../../components/ui/Modal'
import {
  EmptyState,
  NoResultsState,
  Pagination,
  Table,
} from '../../components/ui/Table'
import { FilterSelect, SearchInput, Toolbar } from '../../components/ui/Toolbar'
import { formatMoney, formatPercent } from '../../lib/format'
import { PRODUCT_STATUS_OPTIONS, productStatusInfo } from '../../lib/status'

const BLANK_PRODUCT = {
  sku: '',
  name: '',
  description: '',
  category: '',
  unit: 'pcs',
  unit_price: '',
  cost_price: '',
  tax_rate: '',
  stock_quantity: '0',
  reserved_quantity: '0',
  reorder_level: '0',
  lead_time_days: '0',
  max_discount_percent: '',
  status: 'ACTIVE',
}

/** Only send fields the user filled in; blanks mean "use the default". */
function toPayload(form, { isEdit }) {
  const numeric = (value) => (value === '' ? undefined : Number(value))
  const payload = {
    name: form.name.trim(),
    description: form.description.trim() || undefined,
    category: form.category.trim(),
    unit: form.unit.trim() || 'pcs',
    unit_price: numeric(form.unit_price),
    cost_price: numeric(form.cost_price) ?? 0,
    tax_rate: numeric(form.tax_rate),
    stock_quantity: numeric(form.stock_quantity) ?? 0,
    reserved_quantity: numeric(form.reserved_quantity) ?? 0,
    reorder_level: numeric(form.reorder_level) ?? 0,
    lead_time_days: numeric(form.lead_time_days) ?? 0,
    max_discount_percent: numeric(form.max_discount_percent),
    status: form.status,
  }
  if (!isEdit) payload.sku = form.sku.trim().toUpperCase()
  return payload
}

function ProductForm({ form, setForm, errors, isEdit }) {
  function set(field, value) {
    setForm((current) => ({ ...current, [field]: value }))
  }

  return (
    <div className="space-y-4">
      <div className="grid gap-4 sm:grid-cols-2">
        <Input
          label="SKU"
          value={form.sku}
          error={errors.sku}
          required={!isEdit}
          disabled={isEdit}
          placeholder="PMP-1200"
          hint={isEdit ? 'A SKU cannot be changed once products reference it' : undefined}
          onChange={(event) => set('sku', event.target.value)}
        />
        <Input
          label="Category"
          value={form.category}
          error={errors.category}
          required
          placeholder="Pumps"
          onChange={(event) => set('category', event.target.value)}
        />
      </div>

      <Input
        label="Product name"
        value={form.name}
        error={errors.name}
        required
        onChange={(event) => set('name', event.target.value)}
      />

      <Textarea
        label="Description"
        value={form.description}
        rows={2}
        maxLength={1000}
        onChange={(event) => set('description', event.target.value)}
      />

      <div className="grid gap-4 sm:grid-cols-3">
        <Input
          label="Unit price"
          type="number"
          min="0.01"
          step="0.01"
          value={form.unit_price}
          error={errors.unit_price}
          required
          prefix="₹"
          onChange={(event) => set('unit_price', event.target.value)}
        />
        <Input
          label="Cost price"
          type="number"
          min="0"
          step="0.01"
          value={form.cost_price}
          error={errors.cost_price}
          prefix="₹"
          hint="The discount floor"
          onChange={(event) => set('cost_price', event.target.value)}
        />
        <Input
          label="Unit of measure"
          value={form.unit}
          error={errors.unit}
          placeholder="pcs"
          onChange={(event) => set('unit', event.target.value)}
        />
      </div>

      <div className="grid gap-4 sm:grid-cols-3">
        <Input
          label="Stock quantity"
          type="number"
          min="0"
          value={form.stock_quantity}
          error={errors.stock_quantity}
          onChange={(event) => set('stock_quantity', event.target.value)}
        />
        <Input
          label="Reserved"
          type="number"
          min="0"
          value={form.reserved_quantity}
          error={errors.reserved_quantity}
          hint="Not quotable"
          onChange={(event) => set('reserved_quantity', event.target.value)}
        />
        <Input
          label="Reorder level"
          type="number"
          min="0"
          value={form.reorder_level}
          error={errors.reorder_level}
          hint="Low-stock flag"
          onChange={(event) => set('reorder_level', event.target.value)}
        />
      </div>

      <div className="grid gap-4 sm:grid-cols-3">
        <Input
          label="Lead time (days)"
          type="number"
          min="0"
          value={form.lead_time_days}
          error={errors.lead_time_days}
          hint="For backorders"
          onChange={(event) => set('lead_time_days', event.target.value)}
        />
        <Input
          label="Max discount"
          type="number"
          min="0"
          max="100"
          step="0.5"
          value={form.max_discount_percent}
          error={errors.max_discount_percent}
          prefix="%"
          hint="Blank = policy default"
          onChange={(event) => set('max_discount_percent', event.target.value)}
        />
        <Input
          label="Tax rate"
          type="number"
          min="0"
          max="100"
          step="0.5"
          value={form.tax_rate}
          error={errors.tax_rate}
          prefix="%"
          hint="Blank = company rate"
          onChange={(event) => set('tax_rate', event.target.value)}
        />
      </div>

      {isEdit ? (
        <Select
          label="Status"
          value={form.status}
          options={PRODUCT_STATUS_OPTIONS}
          onChange={(event) => set('status', event.target.value)}
          className="sm:max-w-56"
        />
      ) : null}
    </div>
  )
}

export function ProductManagement() {
  const { isManager } = useAuth()
  const toast = useToast()

  const [search, setSearch] = useState('')
  const [category, setCategory] = useState(undefined)
  const [status, setStatus] = useState(undefined)
  const [page, setPage] = useState(1)

  const [editing, setEditing] = useState(null) // null | 'new' | product
  const [form, setForm] = useState(BLANK_PRODUCT)
  // Only a manager may add a product outright; an employee's "add" is sent to
  // the master-data queue for approval.
  const [reason, setReason] = useState('')
  const [errors, setErrors] = useState({})
  const [saving, setSaving] = useState(false)

  const [stockTarget, setStockTarget] = useState(null)
  const [stockDelta, setStockDelta] = useState('')
  const [stockReason, setStockReason] = useState('')
  const [stockBusy, setStockBusy] = useState(false)

  const [discontinueTarget, setDiscontinueTarget] = useState(null)
  const [discontinuing, setDiscontinuing] = useState(false)

  const debouncedSearch = useDebounce(search)

  const categories = useAsync(() => productsApi.listCategories(), [])
  const products = useAsync(
    () =>
      productsApi.listProducts({
        page,
        page_size: 20,
        search: debouncedSearch || undefined,
        category,
        status,
      }),
    [page, debouncedSearch, category, status]
  )

  const categoryOptions = useMemo(
    () =>
      (categories.data ?? []).map((row) => ({
        value: row.category,
        label: row.category,
      })),
    [categories.data]
  )

  const activeFilters = [debouncedSearch, category, status].filter(Boolean).length

  function clearFilters() {
    setSearch('')
    setCategory(undefined)
    setStatus(undefined)
    setPage(1)
  }

  const needsApproval = editing === 'new' && !isManager

  function openNew() {
    setForm(BLANK_PRODUCT)
    setReason('')
    setErrors({})
    setEditing('new')
  }

  function openEdit(product) {
    setForm({
      sku: product.sku,
      name: product.name,
      description: product.description ?? '',
      category: product.category,
      unit: product.unit,
      unit_price: String(product.unit_price),
      cost_price: String(product.cost_price),
      tax_rate: product.tax_rate === null ? '' : String(product.tax_rate),
      stock_quantity: String(product.stock_quantity),
      reserved_quantity: String(product.reserved_quantity),
      reorder_level: String(product.reorder_level),
      lead_time_days: String(product.lead_time_days),
      max_discount_percent:
        product.max_discount_percent === null ? '' : String(product.max_discount_percent),
      status: product.status,
    })
    setErrors({})
    setEditing(product)
  }

  function validate() {
    const next = {}
    const isEdit = editing !== 'new'

    if (!isEdit && !form.sku.trim()) next.sku = 'Enter a SKU.'
    else if (!isEdit && form.sku.trim().length < 2) next.sku = 'That SKU is too short.'

    if (!form.name.trim()) next.name = 'Enter the product name.'
    else if (form.name.trim().length < 2) next.name = 'That name is too short.'

    if (!form.category.trim()) next.category = 'Enter a category.'

    if (form.unit_price === '' || Number(form.unit_price) <= 0) {
      next.unit_price = 'Enter a unit price greater than zero.'
    }
    if (form.cost_price !== '' && Number(form.cost_price) < 0) {
      next.cost_price = 'Cost price cannot be negative.'
    }
    if (
      form.reserved_quantity !== '' &&
      form.stock_quantity !== '' &&
      Number(form.reserved_quantity) > Number(form.stock_quantity)
    ) {
      next.reserved_quantity = 'Reserved cannot exceed the quantity in stock.'
    }

    setErrors(next)
    return Object.keys(next).length === 0
  }

  async function save() {
    if (!validate()) return
    setSaving(true)
    try {
      const isEdit = editing !== 'new'
      const payload = toPayload(form, { isEdit })
      if (isEdit) {
        await productsApi.updateProduct(editing.id, payload)
        toast.success('Product updated', form.sku)
      } else if (needsApproval) {
        const raised = await masterDataApi.submitProduct(payload, reason)
        toast.success(
          'Sent to a manager',
          `${raised.reference} — ${raised.label} will be added once approved.`
        )
      } else {
        const created = await productsApi.createProduct(payload)
        toast.success('Product added', `${created.sku} — ${created.name}`)
      }
      setEditing(null)
      products.reload()
      categories.reload()
    } catch (error) {
      const fieldErrors = error.fieldErrors ?? {}
      if (Object.keys(fieldErrors).length > 0) setErrors(fieldErrors)
      toast.fromError(error, 'Could not save the product')
    } finally {
      setSaving(false)
    }
  }

  async function applyStock() {
    const delta = Number(stockDelta)
    if (!stockDelta || Number.isNaN(delta) || delta === 0) {
      toast.warning('Enter a movement', 'Use a positive or negative quantity.')
      return
    }
    setStockBusy(true)
    try {
      const updated = await productsApi.adjustStock(
        stockTarget.id,
        delta,
        stockReason || undefined
      )
      toast.success(
        'Stock updated',
        `${updated.sku} is now ${updated.stock_quantity} in stock.`
      )
      setStockTarget(null)
      setStockDelta('')
      setStockReason('')
      products.reload()
    } catch (error) {
      toast.fromError(error, 'Could not adjust the stock')
    } finally {
      setStockBusy(false)
    }
  }

  async function discontinue() {
    setDiscontinuing(true)
    try {
      await productsApi.discontinueProduct(discontinueTarget.id)
      toast.success(
        'Product discontinued',
        `${discontinueTarget.sku} can no longer be quoted.`
      )
      setDiscontinueTarget(null)
      products.reload()
    } catch (error) {
      toast.fromError(error, 'Could not discontinue the product')
    } finally {
      setDiscontinuing(false)
    }
  }

  return (
    <>
      <PageHeader
        title="Product management"
        description="The catalogue the pricing engine reads. Prices here are used the moment a request is submitted."
        actions={
          <>
            <Button variant="secondary" icon={RefreshCw} onClick={products.reload}>
              Refresh
            </Button>
            <Button icon={Plus} onClick={openNew}>
              Add product
            </Button>
          </>
        }
      />

      {isManager ? null : (
        <p className="mb-4 flex items-start gap-1.5 rounded-md border border-amber-200 bg-amber-50 px-3 py-2 text-[12.5px] text-amber-900">
          <ShieldQuestion size={14} className="mt-0.5 shrink-0" aria-hidden="true" />
          <span>
            A sales manager approves new products, because the catalogue drives
            every price the engine calculates. What you add here is sent to them
            —{' '}
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
            placeholder="Search by name, SKU or description"
            className="w-full sm:w-72"
          />
          <FilterSelect
            value={category}
            onChange={(value) => {
              setCategory(value)
              setPage(1)
            }}
            options={categoryOptions}
            placeholder="All categories"
            label="Category"
          />
          <FilterSelect
            value={status}
            onChange={(value) => {
              setStatus(value)
              setPage(1)
            }}
            options={PRODUCT_STATUS_OPTIONS}
            placeholder="All statuses"
            label="Status"
          />
          <span className="ml-auto text-[12.5px] text-slate-500">
            {products.loading
              ? 'Loading…'
              : `${products.data?.meta?.total ?? 0} product(s)`}
          </span>
        </Toolbar>

        <Table
          columns={[
            {
              key: 'product',
              header: 'Product',
              render: (row) => (
                <div className="max-w-72">
                  <p className="truncate text-[13px] font-medium text-slate-800">
                    {row.name}
                  </p>
                  <p className="font-mono text-[11.5px] text-slate-500">
                    {row.sku} · {row.category}
                  </p>
                </div>
              ),
            },
            {
              key: 'unit_price',
              header: 'Price',
              align: 'right',
              render: (row) => (
                <div>
                  <p className="tnum text-[13px] font-medium text-slate-800">
                    {formatMoney(row.unit_price)}
                  </p>
                  <p className="tnum text-[11px] text-slate-500">
                    cost {formatMoney(row.cost_price)}
                  </p>
                </div>
              ),
            },
            {
              key: 'stock',
              header: 'Stock',
              align: 'right',
              render: (row) => {
                const low =
                  row.reorder_level > 0 && row.available_quantity <= row.reorder_level
                return (
                  <div>
                    <p
                      className={`tnum text-[13px] font-medium ${
                        row.available_quantity <= 0
                          ? 'text-rose-600'
                          : low
                            ? 'text-amber-700'
                            : 'text-slate-800'
                      }`}
                    >
                      {row.available_quantity}
                    </p>
                    <p className="tnum text-[11px] text-slate-500">
                      {row.stock_quantity} − {row.reserved_quantity} reserved
                    </p>
                  </div>
                )
              },
            },
            {
              key: 'limits',
              header: 'Overrides',
              render: (row) => (
                <div className="flex flex-col gap-0.5">
                  {row.max_discount_percent !== null ? (
                    <span className="text-[11.5px] text-slate-600">
                      max disc {formatPercent(row.max_discount_percent)}
                    </span>
                  ) : null}
                  {row.tax_rate !== null ? (
                    <span className="text-[11.5px] text-slate-600">
                      tax {formatPercent(row.tax_rate)}
                    </span>
                  ) : null}
                  {row.max_discount_percent === null && row.tax_rate === null ? (
                    <span className="text-[12px] text-slate-400">policy default</span>
                  ) : null}
                </div>
              ),
            },
            {
              key: 'status',
              header: 'Status',
              render: (row) => (
                <Badge tone={productStatusInfo(row.status).tone} size="sm">
                  {productStatusInfo(row.status).label}
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
                    aria-label={`Adjust stock for ${row.sku}`}
                    onClick={() => {
                      setStockTarget(row)
                      setStockDelta('')
                      setStockReason('')
                    }}
                  >
                    <PackagePlus size={15} className="text-slate-500" />
                  </Button>
                  <Button
                    variant="ghost"
                    size="icon-sm"
                    aria-label={`Edit ${row.sku}`}
                    onClick={() => openEdit(row)}
                  >
                    <PencilLine size={15} className="text-slate-500" />
                  </Button>
                  {isManager && row.status === 'ACTIVE' ? (
                    <Button
                      variant="ghost"
                      size="icon-sm"
                      aria-label={`Discontinue ${row.sku}`}
                      onClick={() => setDiscontinueTarget(row)}
                    >
                      <Trash2 size={15} className="text-rose-500" />
                    </Button>
                  ) : null}
                </div>
              ),
            },
          ]}
          rows={products.data?.items ?? []}
          loading={products.loading}
          error={products.error}
          empty={
            activeFilters > 0 ? (
              <NoResultsState onClear={clearFilters} />
            ) : (
              <EmptyState
                icon={Boxes}
                title="No products yet"
                description="Add your first product to start quoting."
                action={
                  <Button icon={Plus} onClick={openNew}>
                    Add product
                  </Button>
                }
              />
            )
          }
        />

        <Pagination meta={products.data?.meta} onPageChange={setPage} />
      </Card>

      <Modal
        open={Boolean(editing)}
        onClose={saving ? undefined : () => setEditing(null)}
        title={
          needsApproval
            ? 'Request a new product'
            : editing === 'new'
              ? 'Add a product'
              : `Edit ${form.sku}`
        }
        description={
          needsApproval
            ? 'A sales manager reviews these details and the product is added to the catalogue once they approve.'
            : editing === 'new'
              ? 'The SKU must be unique. Cost price becomes the floor no discount may breach.'
              : 'Changes apply to requests submitted from now on; issued quotations keep their original figures.'
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
                  ? 'Add product'
                  : 'Save changes'}
            </Button>
          </>
        }
      >
        <div className="space-y-4">
          <ProductForm
            form={form}
            setForm={setForm}
            errors={errors}
            isEdit={editing !== 'new'}
          />

          {needsApproval ? (
            <Textarea
              label="Why this product is needed"
              value={reason}
              rows={2}
              maxLength={500}
              placeholder="Context for the manager deciding — supplier, expected demand…"
              hint="Optional, but it usually saves a round trip."
              onChange={(event) => setReason(event.target.value)}
            />
          ) : null}
        </div>
      </Modal>

      <Modal
        open={Boolean(stockTarget)}
        onClose={stockBusy ? undefined : () => setStockTarget(null)}
        title={`Stock movement — ${stockTarget?.sku ?? ''}`}
        description={
          stockTarget
            ? `Currently ${stockTarget.stock_quantity} in stock, ${stockTarget.reserved_quantity} reserved.`
            : undefined
        }
        footer={
          <>
            <Button
              variant="secondary"
              onClick={() => setStockTarget(null)}
              disabled={stockBusy}
            >
              Cancel
            </Button>
            <Button loading={stockBusy} onClick={applyStock}>
              Apply movement
            </Button>
          </>
        }
      >
        <div className="space-y-4">
          <div className="flex gap-2">
            <Button
              variant="secondary"
              size="sm"
              icon={PackagePlus}
              onClick={() => setStockDelta('10')}
            >
              +10
            </Button>
            <Button
              variant="secondary"
              size="sm"
              icon={PackagePlus}
              onClick={() => setStockDelta('50')}
            >
              +50
            </Button>
            <Button
              variant="secondary"
              size="sm"
              icon={PackageMinus}
              onClick={() => setStockDelta('-10')}
            >
              −10
            </Button>
          </div>

          <Input
            label="Movement"
            type="number"
            value={stockDelta}
            onChange={(event) => setStockDelta(event.target.value)}
            hint="Positive to receive stock, negative to issue it"
            className="sm:max-w-48"
          />

          {stockTarget && stockDelta !== '' && !Number.isNaN(Number(stockDelta)) ? (
            <p className="rounded bg-slate-50 px-3 py-2 text-[12.5px] text-slate-600">
              New stock level:{' '}
              <span className="tnum font-semibold text-slate-800">
                {stockTarget.stock_quantity + Number(stockDelta)}
              </span>
              {stockTarget.stock_quantity + Number(stockDelta) <
              stockTarget.reserved_quantity ? (
                <span className="ml-1 text-rose-600">
                  — below the {stockTarget.reserved_quantity} reserved, which the backend
                  will refuse
                </span>
              ) : null}
            </p>
          ) : null}

          <Input
            label="Reason (optional)"
            value={stockReason}
            maxLength={200}
            placeholder="Goods received, stock count correction…"
            onChange={(event) => setStockReason(event.target.value)}
            hint="Recorded on the audit trail"
          />
        </div>
      </Modal>

      <ConfirmDialog
        open={Boolean(discontinueTarget)}
        onClose={() => setDiscontinueTarget(null)}
        onConfirm={discontinue}
        title={`Discontinue ${discontinueTarget?.sku ?? ''}?`}
        message="The product stops appearing in the catalogue and cannot be quoted. It is not deleted — historical quotations keep referencing it, and you can set it back to active later."
        confirmLabel="Discontinue"
        loading={discontinuing}
      />
    </>
  )
}
