/**
 * Status presentation.
 *
 * The backend's request lifecycle has twelve states, and all but two of the
 * labels the UI shows map one-to-one onto one of them. COMPLETED and ESCALATED
 * are real, stored statuses — the workflow's success gate writes COMPLETED only
 * once all six of its conditions hold, and the escalation boundary writes
 * ESCALATED when a request is parked for a human.
 *
 * Two labels are still derived, and the mapping lives here so it is not
 * re-invented per page:
 *
 *   Generating Quotation  <- status PRICED, the transient step between pricing
 *                            and the outcome
 *   Verification Failed   <- not a request state at all: the result of checking
 *                            an issued quotation's integrity digest against the
 *                            stored amounts (see verifyQuotation)
 */

import {
  AlertTriangle,
  ArrowUpCircle,
  Ban,
  CheckCircle2,
  Clock,
  FileCheck2,
  FileText,
  Loader2,
  Minus,
  PencilLine,
  ShieldAlert,
  ShieldCheck,
  TimerOff,
  XCircle,
} from 'lucide-react'

/** Backend request statuses, exactly as the API sends them. */
export const REQUEST_STATUS = {
  DRAFT: 'DRAFT',
  SUBMITTED: 'SUBMITTED',
  UNDER_VALIDATION: 'UNDER_VALIDATION',
  VALIDATION_FAILED: 'VALIDATION_FAILED',
  PRICED: 'PRICED',
  PENDING_APPROVAL: 'PENDING_APPROVAL',
  APPROVED: 'APPROVED',
  REJECTED: 'REJECTED',
  MODIFICATION_REQUESTED: 'MODIFICATION_REQUESTED',
  COMPLETED: 'COMPLETED',
  ESCALATED: 'ESCALATED',
  CANCELLED: 'CANCELLED',
}

/**
 * Tone -> Tailwind classes. Colour carries meaning here, so these are the only
 * places status colour is defined.
 */
const TONES = {
  neutral: 'bg-slate-100 text-slate-700 ring-slate-200',
  info: 'bg-brand-50 text-brand-700 ring-brand-200',
  progress: 'bg-indigo-50 text-indigo-700 ring-indigo-200',
  warning: 'bg-amber-50 text-amber-800 ring-amber-200',
  success: 'bg-emerald-50 text-emerald-700 ring-emerald-200',
  danger: 'bg-rose-50 text-rose-700 ring-rose-200',
}

export const TONE_CLASSES = TONES

const REQUEST_PRESENTATION = {
  DRAFT: { label: 'Draft', tone: 'neutral', icon: FileText },
  SUBMITTED: { label: 'Submitted', tone: 'info', icon: ArrowUpCircle },
  UNDER_VALIDATION: { label: 'Validating', tone: 'progress', icon: Loader2 },
  VALIDATION_FAILED: {
    label: 'Validation Failed',
    tone: 'danger',
    icon: AlertTriangle,
  },
  PRICED: { label: 'Generating Quotation', tone: 'progress', icon: Loader2 },
  PENDING_APPROVAL: { label: 'Awaiting Approval', tone: 'warning', icon: Clock },
  APPROVED: { label: 'Approved', tone: 'success', icon: CheckCircle2 },
  REJECTED: { label: 'Rejected', tone: 'danger', icon: XCircle },
  MODIFICATION_REQUESTED: {
    label: 'Modification Required',
    tone: 'warning',
    icon: PencilLine,
  },
  COMPLETED: { label: 'Completed', tone: 'success', icon: FileCheck2 },
  ESCALATED: { label: 'Escalated', tone: 'danger', icon: ArrowUpCircle },
  CANCELLED: { label: 'Cancelled', tone: 'neutral', icon: Ban },
}

const FALLBACK = { label: 'Unknown', tone: 'neutral', icon: FileText }

/**
 * Presentation for a request status.
 *
 * The second argument is accepted for the one case that still needs the whole
 * record: APPROVED means "authorised, document not yet verified", which reads
 * better as a progress state than as a success.
 */
export function requestStatusInfo(status, request = null) {
  if (status === REQUEST_STATUS.APPROVED) {
    return request?.quotation_id
      ? { label: 'Finalising', tone: 'progress', icon: Loader2 }
      : { label: 'Approved', tone: 'progress', icon: Loader2 }
  }
  return REQUEST_PRESENTATION[status] ?? FALLBACK
}

/**
 * True when the request is parked for a human.
 *
 * Covers both shapes that means: the stored ESCALATED status, which the
 * workflow's escalation boundary writes, and a request queued for a manager
 * because a business rule raised an exception.
 */
export function isEscalated(request) {
  if (!request) return false
  if (request.status === REQUEST_STATUS.ESCALATED) return true
  return (
    request.status === REQUEST_STATUS.PENDING_APPROVAL &&
    (request.requires_approval || (request.exceptions?.length ?? 0) > 0)
  )
}

/** Why the workflow parked a request, in words. */
const ESCALATION_REASONS = {
  MISSING_CUSTOMER_INFORMATION: 'Customer information is incomplete',
  PRODUCT_UNAVAILABLE: 'A product cannot be supplied',
  DISCOUNT_EXCEPTION: 'The discount is above policy',
  MANAGER_REJECTION: 'The sales manager rejected it',
  REPEATED_PROCESSING_FAILURE: 'Processing failed repeatedly',
  VERIFICATION_MISMATCH: 'The document failed independent verification',
  BUDGET_EXCEEDED: 'The processing budget was exhausted',
}

export function escalationReasonLabel(reason) {
  return ESCALATION_REASONS[reason] ?? (reason ? humaniseReason(reason) : null)
}

function humaniseReason(value) {
  const text = String(value).replace(/_/g, ' ').toLowerCase()
  return text.charAt(0).toUpperCase() + text.slice(1)
}

/** Every status the UI can show for a request, for filter dropdowns. */
export const REQUEST_STATUS_OPTIONS = Object.entries(REQUEST_PRESENTATION).map(
  ([value, { label }]) => ({ value, label })
)

/** Statuses a request can still be edited and resubmitted from. */
export const EDITABLE_STATUSES = new Set([
  REQUEST_STATUS.DRAFT,
  REQUEST_STATUS.VALIDATION_FAILED,
  REQUEST_STATUS.MODIFICATION_REQUESTED,
  // A parked request can be corrected and resubmitted, which is the point of
  // parking it rather than closing it.
  REQUEST_STATUS.ESCALATED,
])

/** Statuses from which nothing further can happen. */
export const TERMINAL_STATUSES = new Set([
  REQUEST_STATUS.COMPLETED,
  REQUEST_STATUS.REJECTED,
  REQUEST_STATUS.CANCELLED,
])

export function canEditRequest(request) {
  return Boolean(request) && EDITABLE_STATUSES.has(request.status)
}

export function canCancelRequest(request) {
  return Boolean(request) && !TERMINAL_STATUSES.has(request.status)
}

// ---------------------------------------------------------------------------
// Quotations
// ---------------------------------------------------------------------------

const QUOTATION_PRESENTATION = {
  ISSUED: { label: 'Issued', tone: 'success', icon: FileCheck2 },
  ACCEPTED: { label: 'Accepted', tone: 'success', icon: CheckCircle2 },
  EXPIRED: { label: 'Expired', tone: 'neutral', icon: Clock },
  WITHDRAWN: { label: 'Withdrawn', tone: 'neutral', icon: Ban },
}

export function quotationStatusInfo(status) {
  return QUOTATION_PRESENTATION[status] ?? FALLBACK
}

export const QUOTATION_STATUS_OPTIONS = Object.entries(QUOTATION_PRESENTATION).map(
  ([value, { label }]) => ({ value, label })
)

/**
 * Presentation for the result of `GET /verify/{code}`.
 *
 * This is the source of the spec's "Verification Failed" state: a quotation
 * whose stored amounts no longer match the integrity digest issued with it.
 */
export function verificationInfo(result) {
  if (!result) return { label: 'Not verified', tone: 'neutral', icon: ShieldAlert }
  if (!result.valid) {
    return { label: 'Verification Failed', tone: 'danger', icon: ShieldAlert }
  }
  if (result.expired) {
    return { label: 'Verified — expired', tone: 'warning', icon: ShieldCheck }
  }
  return { label: 'Verified', tone: 'success', icon: ShieldCheck }
}

// ---------------------------------------------------------------------------
// Approvals
// ---------------------------------------------------------------------------

const APPROVAL_PRESENTATION = {
  PENDING: { label: 'Pending', tone: 'warning', icon: Clock },
  APPROVED: { label: 'Approved', tone: 'success', icon: CheckCircle2 },
  REJECTED: { label: 'Rejected', tone: 'danger', icon: XCircle },
  MODIFICATION_REQUESTED: {
    label: 'Modification Requested',
    tone: 'warning',
    icon: PencilLine,
  },
}

export function approvalStatusInfo(status) {
  return APPROVAL_PRESENTATION[status] ?? FALLBACK
}

export const APPROVAL_STATUS_OPTIONS = Object.entries(APPROVAL_PRESENTATION).map(
  ([value, { label }]) => ({ value, label })
)

// ---------------------------------------------------------------------------
// Workflow steps and execution outcomes
// ---------------------------------------------------------------------------

/** The six pipeline steps, in the order the engine runs them. */
export const WORKFLOW_STEPS = [
  {
    key: 'VALIDATE_REQUEST',
    label: 'Input Validation',
    description: 'Customer, lines and products checked',
  },
  {
    key: 'CHECK_AVAILABILITY',
    label: 'Product Verification',
    description: 'Sellable stock confirmed per line',
  },
  {
    key: 'CALCULATE_PRICING',
    label: 'Price Calculation',
    description: 'Decimal arithmetic for every amount',
  },
  {
    key: 'EVALUATE_DISCOUNT_RULES',
    label: 'Business Rule Validation',
    description: 'Discount policy applied to the figures',
  },
  {
    key: 'DETERMINE_APPROVAL_ROUTE',
    label: 'Approval Routing',
    description: 'Auto-approve or escalate to a manager',
  },
  {
    key: 'GENERATE_DOCUMENT',
    label: 'Quotation Generation',
    description: 'The action tool issues the quotation and renders its PDF',
  },
  {
    key: 'VERIFY_DOCUMENT',
    label: 'Independent Verification',
    description: 'The checker tool recalculates every amount from source',
  },
  {
    key: 'FINALISE',
    label: 'Completion',
    description: 'The success gate is evaluated and the outcome written',
  },
]

/**
 * The six conditions the backend's success gate requires before a request may
 * be COMPLETED. Labelled here so the UI can show which one is outstanding.
 */
export const SUCCESS_GATE_CONDITIONS = [
  { key: 'input_validation_passed', label: 'Input validation' },
  { key: 'product_verification_passed', label: 'Product verification' },
  { key: 'pricing_validation_passed', label: 'Pricing validation' },
  { key: 'approval_recorded', label: 'Approval recorded' },
  { key: 'document_generated', label: 'Document generated' },
  {
    key: 'independent_verification_passed',
    label: 'Independent verification',
  },
]

export const STEP_LABELS = Object.fromEntries(
  WORKFLOW_STEPS.map((step) => [step.key, step.label])
)

const STEP_STATUS_PRESENTATION = {
  SUCCESS: { label: 'Success', tone: 'success', icon: CheckCircle2 },
  FAILED: { label: 'Failed', tone: 'danger', icon: XCircle },
  SKIPPED: { label: 'Skipped', tone: 'neutral', icon: Ban },
}

export function stepStatusInfo(status) {
  return STEP_STATUS_PRESENTATION[status] ?? FALLBACK
}

const OUTCOME_PRESENTATION = {
  COMPLETED: { label: 'Completed', tone: 'success', icon: FileCheck2 },
  AUTO_APPROVED: { label: 'Auto-approved', tone: 'success', icon: CheckCircle2 },
  PENDING_APPROVAL: {
    label: 'Awaiting approval',
    tone: 'warning',
    icon: ArrowUpCircle,
  },
  VALIDATION_FAILED: {
    label: 'Validation failed',
    tone: 'danger',
    icon: AlertTriangle,
  },
  ESCALATED: { label: 'Escalated', tone: 'danger', icon: ArrowUpCircle },
  NO_OP: { label: 'No action needed', tone: 'neutral', icon: Minus },
  BUDGET_EXCEEDED: {
    label: 'Budget exceeded',
    tone: 'danger',
    icon: TimerOff,
  },
}

export function outcomeInfo(outcome) {
  return OUTCOME_PRESENTATION[outcome] ?? FALLBACK
}

// ---------------------------------------------------------------------------
// Exceptions raised by the rule engine
// ---------------------------------------------------------------------------

const EXCEPTION_PRESENTATION = {
  DISCOUNT_LIMIT_EXCEEDED: {
    label: 'Discount above ceiling',
    tone: 'warning',
    hint: 'The requested discount exceeds what the quantity band and customer tier allow.',
  },
  ORDER_VALUE_THRESHOLD: {
    label: 'Order value threshold',
    tone: 'info',
    hint: 'The quotation total reaches the value at which a manager must review it.',
  },
  CREDIT_LIMIT_EXCEEDED: {
    label: 'Credit limit exceeded',
    tone: 'danger',
    hint: 'This quotation would take the customer past their credit limit.',
  },
  STOCK_SHORTFALL: {
    label: 'Stock shortfall',
    tone: 'warning',
    hint: 'One or more lines cannot be met from stock and would be backordered.',
  },
}

export function exceptionInfo(type) {
  return (
    EXCEPTION_PRESENTATION[type] ?? {
      label: type ?? 'Exception',
      tone: 'warning',
      hint: null,
    }
  )
}

// ---------------------------------------------------------------------------
// Availability, customers, products, users
// ---------------------------------------------------------------------------

const AVAILABILITY_PRESENTATION = {
  IN_STOCK: { label: 'In stock', tone: 'success' },
  PARTIAL: { label: 'Partially available', tone: 'warning' },
  OUT_OF_STOCK: { label: 'Out of stock', tone: 'danger' },
}

export function availabilityInfo(status) {
  return AVAILABILITY_PRESENTATION[status] ?? { label: '—', tone: 'neutral' }
}

const CUSTOMER_STATUS_PRESENTATION = {
  ACTIVE: { label: 'Active', tone: 'success' },
  ON_HOLD: { label: 'On hold', tone: 'warning' },
  BLOCKED: { label: 'Blocked', tone: 'danger' },
}

export function customerStatusInfo(status) {
  return CUSTOMER_STATUS_PRESENTATION[status] ?? { label: '—', tone: 'neutral' }
}

export const CUSTOMER_STATUS_OPTIONS = Object.entries(
  CUSTOMER_STATUS_PRESENTATION
).map(([value, { label }]) => ({ value, label }))

const PRODUCT_STATUS_PRESENTATION = {
  ACTIVE: { label: 'Active', tone: 'success' },
  DISCONTINUED: { label: 'Discontinued', tone: 'neutral' },
}

export function productStatusInfo(status) {
  return PRODUCT_STATUS_PRESENTATION[status] ?? { label: '—', tone: 'neutral' }
}

export const PRODUCT_STATUS_OPTIONS = Object.entries(PRODUCT_STATUS_PRESENTATION).map(
  ([value, { label }]) => ({ value, label })
)

// ---------------------------------------------------------------------------
// Master-data authorisation
// ---------------------------------------------------------------------------

const MASTER_DATA_STATUS_PRESENTATION = {
  PENDING: { label: 'Awaiting approval', tone: 'warning', icon: Clock },
  APPROVED: { label: 'Approved', tone: 'success', icon: CheckCircle2 },
  REJECTED: { label: 'Not approved', tone: 'danger', icon: XCircle },
  WITHDRAWN: { label: 'Withdrawn', tone: 'neutral', icon: Ban },
}

export function masterDataStatusInfo(status) {
  return MASTER_DATA_STATUS_PRESENTATION[status] ?? { label: '—', tone: 'neutral' }
}

export const MASTER_DATA_STATUS_OPTIONS = Object.entries(
  MASTER_DATA_STATUS_PRESENTATION
).map(([value, { label }]) => ({ value, label }))

export const MASTER_DATA_ENTITY_OPTIONS = [
  { value: 'CUSTOMER', label: 'Customers' },
  { value: 'PRODUCT', label: 'Products' },
]

/** Singular noun for the record being proposed, for use in a sentence. */
export function masterDataEntityLabel(entityType) {
  return entityType === 'PRODUCT' ? 'product' : 'customer'
}

export const CUSTOMER_TIERS = ['STANDARD', 'SILVER', 'GOLD', 'PLATINUM']

const TIER_PRESENTATION = {
  STANDARD: { label: 'Standard', tone: 'neutral' },
  SILVER: { label: 'Silver', tone: 'neutral' },
  GOLD: { label: 'Gold', tone: 'warning' },
  PLATINUM: { label: 'Platinum', tone: 'info' },
}

export function tierInfo(tier) {
  return TIER_PRESENTATION[tier] ?? { label: tier ?? '—', tone: 'neutral' }
}

export const ROLE_LABELS = {
  CUSTOMER: 'Customer',
  SALES_EMPLOYEE: 'Sales Employee',
  SALES_MANAGER: 'Sales Manager',
}

const NOTIFICATION_PRESENTATION = {
  REQUEST_SUBMITTED: { tone: 'info', icon: ArrowUpCircle },
  VALIDATION_FAILED: { tone: 'danger', icon: AlertTriangle },
  APPROVAL_REQUIRED: { tone: 'warning', icon: Clock },
  QUOTATION_READY: { tone: 'success', icon: FileCheck2 },
  REQUEST_REJECTED: { tone: 'danger', icon: XCircle },
  MODIFICATION_REQUESTED: { tone: 'warning', icon: PencilLine },
}

export function notificationInfo(type) {
  return NOTIFICATION_PRESENTATION[type] ?? { tone: 'neutral', icon: FileText }
}
