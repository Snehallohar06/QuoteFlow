import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { Download, FileText, RefreshCw, Timer } from 'lucide-react'

import { useAuth } from '../../context/AuthContext'
import { useToast } from '../../context/ToastContext'
import { useAsync } from '../../hooks/useAsync'
import { useDebounce } from '../../hooks/useDebounce'
import * as quotationsApi from '../../api/quotations'
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
import { daysUntil, formatDate, formatMoney } from '../../lib/format'
import { QUOTATION_STATUS_OPTIONS, quotationStatusInfo } from '../../lib/status'

export function QuotationList() {
  const { isCustomer, isStaff } = useAuth()
  const toast = useToast()
  const navigate = useNavigate()

  const [search, setSearch] = useState('')
  const [status, setStatus] = useState(undefined)
  const [page, setPage] = useState(1)
  const [downloading, setDownloading] = useState(null)
  const [expiring, setExpiring] = useState(false)

  const debouncedSearch = useDebounce(search)

  const quotations = useAsync(
    () =>
      quotationsApi.listQuotations({
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
  }

  async function download(quotation, event) {
    event.stopPropagation()
    setDownloading(quotation.id)
    try {
      await quotationsApi.downloadQuotationPdf(
        quotation.id,
        quotation.quotation_number
      )
      toast.success('Download started', `${quotation.quotation_number}.pdf`)
      quotations.reload()
    } catch (error) {
      toast.fromError(error, 'Could not download the quotation')
    } finally {
      setDownloading(null)
    }
  }

  async function sweepExpired() {
    setExpiring(true)
    try {
      const count = await quotationsApi.expireDueQuotations()
      toast.success(
        count > 0 ? `${count} quotation(s) expired` : 'Nothing to expire',
        count > 0
          ? 'Quotations past their validity date were marked expired.'
          : 'Every issued quotation is still within its validity window.'
      )
      quotations.reload()
    } catch (error) {
      toast.fromError(error, 'Could not run the expiry sweep')
    } finally {
      setExpiring(false)
    }
  }

  return (
    <>
      <PageHeader
        title={isCustomer ? 'My quotations' : 'Quotation history'}
        description={
          isCustomer
            ? 'Verified quotation documents issued to you.'
            : 'Every quotation issued by the system, with its verification code.'
        }
        actions={
          <>
            <Button variant="secondary" icon={RefreshCw} onClick={quotations.reload}>
              Refresh
            </Button>
            {isStaff ? (
              <Button
                variant="secondary"
                icon={Timer}
                loading={expiring}
                onClick={sweepExpired}
              >
                Expire overdue
              </Button>
            ) : null}
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
            placeholder="Search by number, request or verification code"
            className="w-full sm:w-80"
          />
          <FilterSelect
            value={status}
            onChange={(value) => {
              setStatus(value)
              setPage(1)
            }}
            options={QUOTATION_STATUS_OPTIONS}
            placeholder="All statuses"
            label="Status"
          />
          <span className="ml-auto text-[12.5px] text-slate-500">
            {quotations.loading
              ? 'Loading…'
              : `${quotations.data?.meta?.total ?? 0} quotation(s)`}
          </span>
        </Toolbar>

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
                  <p className="mt-0.5 font-mono text-[11.5px] text-slate-500">
                    from {row.request_number}
                  </p>
                </div>
              ),
            },
            ...(isCustomer
              ? []
              : [
                  {
                    key: 'buyer',
                    header: 'Customer',
                    render: (row) => (
                      <div className="max-w-48">
                        <p className="truncate text-[13px] text-slate-800">
                          {row.buyer.name}
                        </p>
                        <p className="font-mono text-[11.5px] text-slate-500">
                          {row.buyer.code}
                        </p>
                      </div>
                    ),
                  },
                ]),
            {
              key: 'issued_at',
              header: 'Issued',
              render: (row) => (
                <span className="text-[12.5px] text-slate-600">
                  {formatDate(row.issued_at)}
                </span>
              ),
            },
            {
              key: 'valid_until',
              header: 'Valid until',
              render: (row) => {
                const days = daysUntil(row.valid_until)
                const expired = days !== null && days < 0
                return (
                  <div>
                    <p className="text-[12.5px] text-slate-600">
                      {formatDate(row.valid_until)}
                    </p>
                    {row.status === 'ISSUED' ? (
                      <p
                        className={`text-[11px] ${
                          expired
                            ? 'font-medium text-rose-600'
                            : days <= 7
                              ? 'font-medium text-amber-600'
                              : 'text-slate-400'
                        }`}
                      >
                        {expired
                          ? `${Math.abs(days)} days overdue`
                          : `${days} days left`}
                      </p>
                    ) : null}
                  </div>
                )
              },
            },
            {
              key: 'approval',
              header: 'Authorisation',
              render: (row) =>
                row.auto_approved ? (
                  <Badge tone="success" size="sm">
                    Automatic
                  </Badge>
                ) : (
                  <div className="max-w-36">
                    <Badge tone="info" size="sm">
                      Manager
                    </Badge>
                    <p className="mt-0.5 truncate text-[11px] text-slate-500">
                      {row.approved_by_name}
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
            {
              key: 'actions',
              header: '',
              align: 'right',
              render: (row) => (
                <Button
                  variant="secondary"
                  size="sm"
                  icon={Download}
                  loading={downloading === row.id}
                  onClick={(event) => download(row, event)}
                >
                  PDF
                </Button>
              ),
            },
          ]}
          rows={quotations.data?.items ?? []}
          loading={quotations.loading}
          error={quotations.error}
          onRowClick={(row) => navigate(`/quotations/${row.id}`)}
          empty={
            activeFilters > 0 ? (
              <NoResultsState onClear={clearFilters} />
            ) : (
              <EmptyState
                icon={FileText}
                title="No quotations yet"
                description={
                  isCustomer
                    ? 'An approved request produces a quotation you can download here.'
                    : 'Quotations appear here once requests are approved.'
                }
              />
            )
          }
        />

        <Pagination meta={quotations.data?.meta} onPageChange={setPage} />
      </Card>
    </>
  )
}
