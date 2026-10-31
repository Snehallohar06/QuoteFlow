import { useMemo, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { Boxes, Info, PackageX, PlusCircle, ShoppingCart } from 'lucide-react'

import { useAuth } from '../../context/AuthContext'
import { useAsync } from '../../hooks/useAsync'
import { useDebounce } from '../../hooks/useDebounce'
import * as productsApi from '../../api/products'
import { PageHeader } from '../../components/layout/PageHeader'
import { Button } from '../../components/ui/Button'
import { Card, CardBody } from '../../components/ui/Card'
import { Badge } from '../../components/ui/Badge'
import { Checkbox } from '../../components/ui/Field'
import {
  EmptyState,
  ErrorState,
  NoResultsState,
  Pagination,
} from '../../components/ui/Table'
import { FilterSelect, SearchInput } from '../../components/ui/Toolbar'
import { formatMoney, formatPercent } from '../../lib/format'

const PAGE_SIZE = 12

function ProductCard({ product, onAdd }) {
  const outOfStock = product.available_quantity <= 0

  return (
    <Card className="flex flex-col">
      <CardBody className="flex-1">
        <div className="flex items-start justify-between gap-2">
          <p className="font-mono text-[11.5px] text-slate-500">{product.sku}</p>
          <div className="flex shrink-0 flex-wrap justify-end gap-1">
            {outOfStock ? (
              <Badge tone="danger" size="sm">
                Out of stock
              </Badge>
            ) : product.low_stock ? (
              <Badge tone="warning" size="sm">
                Low stock
              </Badge>
            ) : null}
          </div>
        </div>

        <h3 className="mt-1 text-[14.5px] font-semibold leading-snug text-navy-800">
          {product.name}
        </h3>

        {product.description ? (
          <p className="mt-1.5 line-clamp-2 text-[12.5px] leading-snug text-slate-500">
            {product.description}
          </p>
        ) : null}

        <dl className="mt-3 space-y-1.5 border-t border-slate-100 pt-3">
          <div className="flex items-baseline justify-between gap-2">
            <dt className="text-[12px] text-slate-500">Unit price</dt>
            <dd className="tnum text-[14px] font-semibold text-navy-800">
              {formatMoney(product.unit_price)}
              <span className="ml-1 text-[11.5px] font-normal text-slate-400">
                / {product.unit}
              </span>
            </dd>
          </div>
          <div className="flex items-baseline justify-between gap-2">
            <dt className="text-[12px] text-slate-500">Available</dt>
            <dd className="tnum text-[12.5px] font-medium text-slate-700">
              {product.available_quantity} {product.unit}
            </dd>
          </div>
          <div className="flex items-baseline justify-between gap-2">
            <dt className="text-[12px] text-slate-500">
              Discount you may request
              <span className="ml-1 text-slate-400">(at qty 1)</span>
            </dt>
            <dd className="tnum text-[12.5px] font-medium text-brand-700">
              {formatPercent(product.indicative_max_discount_percent)}
            </dd>
          </div>
          {product.lead_time_days > 0 ? (
            <div className="flex items-baseline justify-between gap-2">
              <dt className="text-[12px] text-slate-500">Backorder lead time</dt>
              <dd className="text-[12.5px] text-slate-700">
                {product.lead_time_days} days
              </dd>
            </div>
          ) : null}
        </dl>
      </CardBody>

      <div className="border-t border-slate-200 px-4 py-3">
        <Button
          size="sm"
          variant="secondary"
          icon={PlusCircle}
          className="w-full justify-center"
          onClick={() => onAdd(product)}
        >
          Add to request
        </Button>
      </div>
    </Card>
  )
}

export function ProductCatalogue() {
  const { customer } = useAuth()
  const navigate = useNavigate()

  const [search, setSearch] = useState('')
  const [category, setCategory] = useState(undefined)
  const [inStockOnly, setInStockOnly] = useState(false)
  const [page, setPage] = useState(1)

  const debouncedSearch = useDebounce(search)

  const categories = useAsync(() => productsApi.listCategories(), [])
  const catalogue = useAsync(
    () =>
      productsApi.listCatalogue({
        page,
        page_size: PAGE_SIZE,
        search: debouncedSearch || undefined,
        category,
        in_stock_only: inStockOnly || undefined,
      }),
    [page, debouncedSearch, category, inStockOnly]
  )

  const categoryOptions = useMemo(
    () =>
      (categories.data ?? []).map((row) => ({
        value: row.category,
        label: `${row.category} (${row.product_count})`,
      })),
    [categories.data]
  )

  const activeFilters = [debouncedSearch, category, inStockOnly].filter(Boolean).length

  function clearFilters() {
    setSearch('')
    setCategory(undefined)
    setInStockOnly(false)
    setPage(1)
  }

  /**
   * Adding from the catalogue hands the whole product to the request form
   * through router state, so the form owns the draft and the catalogue stays
   * stateless. The product object is passed rather than just its id because
   * `GET /products/{id}` is staff-only — a customer cannot re-fetch it.
   */
  function addToRequest(product) {
    navigate('/requests/new', { state: { addProduct: product } })
  }

  const items = catalogue.data?.items ?? []

  return (
    <>
      <PageHeader
        title="Product catalogue"
        description={
          customer
            ? `Prices and discount entitlements shown for ${customer.company_name} (${customer.tier} tier).`
            : 'Browse available products and request a quotation.'
        }
        actions={
          <Button icon={ShoppingCart} onClick={() => navigate('/requests/new')}>
            Build a request
          </Button>
        }
      />

      <Card className="mb-4">
        <div className="flex flex-wrap items-center gap-2 px-4 py-3 sm:px-5">
          <SearchInput
            value={search}
            onChange={(value) => {
              setSearch(value)
              setPage(1)
            }}
            placeholder="Search by name, SKU or description"
            className="w-full sm:w-80"
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
          <Checkbox
            label="In stock only"
            checked={inStockOnly}
            onChange={(event) => {
              setInStockOnly(event.target.checked)
              setPage(1)
            }}
            className="ml-1"
          />
          {activeFilters > 0 ? (
            <Button variant="ghost" size="sm" onClick={clearFilters}>
              Clear filters
            </Button>
          ) : null}
          <span className="ml-auto text-[12.5px] text-slate-500">
            {catalogue.loading
              ? 'Loading…'
              : `${catalogue.data?.meta?.total ?? 0} product(s)`}
          </span>
        </div>
      </Card>

      {catalogue.error ? (
        <Card>
          <ErrorState error={catalogue.error} onRetry={catalogue.reload} />
        </Card>
      ) : catalogue.loading ? (
        <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-3">
          {Array.from({ length: 6 }).map((_, index) => (
            <Card key={index} className="p-4">
              <div className="h-3 w-20 animate-pulse rounded bg-slate-200" />
              <div className="mt-2 h-4 w-3/4 animate-pulse rounded bg-slate-200" />
              <div className="mt-3 space-y-2">
                {[0, 1, 2].map((row) => (
                  <div key={row} className="h-3 animate-pulse rounded bg-slate-100" />
                ))}
              </div>
            </Card>
          ))}
        </div>
      ) : items.length === 0 ? (
        <Card>
          {activeFilters > 0 ? (
            <NoResultsState onClear={clearFilters} />
          ) : (
            <EmptyState
              icon={PackageX}
              title="The catalogue is empty"
              description="No active products are available right now. Please contact your sales representative."
            />
          )}
        </Card>
      ) : (
        <>
          <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-3">
            {items.map((product) => (
              <ProductCard key={product.id} product={product} onAdd={addToRequest} />
            ))}
          </div>

          {catalogue.data.meta.total_pages > 1 ? (
            <Card className="mt-4">
              <Pagination
                meta={catalogue.data.meta}
                onPageChange={setPage}
                className="border-t-0"
              />
            </Card>
          ) : null}
        </>
      )}

      <Card className="mt-4 border-brand-200 bg-brand-50/50">
        <CardBody>
          <div className="flex items-start gap-2.5">
            <Info
              size={16}
              className="mt-0.5 shrink-0 text-brand-600"
              aria-hidden="true"
            />
            <div>
              <p className="text-[13px] font-medium text-brand-900">
                How discounts work
              </p>
              <p className="mt-1 text-[12.5px] leading-relaxed text-brand-900/80">
                The discount shown on each product is the maximum you may request for a
                single unit. Larger quantities unlock higher ceilings
                {customer?.tier && customer.tier !== 'STANDARD'
                  ? `, and your ${customer.tier} tier adds a bonus on top`
                  : ''}
                . Requesting more than the ceiling is allowed — the request is simply
                routed to a sales manager for approval rather than being quoted
                automatically.
              </p>
            </div>
          </div>
        </CardBody>
      </Card>
    </>
  )
}

export { Boxes }
