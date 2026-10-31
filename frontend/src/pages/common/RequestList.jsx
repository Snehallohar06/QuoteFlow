import { useState } from 'react'
import { useNavigate, useSearchParams } from 'react-router-dom'
import { ClipboardList, PlusCircle, RefreshCw } from 'lucide-react'

import { useAuth } from '../../context/AuthContext'
import { useAsync } from '../../hooks/useAsync'
import { useDebounce } from '../../hooks/useDebounce'
import * as requestsApi from '../../api/requests'
import { PageHeader } from '../../components/layout/PageHeader'
import { Button } from '../../components/ui/Button'
import { Card } from '../../components/ui/Card'
import { Badge, StatusBadge } from '../../components/ui/Badge'
import {
  EmptyState,
  NoResultsState,
  Pagination,
  Table,
} from '../../components/ui/Table'
import { FilterSelect, SearchInput, Toolbar } from '../../components/ui/Toolbar'
import { formatMoney, formatRelative } from '../../lib/format'
import {
  REQUEST_STATUS_OPTIONS,
  exceptionInfo,
  isEscalated,
  requestStatusInfo,
} from '../../lib/status'

/**
 * The quotation request list.
 *
 * One page serves all three roles. The backend scopes the rows — a customer only
 * ever receives their own — so the only difference here is which columns and
 * filters are worth showing.
 */
export function RequestList() {
  const { isCustomer, isStaff } = useAuth()
  const navigate = useNavigate()
  const [searchParams, setSearchParams] = useSearchParams()

  const [search, setSearch] = useState('')
  const [status, setStatus] = useState(searchParams.get('status') ?? undefined)
  const [page, setPage] = useState(1)

  const debouncedSearch = useDebounce(search)

  const requests = useAsync(
    () =>
      requestsApi.listRequests({
        page,
        page_size: 20,
        status,
        search: debouncedSearch || undefined,
      }),
    [page, status, debouncedSearch]
  )

  const activeFilters = [debouncedSearch, status].filter(Boolean).length

  function clearFilters() {
    setSearch('')
    setStatus(undefined)
    setPage(1)
    setSearchParams({}, { replace: true })
  }

  const columns = [
    {
      key: 'request_number',
      header: 'Request',
      render: (row) => (
        <div>
          <p className="font-mono text-[12.5px] font-medium text-slate-800">
            {row.request_number}
          </p>
          <p className="mt-0.5 text-[12px] text-slate-500">
            {formatRelative(row.submitted_at ?? row.created_at)}
            {row.revision > 0 ? ` · rev ${row.revision}` : ''}
          </p>
        </div>
      ),
    },
    ...(isCustomer
      ? []
      : [
          {
            key: 'customer_name',
            header: 'Customer',
            render: (row) => (
              <div className="max-w-52">
                <p className="truncate text-[13px] text-slate-800">
                  {row.customer_name}
                </p>
                <p className="font-mono text-[11.5px] text-slate-500">
                  {row.customer_code}
                </p>
              </div>
            ),
          },
        ]),
    {
      key: 'lines',
      header: 'Lines',
      align: 'right',
      render: (row) => (
        <span className="tnum text-[13px] text-slate-700">
          {row.pricing?.line_count ?? row.items?.length ?? 0}
        </span>
      ),
    },
    {
      key: 'status',
      header: 'Status',
      render: (row) => (
        <div className="flex flex-wrap items-center gap-1.5">
          <StatusBadge info={requestStatusInfo(row.status, row)} size="sm" />
          {isEscalated(row) ? (
            <Badge tone="warning" size="sm">
              Escalated
            </Badge>
          ) : null}
        </div>
      ),
    },
    {
      key: 'exceptions',
      header: 'Flags',
      render: (row) => {
        if (row.validation_errors?.length) {
          return (
            <Badge tone="danger" size="sm">
              {row.validation_errors.length} error
              {row.validation_errors.length === 1 ? '' : 's'}
            </Badge>
          )
        }
        if (!row.exceptions?.length) {
          return <span className="text-[12.5px] text-slate-400">—</span>
        }
        return (
          <div className="flex flex-wrap gap-1">
            {row.exceptions.slice(0, 2).map((exception, index) => (
              <Badge key={index} tone={exceptionInfo(exception.type).tone} size="sm">
                {exceptionInfo(exception.type).label}
              </Badge>
            ))}
            {row.exceptions.length > 2 ? (
              <Badge tone="neutral" size="sm">
                +{row.exceptions.length - 2}
              </Badge>
            ) : null}
          </div>
        )
      },
    },
    {
      key: 'amount',
      header: 'Amount',
      align: 'right',
      render: (row) =>
        row.pricing ? (
          <span className="tnum font-medium text-slate-800">
            {formatMoney(row.pricing.final_amount, { currency: row.pricing.currency })}
          </span>
        ) : (
          <span className="text-[12.5px] text-slate-400">not priced</span>
        ),
    },
  ]

  return (
    <>
      <PageHeader
        title={isCustomer ? 'My quotation requests' : 'Quotation requests'}
        description={
          isCustomer
            ? 'Every request you have submitted, and where each one has reached.'
            : 'All customer requests across the pipeline.'
        }
        actions={
          <>
            <Button variant="secondary" icon={RefreshCw} onClick={requests.reload}>
              Refresh
            </Button>
            {isCustomer ? (
              <Button icon={PlusCircle} onClick={() => navigate('/requests/new')}>
                New request
              </Button>
            ) : (
              <Button
                icon={PlusCircle}
                onClick={() => navigate('/requests/new/for-customer')}
              >
                Raise for a customer
              </Button>
            )}
          </>
        }
      />

      <Card>
        <Toolbar activeCount={activeFilters} onClear={clearFilters}>
          <SearchInput
            value={search}
            onChange={(value) => {
              setSearch(value)
              setPage(1)
            }}
            placeholder={
              isCustomer
                ? 'Search by request number or SKU'
                : 'Search by request number, customer or SKU'
            }
            className="w-full sm:w-72"
          />
          <FilterSelect
            value={status}
            onChange={(value) => {
              setStatus(value)
              setPage(1)
            }}
            options={REQUEST_STATUS_OPTIONS}
            placeholder="All statuses"
            label="Status"
          />
          <span className="ml-auto text-[12.5px] text-slate-500">
            {requests.loading ? 'Loading…' : `${requests.data?.meta?.total ?? 0} request(s)`}
          </span>
        </Toolbar>

        <Table
          columns={columns}
          rows={requests.data?.items ?? []}
          loading={requests.loading}
          error={requests.error}
          onRowClick={(row) => navigate(`/requests/${row.id}`)}
          empty={
            activeFilters > 0 ? (
              <NoResultsState onClear={clearFilters} />
            ) : (
              <EmptyState
                icon={ClipboardList}
                title={isCustomer ? 'No requests yet' : 'No requests in the system'}
                description={
                  isCustomer
                    ? 'Browse the catalogue and submit your first quotation request.'
                    : 'Requests submitted by customers will appear here.'
                }
                action={
                  isCustomer ? (
                    <Button
                      icon={PlusCircle}
                      onClick={() => navigate('/requests/new')}
                    >
                      Create a request
                    </Button>
                  ) : null
                }
              />
            )
          }
        />

        <Pagination meta={requests.data?.meta} onPageChange={setPage} />
      </Card>

      {isStaff ? (
        <p className="mt-3 text-[12px] text-slate-500">
          Click any row to open the full request, its priced lines and the step-by-step
          workflow trace.
        </p>
      ) : null}
    </>
  )
}
