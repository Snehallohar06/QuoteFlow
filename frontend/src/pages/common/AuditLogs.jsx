import { useState } from 'react'
import { Lock, RefreshCw, ScrollText } from 'lucide-react'

import { useAsync } from '../../hooks/useAsync'
import * as auditApi from '../../api/audit'
import { PageHeader } from '../../components/layout/PageHeader'
import { Button } from '../../components/ui/Button'
import { Card, CardBody } from '../../components/ui/Card'
import { Badge } from '../../components/ui/Badge'
import { Modal } from '../../components/ui/Modal'
import {
  EmptyState,
  NoResultsState,
  Pagination,
  Table,
} from '../../components/ui/Table'
import { FilterSelect, Toolbar } from '../../components/ui/Toolbar'
import { formatDateTime, formatRelative, humanise } from '../../lib/format'

const ACTION_OPTIONS = auditApi.AUDIT_ACTIONS.map((action) => ({
  value: action,
  label: humanise(action),
}))

const ENTITY_OPTIONS = auditApi.AUDIT_ENTITY_TYPES.map((type) => ({
  value: type,
  label: humanise(type),
}))

/** Actions whose colour signals a decision rather than a routine write. */
const ACTION_TONES = {
  APPROVAL_DECIDED: 'warning',
  QUOTATION_GENERATED: 'success',
  QUOTATION_VERIFIED: 'info',
  SETTINGS_UPDATED: 'warning',
  PRODUCT_DELETED: 'danger',
  REQUEST_CANCELLED: 'danger',
  USER_LOGGED_IN: 'neutral',
}

function renderValue(value) {
  if (value === null || value === undefined) return <span className="text-slate-400">—</span>
  if (typeof value === 'boolean') return value ? 'Yes' : 'No'
  if (typeof value === 'object') return JSON.stringify(value)
  return String(value)
}

function ChangeTable({ changes }) {
  const entries = Object.entries(changes ?? {})
  if (entries.length === 0) return null

  return (
    <table className="w-full text-[12.5px]">
      <thead>
        <tr className="border-b border-slate-200 text-left text-[11px] uppercase tracking-wide text-slate-500">
          <th className="py-1.5 pr-3 font-semibold">Field</th>
          <th className="py-1.5 pr-3 font-semibold">Before</th>
          <th className="py-1.5 font-semibold">After</th>
        </tr>
      </thead>
      <tbody className="divide-y divide-slate-100">
        {entries.map(([field, change]) => (
          <tr key={field}>
            <td className="py-1.5 pr-3 font-medium text-slate-700">{humanise(field)}</td>
            <td className="py-1.5 pr-3 text-slate-500">
              {renderValue(change?.before)}
            </td>
            <td className="py-1.5 font-medium text-slate-800">
              {renderValue(change?.after)}
            </td>
          </tr>
        ))}
      </tbody>
    </table>
  )
}

export function AuditLogs() {
  const [action, setAction] = useState(undefined)
  const [entityType, setEntityType] = useState(undefined)
  const [page, setPage] = useState(1)
  const [selected, setSelected] = useState(null)

  const logs = useAsync(
    () =>
      auditApi.listAuditLogs({
        page,
        page_size: 25,
        action,
        entity_type: entityType,
      }),
    [page, action, entityType]
  )

  const activeFilters = [action, entityType].filter(Boolean).length

  function clearFilters() {
    setAction(undefined)
    setEntityType(undefined)
    setPage(1)
  }

  return (
    <>
      <PageHeader
        title="Audit logs"
        description="Append-only record of every state change in the system."
        actions={
          <Button variant="secondary" icon={RefreshCw} onClick={logs.reload}>
            Refresh
          </Button>
        }
      />

      <Card className="mb-4 border-navy-200 bg-navy-50/50">
        <CardBody>
          <div className="flex items-start gap-2.5">
            <Lock
              size={16}
              className="mt-0.5 shrink-0 text-navy-600"
              aria-hidden="true"
            />
            <p className="text-[12.5px] leading-relaxed text-navy-900/80">
              This trail is written once and read thereafter. The backend exposes no
              endpoint that edits or deletes an audit entry, so what you see here is what
              was recorded at the time — including the actor, their role, their IP address
              and a field-level diff of what changed.
            </p>
          </div>
        </CardBody>
      </Card>

      <Card>
        <Toolbar activeCount={activeFilters} onClear={clearFilters}>
          <FilterSelect
            value={action}
            onChange={(value) => {
              setAction(value)
              setPage(1)
            }}
            options={ACTION_OPTIONS}
            placeholder="All actions"
            label="Action"
          />
          <FilterSelect
            value={entityType}
            onChange={(value) => {
              setEntityType(value)
              setPage(1)
            }}
            options={ENTITY_OPTIONS}
            placeholder="All entity types"
            label="Entity type"
          />
          <span className="ml-auto text-[12.5px] text-slate-500">
            {logs.loading ? 'Loading…' : `${logs.data?.meta?.total ?? 0} entry(ies)`}
          </span>
        </Toolbar>

        <Table
          columns={[
            {
              key: 'created_at',
              header: 'When',
              render: (row) => (
                <div title={formatDateTime(row.created_at)}>
                  <p className="text-[12.5px] text-slate-700">
                    {formatRelative(row.created_at)}
                  </p>
                  <p className="text-[11px] text-slate-400">
                    {formatDateTime(row.created_at)}
                  </p>
                </div>
              ),
            },
            {
              key: 'action',
              header: 'Action',
              render: (row) => (
                <Badge tone={ACTION_TONES[row.action] ?? 'info'} size="sm">
                  {humanise(row.action)}
                </Badge>
              ),
            },
            {
              key: 'summary',
              header: 'Summary',
              render: (row) => (
                <span className="block max-w-lg text-[12.5px] leading-snug text-slate-700">
                  {row.summary}
                </span>
              ),
            },
            {
              key: 'actor',
              header: 'Actor',
              render: (row) => (
                <div className="max-w-48">
                  <p className="truncate text-[12.5px] text-slate-700">
                    {row.actor_email ?? 'system'}
                  </p>
                  <p className="text-[11px] text-slate-500">
                    {row.actor_role ? humanise(row.actor_role) : '—'}
                  </p>
                </div>
              ),
            },
            {
              key: 'entity',
              header: 'Entity',
              render: (row) => (
                <span className="text-[12px] text-slate-500">
                  {humanise(row.entity_type)}
                </span>
              ),
            },
            {
              key: 'detail',
              header: '',
              align: 'right',
              render: (row) => {
                const hasDetail =
                  Object.keys(row.changes ?? {}).length > 0 ||
                  Object.keys(row.metadata ?? {}).length > 0
                return hasDetail ? (
                  <Button
                    variant="ghost"
                    size="sm"
                    onClick={(event) => {
                      event.stopPropagation()
                      setSelected(row)
                    }}
                  >
                    Detail
                  </Button>
                ) : null
              },
            },
          ]}
          rows={logs.data?.items ?? []}
          loading={logs.loading}
          error={logs.error}
          onRowClick={(row) => setSelected(row)}
          empty={
            activeFilters > 0 ? (
              <NoResultsState onClear={clearFilters} />
            ) : (
              <EmptyState
                icon={ScrollText}
                title="No audit entries yet"
                description="Activity is recorded here as soon as anything happens in the system."
              />
            )
          }
        />

        <Pagination meta={logs.data?.meta} onPageChange={setPage} />
      </Card>

      <Modal
        open={Boolean(selected)}
        onClose={() => setSelected(null)}
        title={selected ? humanise(selected.action) : ''}
        description={selected?.summary}
        size="lg"
        footer={
          <Button variant="secondary" onClick={() => setSelected(null)}>
            Close
          </Button>
        }
      >
        {selected ? (
          <div className="space-y-4">
            <dl className="grid gap-x-6 gap-y-1.5 sm:grid-cols-2">
              <div className="flex justify-between gap-3">
                <dt className="text-[12px] text-slate-500">Recorded</dt>
                <dd className="text-[12.5px] font-medium text-slate-800">
                  {formatDateTime(selected.created_at)}
                </dd>
              </div>
              <div className="flex justify-between gap-3">
                <dt className="text-[12px] text-slate-500">Entity</dt>
                <dd className="text-[12.5px] font-medium text-slate-800">
                  {humanise(selected.entity_type)}
                </dd>
              </div>
              <div className="flex justify-between gap-3">
                <dt className="text-[12px] text-slate-500">Actor</dt>
                <dd className="truncate text-[12.5px] font-medium text-slate-800">
                  {selected.actor_email ?? 'system'}
                </dd>
              </div>
              <div className="flex justify-between gap-3">
                <dt className="text-[12px] text-slate-500">Role</dt>
                <dd className="text-[12.5px] font-medium text-slate-800">
                  {selected.actor_role ? humanise(selected.actor_role) : '—'}
                </dd>
              </div>
              {selected.entity_id ? (
                <div className="flex justify-between gap-3 sm:col-span-2">
                  <dt className="text-[12px] text-slate-500">Entity ID</dt>
                  <dd className="font-mono text-[11.5px] text-slate-700">
                    {selected.entity_id}
                  </dd>
                </div>
              ) : null}
              {selected.ip_address ? (
                <div className="flex justify-between gap-3">
                  <dt className="text-[12px] text-slate-500">IP address</dt>
                  <dd className="font-mono text-[11.5px] text-slate-700">
                    {selected.ip_address}
                  </dd>
                </div>
              ) : null}
            </dl>

            {Object.keys(selected.changes ?? {}).length > 0 ? (
              <div>
                <p className="mb-1.5 text-[11.5px] font-semibold uppercase tracking-wide text-slate-500">
                  Field changes
                </p>
                <ChangeTable changes={selected.changes} />
              </div>
            ) : null}

            {Object.keys(selected.metadata ?? {}).length > 0 ? (
              <div>
                <p className="mb-1.5 text-[11.5px] font-semibold uppercase tracking-wide text-slate-500">
                  Metadata
                </p>
                <dl className="grid gap-x-6 gap-y-1 sm:grid-cols-2">
                  {Object.entries(selected.metadata).map(([key, value]) => (
                    <div key={key} className="flex justify-between gap-3">
                      <dt className="text-[12px] text-slate-500">{humanise(key)}</dt>
                      <dd className="min-w-0 break-words text-right text-[12.5px] font-medium text-slate-800">
                        {renderValue(value)}
                      </dd>
                    </div>
                  ))}
                </dl>
              </div>
            ) : null}

            {selected.user_agent ? (
              <p className="break-all border-t border-slate-100 pt-3 font-mono text-[10.5px] leading-relaxed text-slate-400">
                {selected.user_agent}
              </p>
            ) : null}
          </div>
        ) : null}
      </Modal>
    </>
  )
}
