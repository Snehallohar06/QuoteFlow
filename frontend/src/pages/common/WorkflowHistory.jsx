import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { FileSearch, Gauge, RefreshCw } from 'lucide-react'

import { useAsync } from '../../hooks/useAsync'
import { useDebounce } from '../../hooks/useDebounce'
import * as requestsApi from '../../api/requests'
import * as analyticsApi from '../../api/analytics'
import { PageHeader } from '../../components/layout/PageHeader'
import { Button } from '../../components/ui/Button'
import { Card, CardBody, CardHeader, StatCard } from '../../components/ui/Card'
import { Badge, StatusBadge } from '../../components/ui/Badge'
import {
  EmptyState,
  NoResultsState,
  Pagination,
  Table,
} from '../../components/ui/Table'
import { FilterSelect, SearchInput, Toolbar } from '../../components/ui/Toolbar'
import { RankedBars } from '../../components/ui/ChartTooltip'
import { formatDuration, formatPercent, formatRelative, humanise } from '../../lib/format'
import { REQUEST_STATUS_OPTIONS, outcomeInfo, requestStatusInfo } from '../../lib/status'

/**
 * Workflow execution history.
 *
 * The backend exposes executions per request rather than as one global feed, so
 * this page lists requests and links through to each one's stored trace. The
 * aggregate figures beside it come from the analytics endpoint, which does read
 * across every execution.
 */
export function WorkflowHistory() {
  const navigate = useNavigate()

  const [search, setSearch] = useState('')
  const [status, setStatus] = useState(undefined)
  const [page, setPage] = useState(1)
  const [days, setDays] = useState('30')

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
  const performance = useAsync(
    () => analyticsApi.getWorkflowPerformance(Number(days)),
    [days]
  )

  const stats = performance.data
  const activeFilters = [debouncedSearch, status].filter(Boolean).length

  function clearFilters() {
    setSearch('')
    setStatus(undefined)
    setPage(1)
  }

  const outcomeRows = Object.entries(stats?.by_outcome ?? {}).map(
    ([outcome, count]) => ({
      key: outcome,
      label: outcomeInfo(outcome).label,
      value: count,
    })
  )

  return (
    <>
      <PageHeader
        title="Workflow execution history"
        description="Every pipeline run is stored with per-step timings and outputs. Open a request to read its trace."
        actions={
          <>
            <FilterSelect
              value={days}
              onChange={(value) => setDays(value || '30')}
              options={[
                { value: '7', label: 'Last 7 days' },
                { value: '30', label: 'Last 30 days' },
                { value: '90', label: 'Last 90 days' },
                { value: '365', label: 'Last year' },
              ]}
              placeholder="Last 30 days"
              label="Reporting window"
            />
            <Button
              variant="secondary"
              icon={RefreshCw}
              onClick={() => {
                requests.reload()
                performance.reload()
              }}
            >
              Refresh
            </Button>
          </>
        }
      />

      <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
        <StatCard
          label="Executions"
          value={stats?.total_executions ?? 0}
          icon={Gauge}
          tone="navy"
          loading={performance.loading}
          hint={`in the last ${days} days`}
        />
        <StatCard
          label="Straight through"
          value={formatPercent(stats?.straight_through_percent ?? 0)}
          tone="emerald"
          loading={performance.loading}
          hint="Auto-approved with no manager"
        />
        <StatCard
          label="Average duration"
          value={formatDuration(stats?.average_duration_ms ?? 0)}
          tone="blue"
          loading={performance.loading}
          hint="End to end, per run"
        />
        <StatCard
          label="Step failures"
          value={
            stats?.steps?.reduce((sum, step) => sum + (step.failures ?? 0), 0) ?? 0
          }
          tone={
            (stats?.steps?.reduce((sum, step) => sum + (step.failures ?? 0), 0) ?? 0) > 0
              ? 'rose'
              : 'slate'
          }
          loading={performance.loading}
          hint="Across all steps"
        />
      </div>

      <div className="mt-4 grid gap-4 lg:grid-cols-3">
        <Card>
          <CardHeader title="Outcomes" description="How runs in this window ended" />
          <CardBody>
            {performance.loading ? (
              <div className="h-28 animate-pulse rounded bg-slate-100" />
            ) : (
              <RankedBars rows={outcomeRows} emptyLabel="No executions in this window" />
            )}
          </CardBody>
        </Card>

        <Card className="lg:col-span-2">
          <CardHeader
            title="Step performance"
            description="Average duration and failure count for each pipeline step"
          />
          <Table
            columns={[
              {
                key: 'step',
                header: 'Step',
                render: (row) => (
                  <span className="text-[13px] font-medium text-slate-800">
                    {humanise(row.step)}
                  </span>
                ),
              },
              {
                key: 'executions',
                header: 'Runs',
                align: 'right',
                render: (row) => <span className="tnum">{row.executions}</span>,
              },
              {
                key: 'average_duration_ms',
                header: 'Avg duration',
                align: 'right',
                render: (row) => (
                  <span className="tnum">{row.average_duration_ms} ms</span>
                ),
              },
              {
                key: 'failures',
                header: 'Failures',
                align: 'right',
                render: (row) =>
                  row.failures > 0 ? (
                    <Badge tone="danger" size="sm">
                      {row.failures}
                    </Badge>
                  ) : (
                    <span className="text-[12.5px] text-slate-400">none</span>
                  ),
              },
            ]}
            rows={stats?.steps ?? []}
            loading={performance.loading}
            error={performance.error}
            empty={
              <EmptyState
                icon={Gauge}
                title="No executions recorded"
                description="Submit a request to see the pipeline run."
              />
            }
          />
        </Card>
      </div>

      <Card className="mt-4">
        <CardHeader
          title="Requests and their traces"
          description="Open a request to read its step-by-step execution history"
          icon={FileSearch}
        />
        <Toolbar activeCount={activeFilters} onClear={clearFilters}>
          <SearchInput
            value={search}
            onChange={(value) => {
              setSearch(value)
              setPage(1)
            }}
            placeholder="Search by request number or customer"
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
            {requests.loading
              ? 'Loading…'
              : `${requests.data?.meta?.total ?? 0} request(s)`}
          </span>
        </Toolbar>

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
                  <p className="text-[11.5px] text-slate-500">{row.customer_name}</p>
                </div>
              ),
            },
            {
              key: 'status',
              header: 'Current status',
              render: (row) => (
                <StatusBadge info={requestStatusInfo(row.status, row)} size="sm" />
              ),
            },
            {
              key: 'revision',
              header: 'Revisions',
              align: 'right',
              render: (row) => (
                <span className="tnum text-[12.5px] text-slate-600">
                  {row.revision + 1}
                </span>
              ),
            },
            {
              key: 'last_execution_id',
              header: 'Last run',
              render: (row) =>
                row.last_execution_id ? (
                  <span className="text-[12.5px] text-slate-500">
                    {formatRelative(row.updated_at)}
                  </span>
                ) : (
                  <span className="text-[12px] text-slate-400">never run</span>
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
                  icon={FileSearch}
                  onClick={(event) => {
                    event.stopPropagation()
                    navigate(`/requests/${row.id}`)
                  }}
                >
                  View trace
                </Button>
              ),
            },
          ]}
          rows={requests.data?.items ?? []}
          loading={requests.loading}
          error={requests.error}
          onRowClick={(row) => navigate(`/requests/${row.id}`)}
          empty={
            activeFilters > 0 ? (
              <NoResultsState onClear={clearFilters} />
            ) : (
              <EmptyState
                icon={FileSearch}
                title="No requests yet"
                description="Workflow traces appear once requests are submitted."
              />
            )
          }
        />

        <Pagination meta={requests.data?.meta} onPageChange={setPage} />
      </Card>
    </>
  )
}
