import { useState } from 'react'
import {
  BarChart3,
  ClipboardCheck,
  ClipboardList,
  Download,
  FileText,
  Gauge,
  Percent,
  RefreshCw,
  TrendingUp,
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

import { useToast } from '../../context/ToastContext'
import { useAsync } from '../../hooks/useAsync'
import * as analyticsApi from '../../api/analytics'
import { PageHeader } from '../../components/layout/PageHeader'
import { Button } from '../../components/ui/Button'
import { Card, CardBody, CardHeader, StatCard } from '../../components/ui/Card'
import { Badge } from '../../components/ui/Badge'
import { ChartTooltip, RankedBars } from '../../components/ui/ChartTooltip'
import { EmptyState, Table } from '../../components/ui/Table'
import { FilterSelect } from '../../components/ui/Toolbar'
import {
  formatHours,
  formatMoney,
  formatMoneyCompact,
  formatNumber,
  formatPercent,
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

const WINDOW_OPTIONS = [
  { value: '7', label: 'Last 7 days' },
  { value: '30', label: 'Last 30 days' },
  { value: '90', label: 'Last 90 days' },
  { value: '180', label: 'Last 6 months' },
  { value: '365', label: 'Last year' },
]

/** Turns the dashboard payload into a CSV a manager can open in a spreadsheet. */
function toCsv(dashboard) {
  const rows = [['Metric', 'Value']]
  const overview = dashboard.overview
  const pairs = [
    ['Reporting window (days)', overview.period_days],
    ['Total requests', overview.total_requests],
    ['Open requests', overview.open_requests],
    ['Approved requests', overview.approved_requests],
    ['Rejected requests', overview.rejected_requests],
    ['Approval rate (%)', overview.approval_rate_percent],
    ['Quotations issued', overview.quotations_issued],
    ['Quoted value', overview.quoted_value],
    ['Average quotation value', overview.average_quotation_value],
    ['Total discount given', overview.total_discount_given],
    ['Discount rate (%)', overview.discount_rate_percent],
    ['Auto-approved quotations', overview.auto_approved_quotations],
    ['Automation rate (%)', overview.automation_rate_percent],
    ['Pending approvals', overview.pending_approvals],
    ['Overdue approvals', overview.overdue_approvals],
    ['Live quotations', overview.live_quotations],
    ['Average approval turnaround (hours)',
      dashboard.approval_performance.average_turnaround_hours],
    ['SLA compliance (%)', dashboard.approval_performance.sla_compliance_percent],
  ]
  rows.push(...pairs.map(([label, value]) => [label, value]))

  rows.push([], ['Requests by status', 'Count'])
  for (const [status, count] of Object.entries(overview.requests_by_status ?? {})) {
    rows.push([requestStatusInfo(status).label, count])
  }

  rows.push([], ['Most requested products', 'Units', 'Quotations', 'Value'])
  for (const product of dashboard.top_products ?? []) {
    rows.push([
      `${product.sku} ${product.name}`,
      product.quantity,
      product.quotations,
      product.value,
    ])
  }

  rows.push([], ['Monthly quoted value', 'Quotations', 'Value', 'Discount'])
  for (const month of dashboard.revenue_trend ?? []) {
    rows.push([month.month, month.quotations, month.quoted_value, month.discount])
  }

  return rows
    .map((row) =>
      row
        .map((cell) => {
          const text = cell === undefined || cell === null ? '' : String(cell)
          return /[",\n]/.test(text) ? `"${text.replace(/"/g, '""')}"` : text
        })
        .join(',')
    )
    .join('\n')
}

export function AnalyticsDashboard() {
  const toast = useToast()
  const [days, setDays] = useState('30')

  const dashboard = useAsync(() => analyticsApi.getDashboard(Number(days)), [days])

  const data = dashboard.data
  const overview = data?.overview
  const approvalPerf = data?.approval_performance
  const workflowPerf = data?.workflow_performance

  function exportCsv() {
    if (!data) return
    try {
      const blob = new Blob([toCsv(data)], { type: 'text/csv;charset=utf-8' })
      const url = URL.createObjectURL(blob)
      const link = document.createElement('a')
      link.href = url
      link.download = `quoteflow-analytics-${days}d.csv`
      document.body.appendChild(link)
      link.click()
      link.remove()
      setTimeout(() => URL.revokeObjectURL(url), 1000)
      toast.success('Export ready', `quoteflow-analytics-${days}d.csv`)
    } catch {
      toast.error('Could not export', 'Your browser blocked the download.')
    }
  }

  const outcomeRows = Object.entries(overview?.requests_by_status ?? {})
    .map(([status, count]) => ({
      key: status,
      label: requestStatusInfo(status).label,
      value: count,
    }))
    .sort((a, b) => b.value - a.value)

  const exceptionRows = (data?.exception_breakdown ?? []).map((row) => ({
    key: row.type,
    label: exceptionInfo(row.type).label,
    value: row.count,
    hint: `${formatPercent(row.share_percent)} of all exceptions`,
  }))

  return (
    <>
      <PageHeader
        title="Analytics"
        description="Every figure is aggregated from the live database — requests, quotations, approvals and workflow executions."
        actions={
          <>
            <FilterSelect
              value={days}
              onChange={(value) => setDays(value || '30')}
              options={WINDOW_OPTIONS}
              placeholder="Last 30 days"
              label="Reporting window"
            />
            <Button variant="secondary" icon={RefreshCw} onClick={dashboard.reload}>
              Refresh
            </Button>
            <Button
              variant="secondary"
              icon={Download}
              disabled={!data}
              onClick={exportCsv}
            >
              Export CSV
            </Button>
          </>
        }
      />

      {/* ---- Headline figures ------------------------------------------- */}
      <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
        <StatCard
          label="Total requests"
          value={formatNumber(overview?.total_requests ?? 0)}
          icon={ClipboardList}
          tone="navy"
          loading={dashboard.loading}
          hint={`${overview?.open_requests ?? 0} still open`}
        />
        <StatCard
          label="Pending requests"
          value={formatNumber(overview?.pending_approvals ?? 0)}
          icon={ClipboardCheck}
          tone="amber"
          loading={dashboard.loading}
          hint={
            overview?.overdue_approvals
              ? `${overview.overdue_approvals} past SLA`
              : 'All within SLA'
          }
        />
        <StatCard
          label="Approved quotations"
          value={formatNumber(overview?.quotations_issued ?? 0)}
          icon={FileText}
          tone="emerald"
          loading={dashboard.loading}
          hint={`${overview?.live_quotations ?? 0} currently valid`}
        />
        <StatCard
          label="Rejected quotations"
          value={formatNumber(overview?.rejected_requests ?? 0)}
          icon={BarChart3}
          tone={overview?.rejected_requests ? 'rose' : 'slate'}
          loading={dashboard.loading}
          hint={`${formatPercent(overview?.approval_rate_percent ?? 0)} approval rate`}
        />
      </div>

      <div className="mt-4 grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
        <StatCard
          label="Quoted value"
          value={formatMoney(overview?.quoted_value ?? 0)}
          icon={TrendingUp}
          tone="blue"
          loading={dashboard.loading}
          hint={`avg ${formatMoney(overview?.average_quotation_value ?? 0)}`}
        />
        <StatCard
          label="Average processing time"
          value={formatHours(approvalPerf?.average_turnaround_hours ?? 0)}
          icon={Gauge}
          tone="slate"
          loading={dashboard.loading}
          hint={`longest ${formatHours(approvalPerf?.longest_turnaround_hours ?? 0)}`}
        />
        <StatCard
          label="Discount given"
          value={formatMoney(overview?.total_discount_given ?? 0)}
          icon={Percent}
          tone="slate"
          loading={dashboard.loading}
          hint={`${formatPercent(overview?.discount_rate_percent ?? 0)} of gross value`}
        />
        <StatCard
          label="Automation rate"
          value={formatPercent(overview?.automation_rate_percent ?? 0)}
          icon={Gauge}
          tone="emerald"
          loading={dashboard.loading}
          hint={`${overview?.auto_approved_quotations ?? 0} quoted with no manual step`}
        />
      </div>

      {/* ---- Volume over time ------------------------------------------- */}
      <Card className="mt-4">
        <CardHeader
          title="Requests submitted per day"
          description="Total quotation requests received across the reporting window"
        />
        <CardBody>
          {dashboard.loading ? (
            <div className="h-64 animate-pulse rounded bg-slate-100" />
          ) : !data?.request_trend?.length ? (
            <EmptyState
              icon={BarChart3}
              title="No requests in this window"
              description="Widen the reporting period, or submit a request to see it appear here."
            />
          ) : (
            <ResponsiveContainer width="100%" height={250}>
              <AreaChart
                data={data.request_trend}
                margin={{ top: 6, right: 12, left: -16, bottom: 0 }}
              >
                <defs>
                  <linearGradient id="analyticsVolume" x1="0" y1="0" x2="0" y2="1">
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
                  fill="url(#analyticsVolume)"
                  activeDot={{ r: 4.5, strokeWidth: 2, stroke: '#ffffff' }}
                />
              </AreaChart>
            </ResponsiveContainer>
          )}
        </CardBody>
      </Card>

      {/* ---- Composition ------------------------------------------------ */}
      <div className="mt-4 grid gap-4 lg:grid-cols-2">
        <Card>
          <CardHeader
            title="Request outcomes"
            description="Where this window's requests ended up"
          />
          <CardBody>
            {dashboard.loading ? (
              <div className="h-48 animate-pulse rounded bg-slate-100" />
            ) : (
              <RankedBars rows={outcomeRows} emptyLabel="No requests in this window" />
            )}
          </CardBody>
        </Card>

        <Card>
          <CardHeader
            title="Why requests escalate"
            description="The rules that sent work to a manager"
          />
          <CardBody>
            {dashboard.loading ? (
              <div className="h-48 animate-pulse rounded bg-slate-100" />
            ) : (
              <RankedBars
                rows={exceptionRows}
                emptyLabel="Every request stayed within policy"
              />
            )}
          </CardBody>
        </Card>
      </div>

      {/* ---- Monthly quotation volume ----------------------------------- */}
      <div className="mt-4 grid gap-4 lg:grid-cols-2">
        <Card>
          <CardHeader
            title="Monthly quotation volume"
            description="Number of quotations issued per month"
          />
          <CardBody>
            {dashboard.loading ? (
              <div className="h-52 animate-pulse rounded bg-slate-100" />
            ) : !data?.revenue_trend?.length ? (
              <EmptyState icon={FileText} title="No quotations issued yet" />
            ) : (
              <ResponsiveContainer width="100%" height={210}>
                <BarChart
                  data={data.revenue_trend}
                  margin={{ top: 6, right: 10, left: -18, bottom: 0 }}
                >
                  <CartesianGrid {...GRID_PROPS} vertical={false} />
                  <XAxis dataKey="month" tickFormatter={chartMonth} {...X_AXIS_PROPS} />
                  <YAxis allowDecimals={false} width={38} {...Y_AXIS_PROPS} />
                  <Tooltip
                    content={<ChartTooltip labelFormatter={chartMonth} />}
                    cursor={{ fill: 'rgba(42,120,214,0.06)' }}
                  />
                  <Bar
                    dataKey="quotations"
                    name="Quotations"
                    fill={SERIES[0]}
                    radius={BAR_RADIUS}
                    maxBarSize={44}
                  />
                </BarChart>
              </ResponsiveContainer>
            )}
          </CardBody>
        </Card>

        <Card>
          <CardHeader
            title="Monthly quoted value"
            description="Net of discount, per month"
          />
          <CardBody>
            {dashboard.loading ? (
              <div className="h-52 animate-pulse rounded bg-slate-100" />
            ) : !data?.revenue_trend?.length ? (
              <EmptyState icon={TrendingUp} title="No quotations issued yet" />
            ) : (
              <ResponsiveContainer width="100%" height={210}>
                <BarChart
                  data={data.revenue_trend}
                  margin={{ top: 6, right: 10, left: -4, bottom: 0 }}
                >
                  <CartesianGrid {...GRID_PROPS} vertical={false} />
                  <XAxis dataKey="month" tickFormatter={chartMonth} {...X_AXIS_PROPS} />
                  <YAxis
                    tickFormatter={(value) => formatMoneyCompact(value)}
                    width={58}
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
      </div>

      {/* ---- Tables ----------------------------------------------------- */}
      <div className="mt-4 grid gap-4 lg:grid-cols-2">
        <Card>
          <CardHeader
            title="Most requested products"
            description="Ranked by quoted value"
            icon={FileText}
          />
          <Table
            columns={[
              {
                key: 'sku',
                header: 'Product',
                render: (row) => (
                  <div className="max-w-56">
                    <p className="truncate text-[13px] font-medium text-slate-800">
                      {row.name}
                    </p>
                    <p className="font-mono text-[11.5px] text-slate-500">{row.sku}</p>
                  </div>
                ),
              },
              {
                key: 'quantity',
                header: 'Units',
                align: 'right',
                render: (row) => <span className="tnum">{formatNumber(row.quantity)}</span>,
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
            rows={data?.top_products ?? []}
            loading={dashboard.loading}
            error={dashboard.error}
            empty={<EmptyState icon={FileText} title="No products quoted yet" />}
          />
        </Card>

        <Card>
          <CardHeader
            title="Highest-value customers"
            description="Ranked by quoted value in this window"
          />
          <Table
            columns={[
              {
                key: 'customer_name',
                header: 'Customer',
                render: (row) => (
                  <span className="block max-w-56 truncate text-[13px] text-slate-800">
                    {row.customer_name}
                  </span>
                ),
              },
              {
                key: 'quotations',
                header: 'Quotations',
                align: 'right',
                render: (row) => <span className="tnum">{row.quotations}</span>,
              },
              {
                key: 'discount',
                header: 'Discount',
                align: 'right',
                render: (row) => (
                  <span className="tnum text-emerald-700">
                    {formatMoney(row.discount)}
                  </span>
                ),
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
            rows={data?.top_customers ?? []}
            loading={dashboard.loading}
            error={dashboard.error}
            empty={<EmptyState title="No customer activity yet" />}
          />
        </Card>
      </div>

      {/* ---- Process performance ---------------------------------------- */}
      <div className="mt-4 grid gap-4 lg:grid-cols-3">
        <Card>
          <CardHeader
            title="Approval performance"
            description="Turnaround and SLA compliance"
            icon={ClipboardCheck}
          />
          <CardBody>
            <dl className="space-y-2">
              {[
                ['Decisions recorded', formatNumber(approvalPerf?.decided ?? 0)],
                ['Approved', formatNumber(approvalPerf?.approved ?? 0)],
                ['Rejected', formatNumber(approvalPerf?.rejected ?? 0)],
                [
                  'Average turnaround',
                  formatHours(approvalPerf?.average_turnaround_hours ?? 0),
                ],
                [
                  'Longest turnaround',
                  formatHours(approvalPerf?.longest_turnaround_hours ?? 0),
                ],
                ['Within SLA', formatNumber(approvalPerf?.within_sla ?? 0)],
              ].map(([label, value]) => (
                <div key={label} className="flex items-baseline justify-between gap-4">
                  <dt className="text-[13px] text-slate-500">{label}</dt>
                  <dd className="tnum text-[13.5px] font-medium text-slate-800">
                    {value}
                  </dd>
                </div>
              ))}
              <div className="flex items-baseline justify-between gap-4 border-t border-slate-200 pt-2">
                <dt className="text-[13.5px] font-semibold text-navy-800">
                  SLA compliance
                </dt>
                <dd className="tnum text-[16px] font-semibold text-navy-800">
                  {formatPercent(approvalPerf?.sla_compliance_percent ?? 0)}
                </dd>
              </div>
            </dl>
          </CardBody>
        </Card>

        <Card className="lg:col-span-2">
          <CardHeader
            title="Workflow step timings"
            description="Average duration per pipeline step, from the stored execution traces"
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
                      {formatNumber(workflowPerf.total_executions)}
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
                        ? `${step.failures} failure(s) across ${step.executions} runs`
                        : null,
                  }))}
                  valueFormatter={(value) => `${value} ms`}
                />

                <div className="mt-3 flex flex-wrap items-center gap-2 border-t border-slate-100 pt-3">
                  <span className="text-[12px] text-slate-500">Outcomes:</span>
                  {Object.entries(workflowPerf.by_outcome ?? {}).map(
                    ([outcome, count]) => (
                      <Badge key={outcome} tone="neutral" size="sm">
                        {humanise(outcome)} · {count}
                      </Badge>
                    )
                  )}
                </div>
              </>
            )}
          </CardBody>
        </Card>
      </div>
    </>
  )
}
