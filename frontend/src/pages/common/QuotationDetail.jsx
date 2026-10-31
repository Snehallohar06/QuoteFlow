import { useState } from 'react'
import { useNavigate, useParams } from 'react-router-dom'
import {
  Building2,
  Copy,
  Download,
  ExternalLink,
  FileCheck2,
  ShieldCheck,
  Timer,
  User,
} from 'lucide-react'

import { useAuth } from '../../context/AuthContext'
import { useToast } from '../../context/ToastContext'
import { useAsync } from '../../hooks/useAsync'
import * as quotationsApi from '../../api/quotations'
import { PageHeader } from '../../components/layout/PageHeader'
import { Button } from '../../components/ui/Button'
import {
  Card,
  CardBody,
  CardHeader,
  DetailList,
  DetailRow,
} from '../../components/ui/Card'
import { Badge, StatusBadge } from '../../components/ui/Badge'
import { FilterSelect } from '../../components/ui/Toolbar'
import { ErrorState, PageLoader } from '../../components/ui/Table'
import {
  LineItemsTable,
  PricingSummary,
} from '../../components/workflow/PricingBreakdown'
import { daysUntil, formatDate, formatDateTime } from '../../lib/format'
import {
  QUOTATION_STATUS_OPTIONS,
  quotationStatusInfo,
  verificationInfo,
} from '../../lib/status'

function PartyBlock({ title, party, icon: Icon }) {
  return (
    <div>
      <p className="flex items-center gap-1.5 text-[11.5px] font-semibold uppercase tracking-wide text-slate-500">
        <Icon size={13} aria-hidden="true" />
        {title}
      </p>
      <p className="mt-1.5 text-[13.5px] font-semibold text-navy-800">{party.name}</p>
      {party.code ? (
        <p className="font-mono text-[11.5px] text-slate-500">{party.code}</p>
      ) : null}
      {party.contact_name ? (
        <p className="mt-1 text-[12.5px] text-slate-600">Attn: {party.contact_name}</p>
      ) : null}
      {party.address_lines?.map((line, index) => (
        <p key={index} className="text-[12.5px] leading-snug text-slate-600">
          {line}
        </p>
      ))}
      {party.email ? (
        <p className="mt-1 text-[12.5px] text-slate-600">{party.email}</p>
      ) : null}
      {party.phone ? <p className="text-[12.5px] text-slate-600">{party.phone}</p> : null}
      {party.tax_id ? (
        <p className="mt-1 font-mono text-[11.5px] text-slate-500">
          Tax ID {party.tax_id}
        </p>
      ) : null}
    </div>
  )
}

export function QuotationDetail() {
  const { id } = useParams()
  const { isManager } = useAuth()
  const toast = useToast()
  const navigate = useNavigate()

  const quotation = useAsync(() => quotationsApi.getQuotation(id), [id])
  const [verification, setVerification] = useState(null)
  const [verifying, setVerifying] = useState(false)
  const [downloading, setDownloading] = useState(false)
  const [statusBusy, setStatusBusy] = useState(false)

  const data = quotation.data

  async function download() {
    setDownloading(true)
    try {
      await quotationsApi.downloadQuotationPdf(id, data.quotation_number)
      toast.success('Download started', `${data.quotation_number}.pdf`)
      quotation.reload()
    } catch (error) {
      toast.fromError(error, 'Could not download the quotation')
    } finally {
      setDownloading(false)
    }
  }

  async function openPdf() {
    try {
      await quotationsApi.openQuotationPdf(id)
      quotation.reload()
    } catch (error) {
      toast.fromError(error, 'Could not open the quotation')
    }
  }

  /**
   * Runs the public verification endpoint — the same unauthenticated call a
   * recipient of the PDF would make. This is what produces the spec's
   * "Verification Failed" state when the stored amounts no longer match.
   */
  async function verify() {
    setVerifying(true)
    try {
      const result = await quotationsApi.verifyQuotation(data.verification_code)
      setVerification(result)
      if (result.valid) {
        toast.success(
          'Verified',
          result.expired
            ? 'Authentic, but the quotation has passed its validity date.'
            : 'The stored amounts match the digest issued with this document.'
        )
      } else {
        toast.error('Verification failed', result.reason)
      }
    } catch (error) {
      toast.fromError(error, 'Could not verify the quotation')
    } finally {
      setVerifying(false)
    }
  }

  async function copyCode() {
    try {
      await navigator.clipboard.writeText(data.verification_code)
      toast.success('Code copied', data.verification_code)
    } catch {
      toast.warning('Could not copy', 'Your browser blocked clipboard access.')
    }
  }

  async function changeStatus(newStatus) {
    if (!newStatus) return
    setStatusBusy(true)
    try {
      await quotationsApi.setQuotationStatus(id, newStatus)
      toast.success('Status updated', `Marked ${newStatus.toLowerCase()}.`)
      quotation.reload()
    } catch (error) {
      toast.fromError(error, 'Could not change the status')
    } finally {
      setStatusBusy(false)
    }
  }

  if (quotation.loading && !data) return <PageLoader label="Loading quotation" />
  if (quotation.error) {
    return (
      <Card>
        <ErrorState error={quotation.error} onRetry={quotation.reload} />
      </Card>
    )
  }
  if (!data) return null

  const days = daysUntil(data.valid_until)
  const expired = days !== null && days < 0
  const verifyState = verificationInfo(verification)

  return (
    <>
      <PageHeader
        title={data.quotation_number}
        description={`Issued to ${data.buyer.name} on ${formatDate(data.issued_at)}`}
        breadcrumbs={[
          { label: 'Quotations', to: '/quotations' },
          { label: data.quotation_number },
        ]}
        meta={
          <div className="flex flex-wrap items-center gap-1.5">
            <StatusBadge info={quotationStatusInfo(data.status)} size="lg" />
            {data.auto_approved ? (
              <Badge tone="success">Auto-approved</Badge>
            ) : (
              <Badge tone="info">Manager approved</Badge>
            )}
            {expired && data.status === 'ISSUED' ? (
              <Badge tone="danger">Past validity</Badge>
            ) : null}
          </div>
        }
        actions={
          <>
            <Button
              variant="secondary"
              icon={ShieldCheck}
              loading={verifying}
              onClick={verify}
            >
              Verify
            </Button>
            <Button variant="secondary" icon={ExternalLink} onClick={openPdf}>
              Open PDF
            </Button>
            <Button icon={Download} loading={downloading} onClick={download}>
              Download
            </Button>
          </>
        }
      />

      {verification ? (
        <Card
          className={`mb-4 ${
            verification.valid
              ? verification.expired
                ? 'border-amber-200 bg-amber-50/60'
                : 'border-emerald-200 bg-emerald-50/60'
              : 'border-rose-200 bg-rose-50/60'
          }`}
        >
          <CardBody>
            <div className="flex flex-wrap items-start justify-between gap-3">
              <div className="flex items-start gap-2.5">
                <verifyState.icon
                  size={17}
                  className={`mt-0.5 shrink-0 ${
                    verification.valid
                      ? verification.expired
                        ? 'text-amber-600'
                        : 'text-emerald-600'
                      : 'text-rose-600'
                  }`}
                  aria-hidden="true"
                />
                <div>
                  <p className="text-[13.5px] font-semibold text-slate-900">
                    {verifyState.label}
                  </p>
                  <p className="mt-0.5 text-[12.5px] leading-snug text-slate-600">
                    {verification.valid
                      ? `The amounts on record match the integrity digest issued with ${verification.quotation_number}.`
                      : verification.reason}
                  </p>
                </div>
              </div>
              <Button
                variant="ghost"
                size="sm"
                onClick={() => setVerification(null)}
              >
                Dismiss
              </Button>
            </div>
          </CardBody>
        </Card>
      ) : null}

      <div className="grid gap-4 lg:grid-cols-[1fr_340px]">
        <div className="space-y-4">
          <Card>
            <CardBody>
              <div className="grid gap-6 sm:grid-cols-2">
                <PartyBlock title="From" party={data.seller} icon={Building2} />
                <PartyBlock title="Quotation for" party={data.buyer} icon={User} />
              </div>
            </CardBody>
          </Card>

          <Card>
            <CardHeader
              title="Quoted lines"
              description="Frozen at issue — these figures cannot change"
            />
            <LineItemsTable
              items={data.items}
              currency={data.pricing.currency}
              showAvailability={false}
            />
            <div className="border-t border-slate-200">
              <PricingSummary pricing={data.pricing} />
            </div>
          </Card>

          {data.terms?.length ? (
            <Card>
              <CardHeader title="Terms and conditions" />
              <CardBody>
                <ol className="space-y-1.5">
                  {data.terms.map((term, index) => (
                    <li
                      key={index}
                      className="text-[12.5px] leading-relaxed text-slate-600"
                    >
                      {index + 1}. {term}
                    </li>
                  ))}
                </ol>
              </CardBody>
            </Card>
          ) : null}
        </div>

        <div className="space-y-4">
          <Card className="border-navy-200 bg-navy-50/50">
            <CardHeader title="Document verification" icon={ShieldCheck} />
            <CardBody>
              <p className="text-[12px] text-slate-600">
                Printed on the PDF. Anyone holding the document can check it without
                signing in.
              </p>
              <div className="mt-2.5 flex items-center gap-2">
                <code className="flex-1 rounded border border-navy-200 bg-white px-2.5 py-2 text-center font-mono text-[14px] font-semibold tracking-wider text-navy-800">
                  {data.verification_code}
                </code>
                <Button
                  variant="secondary"
                  size="icon"
                  onClick={copyCode}
                  aria-label="Copy verification code"
                >
                  <Copy size={15} />
                </Button>
              </div>
              <Button
                variant="secondary"
                size="sm"
                icon={ShieldCheck}
                loading={verifying}
                onClick={verify}
                className="mt-2.5 w-full justify-center"
              >
                Run verification now
              </Button>
              <p className="mt-2.5 break-all font-mono text-[10px] leading-relaxed text-slate-400">
                SHA-256 HMAC {data.integrity_hash}
              </p>
            </CardBody>
          </Card>

          <Card>
            <CardHeader title="Document details" icon={FileCheck2} />
            <CardBody>
              <DetailList>
                <DetailRow label="Quotation number" value={data.quotation_number} mono />
                <DetailRow label="Source request" value={data.request_number} mono />
                <DetailRow label="Issued" value={formatDateTime(data.issued_at)} />
                <DetailRow
                  label="Valid until"
                  value={
                    <span className={expired ? 'text-rose-600' : undefined}>
                      {formatDate(data.valid_until)}
                      {data.status === 'ISSUED' ? (
                        <span className="ml-1 text-[11.5px] text-slate-400">
                          ({expired ? `${Math.abs(days)}d overdue` : `${days}d left`})
                        </span>
                      ) : null}
                    </span>
                  }
                />
                <DetailRow
                  label="Authorisation"
                  value={
                    data.auto_approved
                      ? 'Automatic — within policy'
                      : data.approved_by_name ?? 'Sales manager'
                  }
                />
                <DetailRow label="Downloads" value={data.download_count} />
                {data.pdf_generated_at ? (
                  <DetailRow
                    label="PDF generated"
                    value={formatDateTime(data.pdf_generated_at)}
                  />
                ) : null}
              </DetailList>

              <Button
                variant="ghost"
                size="sm"
                className="mt-3 w-full justify-center"
                onClick={() => navigate(`/requests/${data.request_id}`)}
              >
                View the source request
              </Button>
            </CardBody>
          </Card>

          {isManager ? (
            <Card>
              <CardHeader
                title="Change status"
                description="Record acceptance or withdraw the quotation"
                icon={Timer}
              />
              <CardBody>
                <FilterSelect
                  value={data.status}
                  onChange={changeStatus}
                  options={QUOTATION_STATUS_OPTIONS}
                  placeholder="Select a status"
                  label="Quotation status"
                  className="w-full"
                />
                {statusBusy ? (
                  <p className="mt-2 text-[12px] text-slate-500">Updating…</p>
                ) : (
                  <p className="mt-2 text-[11.5px] leading-snug text-slate-500">
                    Marking a quotation accepted keeps it counted against the customer's
                    credit exposure; withdrawing it releases that exposure.
                  </p>
                )}
              </CardBody>
            </Card>
          ) : null}
        </div>
      </div>
    </>
  )
}
