import { useEffect, useState } from 'react'
import {
  Building2,
  Info,
  Percent,
  Plus,
  RefreshCw,
  Save,
  ShieldCheck,
  Trash2,
} from 'lucide-react'

import { useAuth } from '../../context/AuthContext'
import { useToast } from '../../context/ToastContext'
import { useAsync } from '../../hooks/useAsync'
import * as settingsApi from '../../api/settings'
import { PageHeader } from '../../components/layout/PageHeader'
import { Button } from '../../components/ui/Button'
import { Card, CardBody, CardFooter, CardHeader } from '../../components/ui/Card'
import { Badge } from '../../components/ui/Badge'
import { Checkbox, Input } from '../../components/ui/Field'
import { ErrorState, PageLoader } from '../../components/ui/Table'
import { CUSTOMER_TIERS, tierInfo } from '../../lib/status'
import { formatMoney, formatPercent } from '../../lib/format'

/**
 * The company rule book.
 *
 * Everything on this page is read by the pricing, discount and approval engines
 * at runtime — no threshold is hard-coded in the backend. A manager can re-tune
 * the deployed workflow here without a code change; every other role sees it
 * read-only, which is useful because it explains the limits that apply to them.
 */
export function CompanySettings() {
  const { isManager } = useAuth()
  const toast = useToast()

  const settings = useAsync(() => settingsApi.getSettings(), [])

  const [tiers, setTiers] = useState([])
  const [bonuses, setBonuses] = useState({})
  const [discount, setDiscount] = useState({ absolute: '', costFloor: true })
  const [tax, setTax] = useState({ name: '', rate: '' })
  const [approval, setApproval] = useState({
    threshold: '',
    sla: '',
    onDiscount: true,
    onStock: true,
    onCredit: true,
  })
  const [quotation, setQuotation] = useState({ validity: '', backorder: true })
  const [errors, setErrors] = useState({})
  const [saving, setSaving] = useState(false)

  // Load the stored document into the editable form once it arrives.
  useEffect(() => {
    const data = settings.data
    if (!data) return

    setTiers(
      data.discount_policy.tiers.map((tier) => ({
        min_quantity: String(tier.min_quantity),
        max_quantity: tier.max_quantity === null ? '' : String(tier.max_quantity),
        max_discount_percent: String(tier.max_discount_percent),
        label: tier.label ?? '',
      }))
    )
    setBonuses(
      Object.fromEntries(
        CUSTOMER_TIERS.map((tier) => [
          tier,
          String(data.discount_policy.tier_bonus_percent?.[tier] ?? 0),
        ])
      )
    )
    setDiscount({
      absolute: String(data.discount_policy.absolute_max_discount_percent),
      costFloor: data.discount_policy.enforce_cost_floor,
    })
    setTax({
      name: data.tax_policy.name,
      rate: String(data.tax_policy.rate_percent),
    })
    setApproval({
      threshold: String(data.approval_policy.order_value_threshold),
      sla: String(data.approval_policy.approval_sla_hours),
      onDiscount: data.approval_policy.require_on_discount_exception,
      onStock: data.approval_policy.require_on_stock_shortfall,
      onCredit: data.approval_policy.require_on_credit_breach,
    })
    setQuotation({
      validity: String(data.quotation_policy.validity_days),
      backorder: data.quotation_policy.allow_backorder,
    })
  }, [settings.data])

  function updateTier(index, patch) {
    setTiers((current) => {
      const next = [...current]
      next[index] = { ...next[index], ...patch }
      return next
    })
    setErrors({})
  }

  function addTier() {
    const last = tiers[tiers.length - 1]
    const nextMin = last?.max_quantity ? Number(last.max_quantity) + 1 : 1
    setTiers((current) => [
      ...current,
      {
        min_quantity: String(nextMin),
        max_quantity: '',
        max_discount_percent: '0',
        label: '',
      },
    ])
  }

  function removeTier(index) {
    setTiers((current) => current.filter((_, position) => position !== index))
  }

  /** Mirrors the backend's DiscountTier validation so a bad table is caught here. */
  function validate() {
    const next = {}

    if (tiers.length === 0) {
      next.tiers = 'At least one discount tier must be configured.'
    }
    tiers.forEach((tier, index) => {
      const min = Number(tier.min_quantity)
      const max = tier.max_quantity === '' ? null : Number(tier.max_quantity)
      if (!tier.min_quantity || Number.isNaN(min) || min < 1) {
        next[`tier-${index}`] = 'Minimum quantity must be at least 1.'
      } else if (max !== null && max < min) {
        next[`tier-${index}`] = 'Maximum must be greater than or equal to the minimum.'
      } else if (
        tier.max_discount_percent === '' ||
        Number(tier.max_discount_percent) < 0 ||
        Number(tier.max_discount_percent) > 100
      ) {
        next[`tier-${index}`] = 'Discount must be between 0 and 100.'
      }
    })

    if (
      discount.absolute === '' ||
      Number(discount.absolute) < 0 ||
      Number(discount.absolute) > 100
    ) {
      next.absolute = 'Enter a percentage between 0 and 100.'
    }
    if (tax.rate === '' || Number(tax.rate) < 0 || Number(tax.rate) > 100) {
      next.taxRate = 'Enter a percentage between 0 and 100.'
    }
    if (!tax.name.trim()) next.taxName = 'Give the tax a name, e.g. GST.'
    if (approval.threshold === '' || Number(approval.threshold) < 0) {
      next.threshold = 'Enter 0 or more. Use 0 to disable the value check.'
    }
    if (approval.sla === '' || Number(approval.sla) < 1) {
      next.sla = 'The SLA must be at least one hour.'
    }
    if (quotation.validity === '' || Number(quotation.validity) < 1) {
      next.validity = 'Validity must be at least one day.'
    }

    setErrors(next)
    return Object.keys(next).length === 0
  }

  async function save() {
    if (!validate()) {
      toast.warning('Check the highlighted fields', 'The rule book was not saved.')
      return
    }

    setSaving(true)
    try {
      const patch = {
        discount_policy: {
          // Lists are replaced wholesale by the backend, which is the intent here.
          tiers: tiers.map((tier) => ({
            min_quantity: Number(tier.min_quantity),
            max_quantity: tier.max_quantity === '' ? null : Number(tier.max_quantity),
            max_discount_percent: Number(tier.max_discount_percent),
            label: tier.label.trim() || null,
          })),
          tier_bonus_percent: Object.fromEntries(
            Object.entries(bonuses).map(([tier, value]) => [tier, Number(value) || 0])
          ),
          absolute_max_discount_percent: Number(discount.absolute),
          enforce_cost_floor: discount.costFloor,
        },
        tax_policy: {
          name: tax.name.trim(),
          rate_percent: Number(tax.rate),
        },
        approval_policy: {
          order_value_threshold: Number(approval.threshold),
          approval_sla_hours: Number(approval.sla),
          require_on_discount_exception: approval.onDiscount,
          require_on_stock_shortfall: approval.onStock,
          require_on_credit_breach: approval.onCredit,
        },
        quotation_policy: {
          validity_days: Number(quotation.validity),
          allow_backorder: quotation.backorder,
        },
      }

      await settingsApi.updateSettings(patch)
      toast.success(
        'Rule book updated',
        'The engines use these values from the next request onwards.'
      )
      settings.reload()
    } catch (error) {
      // The backend validates the merged document and rejects a bad patch with
      // field paths, which map straight onto the inputs above.
      const fieldErrors = error.fieldErrors ?? {}
      if (Object.keys(fieldErrors).length > 0) {
        setErrors(
          Object.fromEntries(
            Object.entries(fieldErrors).map(([field, message]) => [field, message])
          )
        )
      }
      toast.fromError(error, 'Could not save the settings')
    } finally {
      setSaving(false)
    }
  }

  if (settings.loading && !settings.data) return <PageLoader label="Loading settings" />
  if (settings.error) {
    return (
      <Card>
        <ErrorState error={settings.error} onRetry={settings.reload} />
      </Card>
    )
  }

  const profile = settings.data?.profile
  const readOnly = !isManager

  return (
    <>
      <PageHeader
        title="Company settings"
        description="The business rules the workflow engine reads at runtime. No threshold here is hard-coded in the backend."
        actions={
          <>
            <Button variant="secondary" icon={RefreshCw} onClick={settings.reload}>
              Reload
            </Button>
            {isManager ? (
              <Button icon={Save} loading={saving} onClick={save}>
                Save changes
              </Button>
            ) : null}
          </>
        }
      />

      {readOnly ? (
        <Card className="mb-4 border-slate-300 bg-slate-50">
          <CardBody>
            <div className="flex items-start gap-2.5">
              <Info
                size={16}
                className="mt-0.5 shrink-0 text-slate-500"
                aria-hidden="true"
              />
              <p className="text-[12.5px] leading-relaxed text-slate-600">
                These are the rules that apply to your requests. Only a sales manager can
                change them.
              </p>
            </div>
          </CardBody>
        </Card>
      ) : null}

      <div className="grid gap-4 lg:grid-cols-2">
        <Card className="lg:col-span-2">
          <CardHeader
            title="Discount tiers"
            description="The maximum discount allowed at each order quantity, before the customer-tier bonus"
            icon={Percent}
            action={
              isManager ? (
                <Button variant="secondary" size="sm" icon={Plus} onClick={addTier}>
                  Add tier
                </Button>
              ) : null
            }
          />
          <CardBody>
            {errors.tiers ? (
              <p className="mb-3 rounded border border-rose-200 bg-rose-50 px-3 py-2 text-[12.5px] text-rose-800">
                {errors.tiers}
              </p>
            ) : null}

            <div className="space-y-3">
              {tiers.map((tier, index) => (
                <div
                  key={index}
                  className="rounded-md border border-slate-200 bg-slate-50/60 p-3"
                >
                  <div className="grid gap-3 sm:grid-cols-[1fr_1fr_1fr_1.4fr_auto]">
                    <Input
                      label="From quantity"
                      type="number"
                      min="1"
                      value={tier.min_quantity}
                      disabled={readOnly}
                      onChange={(event) =>
                        updateTier(index, { min_quantity: event.target.value })
                      }
                    />
                    <Input
                      label="To quantity"
                      type="number"
                      min="1"
                      value={tier.max_quantity}
                      disabled={readOnly}
                      placeholder="and above"
                      hint="Blank = open ended"
                      onChange={(event) =>
                        updateTier(index, { max_quantity: event.target.value })
                      }
                    />
                    <Input
                      label="Max discount"
                      type="number"
                      min="0"
                      max="100"
                      step="0.5"
                      value={tier.max_discount_percent}
                      disabled={readOnly}
                      prefix="%"
                      onChange={(event) =>
                        updateTier(index, { max_discount_percent: event.target.value })
                      }
                    />
                    <Input
                      label="Label"
                      value={tier.label}
                      disabled={readOnly}
                      placeholder="1-5 units"
                      onChange={(event) =>
                        updateTier(index, { label: event.target.value })
                      }
                    />
                    {isManager ? (
                      <div className="flex items-end pb-0.5">
                        <Button
                          variant="ghost"
                          size="icon"
                          aria-label={`Remove tier ${index + 1}`}
                          disabled={tiers.length <= 1}
                          onClick={() => removeTier(index)}
                        >
                          <Trash2 size={15} className="text-rose-500" />
                        </Button>
                      </div>
                    ) : null}
                  </div>
                  {errors[`tier-${index}`] ? (
                    <p className="mt-2 text-[12px] text-rose-600">
                      {errors[`tier-${index}`]}
                    </p>
                  ) : null}
                </div>
              ))}
            </div>

            <div className="mt-4 border-t border-slate-200 pt-4">
              <p className="mb-2.5 text-[12.5px] font-medium text-slate-700">
                Customer tier bonus
                <span className="ml-1 font-normal text-slate-500">
                  — added to the band ceiling for that customer
                </span>
              </p>
              <div className="grid gap-3 sm:grid-cols-4">
                {CUSTOMER_TIERS.map((tier) => (
                  <Input
                    key={tier}
                    label={tierInfo(tier).label}
                    type="number"
                    min="0"
                    max="100"
                    step="0.5"
                    value={bonuses[tier] ?? '0'}
                    disabled={readOnly}
                    prefix="%"
                    onChange={(event) =>
                      setBonuses((current) => ({ ...current, [tier]: event.target.value }))
                    }
                  />
                ))}
              </div>
            </div>

            <div className="mt-4 grid gap-4 border-t border-slate-200 pt-4 sm:grid-cols-2">
              <Input
                label="Absolute maximum discount"
                type="number"
                min="0"
                max="100"
                step="0.5"
                value={discount.absolute}
                error={errors.absolute}
                disabled={readOnly}
                prefix="%"
                hint="No approval can grant more than this; requests above it are refused outright"
                onChange={(event) =>
                  setDiscount((current) => ({ ...current, absolute: event.target.value }))
                }
              />
              <div className="flex items-center pt-1">
                <Checkbox
                  label="Never sell below cost price"
                  hint="Refuses any discount that would price a line under its cost"
                  checked={discount.costFloor}
                  disabled={readOnly}
                  onChange={(event) =>
                    setDiscount((current) => ({
                      ...current,
                      costFloor: event.target.checked,
                    }))
                  }
                />
              </div>
            </div>
          </CardBody>
        </Card>

        <Card>
          <CardHeader
            title="Approval routing"
            description="When a priced request must stop for a manager"
            icon={ShieldCheck}
          />
          <CardBody className="space-y-4">
            <Input
              label="Order value threshold"
              type="number"
              min="0"
              step="1000"
              value={approval.threshold}
              error={errors.threshold}
              disabled={readOnly}
              prefix="₹"
              hint="Requests at or above this always need review. 0 disables the check."
              onChange={(event) =>
                setApproval((current) => ({ ...current, threshold: event.target.value }))
              }
            />
            <Input
              label="Approval SLA"
              type="number"
              min="1"
              value={approval.sla}
              error={errors.sla}
              disabled={readOnly}
              hint="Hours a manager has to decide; drives the SLA metric"
              onChange={(event) =>
                setApproval((current) => ({ ...current, sla: event.target.value }))
              }
            />

            <div className="space-y-2.5 border-t border-slate-200 pt-3">
              <Checkbox
                label="Escalate on a discount exception"
                hint="A line above its ceiling goes to a manager"
                checked={approval.onDiscount}
                disabled={readOnly}
                onChange={(event) =>
                  setApproval((current) => ({
                    ...current,
                    onDiscount: event.target.checked,
                  }))
                }
              />
              <Checkbox
                label="Escalate on a stock shortfall"
                hint="Any line that cannot be met from stock"
                checked={approval.onStock}
                disabled={readOnly}
                onChange={(event) =>
                  setApproval((current) => ({ ...current, onStock: event.target.checked }))
                }
              />
              <Checkbox
                label="Escalate on a credit-limit breach"
                hint="When the quotation would exceed the customer's limit"
                checked={approval.onCredit}
                disabled={readOnly}
                onChange={(event) =>
                  setApproval((current) => ({
                    ...current,
                    onCredit: event.target.checked,
                  }))
                }
              />
            </div>
          </CardBody>
        </Card>

        <Card>
          <CardHeader
            title="Tax and quotation policy"
            description="Applied to every new quotation"
          />
          <CardBody className="space-y-4">
            <div className="grid gap-4 sm:grid-cols-2">
              <Input
                label="Tax name"
                value={tax.name}
                error={errors.taxName}
                disabled={readOnly}
                placeholder="GST"
                onChange={(event) =>
                  setTax((current) => ({ ...current, name: event.target.value }))
                }
              />
              <Input
                label="Default tax rate"
                type="number"
                min="0"
                max="100"
                step="0.5"
                value={tax.rate}
                error={errors.taxRate}
                disabled={readOnly}
                prefix="%"
                hint="Products may override this"
                onChange={(event) =>
                  setTax((current) => ({ ...current, rate: event.target.value }))
                }
              />
            </div>

            <Input
              label="Quotation validity"
              type="number"
              min="1"
              value={quotation.validity}
              error={errors.validity}
              disabled={readOnly}
              hint="Days before an issued quotation expires"
              onChange={(event) =>
                setQuotation((current) => ({ ...current, validity: event.target.value }))
              }
              className="sm:max-w-56"
            />

            <Checkbox
              label="Allow backorders"
              hint="When off, a request that cannot be met from stock fails validation instead of being quoted with a lead time"
              checked={quotation.backorder}
              disabled={readOnly}
              onChange={(event) =>
                setQuotation((current) => ({
                  ...current,
                  backorder: event.target.checked,
                }))
              }
            />

            <div className="rounded-md bg-slate-50 px-3 py-2.5">
              <p className="text-[11.5px] font-medium uppercase tracking-wide text-slate-500">
                Currently in force
              </p>
              <ul className="mt-1.5 space-y-0.5 text-[12.5px] text-slate-600">
                <li>
                  Tax:{' '}
                  <span className="font-medium text-slate-800">
                    {settings.data.tax_policy.name}{' '}
                    {formatPercent(settings.data.tax_policy.rate_percent)}
                  </span>
                </li>
                <li>
                  Review above{' '}
                  <span className="font-medium text-slate-800">
                    {formatMoney(settings.data.approval_policy.order_value_threshold)}
                  </span>
                </li>
                <li>
                  Validity{' '}
                  <span className="font-medium text-slate-800">
                    {settings.data.quotation_policy.validity_days} days
                  </span>
                </li>
                <li>
                  Hard ceiling{' '}
                  <span className="font-medium text-slate-800">
                    {formatPercent(
                      settings.data.discount_policy.absolute_max_discount_percent
                    )}
                  </span>
                </li>
              </ul>
            </div>
          </CardBody>
        </Card>

        <Card className="lg:col-span-2">
          <CardHeader
            title="Company profile"
            description="Printed on every quotation PDF"
            icon={Building2}
          />
          <CardBody>
            <div className="grid gap-4 sm:grid-cols-2">
              <div>
                <p className="text-[14px] font-semibold text-navy-800">
                  {profile?.name}
                </p>
                <p className="text-[12.5px] text-slate-500">{profile?.legal_name}</p>
                <div className="mt-2 space-y-0.5">
                  {profile?.address_lines?.map((line, index) => (
                    <p key={index} className="text-[12.5px] text-slate-600">
                      {line}
                    </p>
                  ))}
                </div>
              </div>
              <div className="space-y-1">
                <p className="text-[12.5px] text-slate-600">{profile?.email}</p>
                <p className="text-[12.5px] text-slate-600">{profile?.phone}</p>
                <p className="text-[12.5px] text-slate-600">{profile?.website}</p>
                <p className="font-mono text-[11.5px] text-slate-500">
                  Tax ID {profile?.tax_id}
                </p>
              </div>
            </div>
            <p className="mt-3 flex items-start gap-1.5 border-t border-slate-100 pt-3 text-[11.5px] leading-snug text-slate-500">
              <Info size={12} className="mt-0.5 shrink-0" aria-hidden="true" />
              The company profile is seeded with the deployment and is not editable from
              this screen. Changing it is a settings patch on the backend.
            </p>
          </CardBody>
        </Card>
      </div>

      {isManager ? (
        <Card className="mt-4">
          <CardFooter>
            <p className="mr-auto flex items-center gap-1.5 text-[12px] text-slate-500">
              <Badge tone="info" size="sm">
                Takes effect immediately
              </Badge>
              Saved values apply to the next request submitted, not to quotations already
              issued.
            </p>
            <Button variant="secondary" onClick={settings.reload} disabled={saving}>
              Discard changes
            </Button>
            <Button icon={Save} loading={saving} onClick={save}>
              Save changes
            </Button>
          </CardFooter>
        </Card>
      ) : null}
    </>
  )
}
