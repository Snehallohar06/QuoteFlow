import { useEffect, useState } from 'react'
import { useParams } from 'react-router-dom'
import { Info, ScanLine, ShieldCheck } from 'lucide-react'

import { useToast } from '../../context/ToastContext'
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
import { Badge } from '../../components/ui/Badge'
import { Input } from '../../components/ui/Field'
import { formatDate, formatDateTime, formatMoney } from '../../lib/format'
import { quotationStatusInfo, verificationInfo } from '../../lib/status'

/**
 * Check a quotation against the issuing system.
 *
 * Calls the public `GET /verify/{code}` endpoint, which needs no token — the
 * same call a recipient of the PDF would make. A mismatch between the stored
 * amounts and the integrity digest is what the spec calls "Verification Failed".
 */
export function VerifyQuotation() {
  const { code: codeFromUrl } = useParams()
  const toast = useToast()

  const [code, setCode] = useState(codeFromUrl ?? '')
  const [result, setResult] = useState(null)
  const [error, setError] = useState(null)
  const [pending, setPending] = useState(false)

  async function runVerification(value) {
    const trimmed = (value ?? '').trim()
    if (!trimmed) {
      setError('Enter the verification code printed on the quotation.')
      return
    }

    setPending(true)
    setError(null)
    try {
      const response = await quotationsApi.verifyQuotation(trimmed)
      setResult(response)
      if (response.valid) {
        toast.success('Quotation verified', response.quotation_number)
      } else {
        toast.warning('Not verified', response.reason)
      }
    } catch (caught) {
      setError(caught.message)
      setResult(null)
    } finally {
      setPending(false)
    }
  }

  // A link of the form /verify/A3KP-7WQX-R9MT verifies immediately.
  useEffect(() => {
    if (codeFromUrl) runVerification(codeFromUrl)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [codeFromUrl])

  const info = verificationInfo(result)

  return (
    <>
      <PageHeader
        title="Verify a quotation"
        description="Confirm that a quotation document is genuine and that its amounts have not been altered since it was issued."
      />

      <div className="grid gap-4 lg:grid-cols-[400px_1fr]">
        <Card>
          <CardHeader title="Verification code" icon={ScanLine} />
          <CardBody>
            <form
              onSubmit={(event) => {
                event.preventDefault()
                runVerification(code)
              }}
              noValidate
            >
              <Input
                label="Code printed on the PDF"
                value={code}
                error={error}
                placeholder="A3KP-7WQX-R9MT"
                autoComplete="off"
                spellCheck={false}
                className="font-mono"
                onChange={(event) => {
                  setCode(event.target.value.toUpperCase())
                  setError(null)
                }}
                hint="Three groups of four characters, as shown in the document footer"
              />
              <Button
                type="submit"
                icon={ShieldCheck}
                loading={pending}
                className="mt-3 w-full justify-center"
              >
                Verify
              </Button>
            </form>

            <div className="mt-4 flex items-start gap-2 border-t border-slate-100 pt-3">
              <Info
                size={14}
                className="mt-0.5 shrink-0 text-slate-400"
                aria-hidden="true"
              />
              <p className="text-[12px] leading-relaxed text-slate-500">
                This check needs no sign-in. The system re-derives the document's
                integrity digest from the amounts it holds and compares it to the digest
                issued with the PDF. Because that digest is keyed with a secret, a
                tampered document cannot be given a matching one.
              </p>
            </div>
          </CardBody>
        </Card>

        <Card>
          <CardHeader title="Result" />
          <CardBody>
            {!result ? (
              <div className="py-10 text-center">
                <span className="inline-grid h-12 w-12 place-items-center rounded-full bg-slate-100 text-slate-400">
                  <ShieldCheck size={22} aria-hidden="true" />
                </span>
                <p className="mt-3 text-[14px] font-medium text-slate-700">
                  No code checked yet
                </p>
                <p className="mx-auto mt-1 max-w-sm text-[13px] leading-relaxed text-slate-500">
                  Enter a verification code to see what was quoted, to whom, and whether
                  the document is still authentic.
                </p>
              </div>
            ) : (
              <>
                <div
                  className={`flex items-start gap-3 rounded-md border px-3.5 py-3 ${
                    result.valid
                      ? result.expired
                        ? 'border-amber-200 bg-amber-50'
                        : 'border-emerald-200 bg-emerald-50'
                      : 'border-rose-200 bg-rose-50'
                  }`}
                >
                  <info.icon
                    size={18}
                    className={`mt-0.5 shrink-0 ${
                      result.valid
                        ? result.expired
                          ? 'text-amber-600'
                          : 'text-emerald-600'
                        : 'text-rose-600'
                    }`}
                    aria-hidden="true"
                  />
                  <div className="min-w-0">
                    <p className="text-[14px] font-semibold text-slate-900">
                      {info.label}
                    </p>
                    <p className="mt-0.5 text-[13px] leading-snug text-slate-600">
                      {result.valid
                        ? result.expired
                          ? 'This quotation is authentic, but it has passed its validity date. Ask for a fresh quotation before ordering.'
                          : 'The amounts on record match the digest issued with this document.'
                        : result.reason}
                    </p>
                  </div>
                </div>

                {result.quotation_number ? (
                  <DetailList className="mt-4">
                    <DetailRow
                      label="Quotation number"
                      value={result.quotation_number}
                      mono
                    />
                    <DetailRow
                      label="Source request"
                      value={result.request_number}
                      mono
                    />
                    <DetailRow label="Issued to" value={result.customer_name} />
                    <DetailRow label="Issued" value={formatDateTime(result.issued_at)} />
                    <DetailRow
                      label="Valid until"
                      value={
                        <span className={result.expired ? 'text-rose-600' : undefined}>
                          {formatDate(result.valid_until)}
                        </span>
                      }
                    />
                    <DetailRow
                      label="Status"
                      value={
                        <Badge
                          tone={quotationStatusInfo(result.status).tone}
                          size="sm"
                        >
                          {quotationStatusInfo(result.status).label}
                        </Badge>
                      }
                    />
                    <DetailRow label="Lines" value={result.line_count} />
                    <DetailRow
                      label="Final amount"
                      value={formatMoney(result.final_amount, {
                        currency: result.currency,
                      })}
                    />
                    <DetailRow
                      label="Authorisation"
                      value={
                        result.auto_approved
                          ? 'Automatic — within policy'
                          : (result.approved_by ?? 'Sales manager')
                      }
                    />
                  </DetailList>
                ) : null}

                {result.integrity_hash ? (
                  <p className="mt-3 break-all border-t border-slate-100 pt-3 font-mono text-[10px] leading-relaxed text-slate-400">
                    SHA-256 HMAC {result.integrity_hash}
                  </p>
                ) : null}
              </>
            )}
          </CardBody>
        </Card>
      </div>
    </>
  )
}
