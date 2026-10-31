import { useNavigate } from 'react-router-dom'
import {
  ArrowRight,
  BarChart3,
  ClipboardCheck,
  ClipboardList,
  FileText,
  Gauge,
  RefreshCw,
  TrendingUp,
  TriangleAlert,
  XCircle,
} from 'lucide-react'
import {
  Area,
  AreaChart,
  Bar,
  BarChart,
  CartesianGrid,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts'

import { useAsync } from '../../hooks/useAsync'
import * as analyticsApi from '../../api/analytics'
import * as approvalsApi from '../../api/approvals'
import { PageHeader } from '../../components/layout/PageHeader'
import { Button } from '../../components/ui/Button'
import { Card, CardBody, CardHeader, StatCard } from '../../components/ui/Card'
import { Badge } from '../../components/ui/Badge'
import { ChartTooltip, RankedBars } from '../../components/ui/ChartTooltip'
import { EmptyState, Table } from '../../components/ui/Table'
import {
  formatHours,
  formatMoney,
  formatMoneyCompact,
  formatPercent,
  formatRelative,
  humanise,
} from '../../lib/format'
import {
  BAR_RADIUS,
  CHART_INK,
  GRID_PROPS,
  SERIES,
  X_AXIS_PROPS,
  Y_AXIS_PROPS,
  chartDate,
  chartMonth,
} from '../../lib/charts'
import { exceptionInfo, requestStatusInfo } from '../../lib/status'

/** Status order for the outcome-mix chart; stable so bars never reshuffle. */
const OUTCOME_ORDER = [
  'APPROVED',
  'PENDING_APPROVAL',
  'MODIFICATION_REQUESTED',
  'VALIDATION_FAILED',
  'REJECTED',
  'SUBMITTED',
  'UNDER_VALIDATION',
  'PRICED',
  'CANCELLED',
  'DRAFT',
]

export function ManagerDashboard() {
  const navigate = useNavigate()

  const dashboard = useAsync(() => analyticsApi.getDashboard(30), [])
  const pending = useAsync(
    () => approvalsApi.listApprovals({ status: 'PENDING', page_size: 6 }),
    []
  )

  const data = dashboard.data
  const overview = data?.overview
  const trend = data?.request_trend ?? []
  const revenue = data?.revenue_trend ?? []
  const exceptions = data?.exception_breakdown ?? []
  const approvalPerf = data?.approval_performance
  const workflowPerf = data?.workflow_performance

  const outcomeRows = OUTCOME_ORDER.filter(
    (status) => (overview?.requests_by_status?.[status] ?? 0) > 0
  ).map((status) => ({
    key: status,
    label: requestStatusInfo(status).label,
    value: overview.requests_by_status[status],
  }))

  const exceptionRows = exceptions.map((row) => ({
    key: row.type,
    label: exceptionInfo(row.type).label,
    value: row.count,
    hint: `${formatPercent(row.share_percent)} of all exceptions`,
  }))

  function reloadAll() {
    dashboard.reload()
    pending.reload()
  }

  return (
    <>
      <PageHeader
        title="Manager dashboard"
        description="Pipeline, approvals and automation performance over the last 30 days."
        actions={
          <>
            <Button variant="secondary" icon={RefreshCw} onClick={reloadAll}>
              Refresh
            </Button>
            <Button
              variant="secondary"
              icon={BarChart3}
              onClick={() => navigate('/analytics')}
            >
              Full analytics
            </Button>
            <Button icon={ClipboardCheck} onClick={() => navigate('/approvals')}>
              Approvals
              {overview?.pending_approvals ? (
                <span className="ml-1 rounded-full bg-white/25 px-1.5 text-[11px] font-semibold">
                  {overview.pending_approvals}
                </span>
              ) : null}
            </Button>
          </>
        }
      />

      <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
        <StatCard
          label="Total requests"
          value={overview?.total_requests ?? 0}
          icon={ClipboardList}
          tone="navy"
          loading={dashboard.loading}
          hint={`${overview?.open_requests ?? 0} open`}
        />
        <StatCard
          label="Pending approvals"
          value={overview?.pending_approvals ?? 0}
          icon={ClipboardCheck}
          tone={overview?.overdue_approvals ? 'rose' : 'amber'}
          loading={dashboard.loading}
          hint={
            overview?.overdue_approvals
              ? `${overview.overdue_approvals} past SLA`
              : 'All within SLA'
          }
        />
        <StatCard
          label="Quoted value"
          value={formatMoney(overview?.quoted_value ?? 0)}
          icon={TrendingUp}
          tone="emerald"
          loading={dashboard.loading}
          hint={`${overview?.quotations_issued ?? 0} quotations`}
        />
        <StatCard
          label="Straight-through rate"
          value={formatPercent(overview?.automation_rate_percent ?? 0)}
          icon={Gauge}
          tone="blue"
          loading={dashboard.loading}
          hint={`${overview?.auto_approved_quotations ?? 0} auto-approved`}
        />
      </div>

      <div className="mt-4 grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
        <StatCard
          label="Approval rate"
          value={formatPercent(overview?.approval_rate_percent ?? 0)}
          tone="slate"
          loading={dashboard.loading}
          hint={`${overview?.approved_requests ?? 0} approved · ${
            overview?.rejected_requests ?? 0
          } rejected`}
        />
        <StatCard
          label="Avg processing time"
          value={formatHours(approvalPerf?.average_turnaround_hours ?? 0)}
          tone="slate"
          loading={dashboard.loading}
          hint={`${approvalPerf?.decided ?? 0} decisions`}
        />
        <StatCard
          label="SLA compliance"
          value={formatPercent(approvalPerf?.sla_compliance_percent ?? 0)}
          tone="slate"
          loading={dashboard.loading}
          hint={`${approvalPerf?.within_sla ?? 0} within target`}
        />
        <StatCard
          label="Discount given"
          value={formatMoney(overview?.total_discount_given ?? 0)}
          tone="slate"
          loading={dashboard.loading}
          hint={`${formatPercent(overview?.discount_rate_percent ?? 0)} of gross`}
        />
      </div>

      <div className="mt-4 grid gap-4 lg:grid-cols-3">
        {/* Single series: volume over time. Identity needs no colour. */}
        <Card className="lg:col-span-2">
          <CardHeader
            title="Requests submitted per day"
            description="Total quotation requests received over the reporting window"
          />
          <CardBody>
            {dashboard.loading ? (
              <div className="h-60 animate-pulse rounded bg-slate-100" />
            ) : trend.length === 0 ? (
              <EmptyState
                icon={BarChart3}
                title="No activity in this window"
                description="Submit a request, or widen the reporting period."
              />
            ) : (
              <ResponsiveContainer width="100%" height={240}>
                <AreaChart
                  data={trend}
                  margin={{ top: 6, right: 10, left: -18, bottom: 0 }}
                >
                  <defs>
                    <linearGradient id="requestVolume" x1="0" y1="0" x2="0" y2="1">
                      <stop offset="0%" stopColor={SERIES[0]} stopOpacity={0.22} />
                      <stop offset="100%" stopColor={SERIES[0]} stopOpacity={0.02} />
                    </linearGradient>
                  </defs>
                  <CartesianGrid {...GRID_PROPS} vertical={false} />
                  <XAxis dataKey="date" tickFormatter={chartDate} {...X_AXIS_PROPS} />
                  <YAxis allowDecimals={false} width={38} {...Y_AXIS_PROPS} />
                  <Tooltip
                    content={<ChartTooltip labelFormatter={chartDate} />}
                    cursor={{ stroke: CHART_INK.axis, strokeWidth: 1 }}
                  />
                  <Area
                    type="monotone"
                    dataKey="total"
                    name="Requests"
                    stroke={SERIES[0]}
                    strokeWidth={2}
                    fill="url(#requestVolume)"
                    activeDot={{ r: 4.5, strokeWidth: 2, stroke: '#ffffff' }}
                  />
                </AreaChart>
              </ResponsiveContainer>
            )}
          </CardBody>
        </Card>

        {/* Outcome mix as a ranked list: the status name is the label, at full
            contrast, so no colour separation is needed between nine statuses. */}
        <Card>
          <CardHeader
            title="Outcome mix"
            description="Where this window's requests ended up"
          />
          <CardBody>
            {dashboard.loading ? (
              <div className="h-60 animate-pulse rounded bg-slate-100" />
            ) : (
              <RankedBars
                rows={outcomeRows}
                emptyLabel="No requests in this period"
                valueFormatter={(value) => value}
              />
            )}
          </CardBody>
        </Card>
      </div>

      <div className="mt-4 grid gap-4 lg:grid-cols-3">
        <Card>
          <CardHeader title="Quoted value by month" description="Net of discount" />
          <CardBody>
            {dashboard.loading ? (
              <div className="h-52 animate-pulse rounded bg-slate-100" />
            ) : revenue.length === 0 ? (
              <EmptyState icon={TrendingUp} title="No quotations issued yet" />
            ) : (
              <ResponsiveContainer width="100%" height={200}>
                <BarChart
                  data={revenue}
                  margin={{ top: 6, right: 10, left: -6, bottom: 0 }}
                >
                  <CartesianGrid {...GRID_PROPS} vertical={false} />
                  <XAxis dataKey="month" tickFormatter={chartMonth} {...X_AXIS_PROPS} />
                  <YAxis
                    tickFormatter={(value) => formatMoneyCompact(value)}
                    width={56}
                    {...Y_AXIS_PROPS}
                  />
                  <Tooltip
                    content={
                      <ChartTooltip
                        labelFormatter={chartMonth}
                        valueFormatter={(value) => formatMoney(value)}
                      />
                    }
                    cursor={{ fill: 'rgba(42,120,214,0.06)' }}
                  />
                  <Bar
                    dataKey="quoted_value"
                    name="Quoted value"
                    fill={SERIES[0]}
                    radius={BAR_RADIUS}
                    maxBarSize={44}
                  />
                </BarChart>
              </ResponsiveContainer>
            )}
          </CardBody>
        </Card>

        <Card className="lg:col-span-2">
          <CardHeader
            title="Workflow step timings"
            description="Average duration of each pipeline step, from the stored execution traces"
            icon={Gauge}
          />
          <CardBody>
            {dashboard.loading ? (
              <div className="h-52 animate-pulse rounded bg-slate-100" />
            ) : !workflowPerf?.steps?.length ? (
              <EmptyState icon={Gauge} title="No executions recorded in this window" />
            ) : (
              <>
                <div className="mb-3 flex flex-wrap gap-x-5 gap-y-1 text-[12.5px] text-slate-600">
                  <span>
                    <span className="font-semibold text-navy-800">
                      {workflowPerf.total_executions}
                    </span>{' '}
                    executions
                  </span>
                  <span>
                    <span className="font-semibold text-navy-800">
                      {workflowPerf.average_duration_ms} ms
                    </span>{' '}
                    average end to end
                  </span>
                  <span>
                    <span className="font-semibold text-navy-800">
                      {formatPercent(workflowPerf.straight_through_percent)}
                    </span>{' '}
                    straight through
                  </span>
                </div>

                <RankedBars
                  rows={workflowPerf.steps.map((step) => ({
                    key: step.step,
                    label: humanise(step.step),
                    value: step.average_duration_ms,
                    hint:
                      step.failures > 0
                        ? `${step.failures} failure${step.failures === 1 ? '' : 's'} across ${step.executions} runs`
                        : null,
                  }))}
                  valueFormatter={(value) => `${value} ms`}
                />

                {/* Failures carry an icon and a number, never colour alone. */}
                {workflowPerf.steps.some((step) => step.failures > 0) ? (
                  <div className="mt-3 flex flex-wrap items-center gap-2 border-t border-slate-100 pt-3">
                    <span className="text-[12px] text-slate-500">Step failures:</span>
                    {workflowPerf.steps
                      .filter((step) => step.failures > 0)
                      .map((step) => (
                        <Badge key={step.step} tone="danger" size="sm" icon={XCircle}>
                          {humanise(step.step)} · {step.failures}
                        </Badge>
                      ))}
                  </div>
                ) : null}
              </>
            )}
          </CardBody>
        </Card>
      </div>

      <div className="mt-4 grid gap-4 lg:grid-cols-3">
        <Card>
          <CardHeader
            title="Why requests escalate"
            description="Rules that sent work to a manager"
            icon={TriangleAlert}
          />
          <CardBody>
            {dashboard.loading ? (
              <div className="h-40 animate-pulse rounded bg-slate-100" />
            ) : (
              <RankedBars
                rows={exceptionRows}
                emptyLabel="Every request stayed within policy"
              />
            )}
          </CardBody>
        </Card>

        <Card className="lg:col-span-2">
          <CardHeader
            title="Most requested products"
            description="By quoted value in the reporting window"
            icon={FileText}
          />
          <Table
            columns={[
              {
                key: 'sku',
                header: 'Product',
                render: (row) => (
                  <div>
                    <p className="text-[13px] font-medium text-slate-800">{row.name}</p>
                    <p className="font-mono text-[11.5px] text-slate-500">{row.sku}</p>
                  </div>
                ),
              },
              {
                key: 'quantity',
                header: 'Units',
                align: 'right',
                render: (row) => <span className="tnum">{row.quantity}</span>,
              },
              {
                key: 'quotations',
                header: 'Quotations',
                align: 'right',
                render: (row) => <span className="tnum">{row.quotations}</span>,
              },
              {
                key: 'value',
                header: 'Value',
                align: 'right',
                render: (row) => (
                  <span className="tnum font-medium text-slate-800">
                    {formatMoney(row.value)}
                  </span>
                ),
              },
            ]}
            rows={(data?.top_products ?? []).slice(0, 6)}
            loading={dashboard.loading}
            error={dashboard.error}
            empty={
              <EmptyState icon={FileText} title="No products quoted in this window" />
            }
          />
        </Card>
      </div>

      <Card className="mt-4">
        <CardHeader
          title="Awaiting your decision"
          description="Requests the rule engine escalated"
          icon={ClipboardCheck}
          action={
            <Button
              variant="ghost"
              size="sm"
              iconRight={ArrowRight}
              onClick={() => navigate('/approvals')}
            >
              View queue
            </Button>
          }
        />
        <Table
          columns={[
            {
              key: 'request_number',
              header: 'Request',
              render: (row) => (
                <span className="font-mono text-[12.5px] font-medium text-slate-800">
                  {row.request_number}
                </span>
              ),
            },
            { key: 'customer_name', header: 'Customer' },
            {
              key: 'exceptions',
              header: 'Exceptions',
              render: (row) => (
                <div className="flex flex-wrap gap-1">
                  {(row.exceptions ?? []).map((exception, index) => (
                    <Badge
                      key={index}
                      tone={exceptionInfo(exception.type).tone}
                      size="sm"
                    >
                      {exceptionInfo(exception.type).label}
                    </Badge>
                  ))}
                </div>
              ),
            },
            {
              key: 'requested_discount_percent',
              header: 'Discount asked',
              align: 'right',
              render: (row) => (
                <span className="tnum">
                  {formatPercent(row.requested_discount_percent)}
                </span>
              ),
            },
            {
              key: 'requested_amount',
              header: 'Amount',
              align: 'right',
              render: (row) => (
                <span className="tnum font-medium text-slate-800">
                  {formatMoney(row.requested_amount)}
                </span>
              ),
            },
            {
              key: 'sla_due_at',
              header: 'SLA',
              render: (row) => {
                const overdue = row.sla_due_at && new Date(row.sla_due_at) < new Date()
                return (
                  <span
                    className={`text-[12.5px] ${
                      overdue ? 'font-medium text-rose-600' : 'text-slate-500'
                    }`}
                  >
                    {overdue ? 'Overdue' : `due ${formatRelative(row.sla_due_at)}`}
                  </span>
                )
              },
            },
          ]}
          rows={pending.data?.items ?? []}
          loading={pending.loading}
          error={pending.error}
          onRowClick={(row) => navigate(`/approvals/${row.id}`)}
          empty={
            <EmptyState
              icon={ClipboardCheck}
              title="Queue is clear"
              description="There are no requests waiting for a decision."
            />
          }
        />
      </Card>
    </>
  )
}
