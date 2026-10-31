"""`quotation_requests` collection - the working document of the workflow.

A request carries its own priced lines, the exceptions the rule engine raised and
the status it reached, so the sales console can render a full picture from one
read.
"""

from datetime import datetime

from pydantic import Field

from app.models.common import (
    DocumentModel,
    JsonDict,
    Money,
    PyObjectId,
    Rate,
    utc_now,
)
from app.models.enums import (
    AvailabilityStatus,
    EscalationReason,
    ExceptionType,
    RequestStatus,
)


class LineAvailability(DocumentModel):
    """Outcome of the stock check for one line."""

    status: AvailabilityStatus
    available_quantity: int
    shortfall: int = 0
    lead_time_days: int = 0
    backorder_allowed: bool = True


class RequestLine(DocumentModel):
    """A fully priced line. Every monetary field is computed by the engines."""

    product_id: PyObjectId
    sku: str
    name: str
    unit: str = "pcs"
    quantity: int = Field(ge=1)
    unit_price: Money

    requested_discount_percent: Rate = Field(default="0")
    #: Ceiling derived from the quantity band plus the customer tier bonus.
    max_allowed_discount_percent: Rate = Field(default="0")
    #: What the pricing engine actually charged (may be a manager override).
    applied_discount_percent: Rate = Field(default="0")
    #: True when the request asked for more than the ceiling allows.
    discount_exception: bool = False

    line_subtotal: Money = Field(default="0.00")
    line_discount_amount: Money = Field(default="0.00")
    line_taxable_amount: Money = Field(default="0.00")
    tax_rate: Rate = Field(default="0")
    line_tax_amount: Money = Field(default="0.00")
    line_total: Money = Field(default="0.00")

    availability: LineAvailability | None = None
    notes: str | None = None


class PricingSummary(DocumentModel):
    """Document-level totals, all derived from the line amounts."""

    subtotal: Money = Field(default="0.00")
    total_discount: Money = Field(default="0.00")
    taxable_amount: Money = Field(default="0.00")
    total_tax: Money = Field(default="0.00")
    final_amount: Money = Field(default="0.00")
    #: total_discount expressed as a percentage of subtotal.
    effective_discount_percent: Rate = Field(default="0")
    currency: str = "INR"
    tax_label: str = "GST"
    total_quantity: int = 0
    line_count: int = 0


class RuleException(DocumentModel):
    """A reason the request could not be auto-approved."""

    type: ExceptionType
    message: str
    #: Structured facts behind the exception, for the manager UI and analytics.
    context: JsonDict = Field(default_factory=dict)


class StatusHistoryEntry(DocumentModel):
    from_status: RequestStatus | None = None
    to_status: RequestStatus
    actor_id: PyObjectId | None = None
    actor_name: str | None = None
    note: str | None = None
    at: datetime = Field(default_factory=utc_now)


class QuotationRequest(DocumentModel):
    request_number: str
    customer_id: PyObjectId
    customer_code: str
    customer_name: str
    #: The user who keyed the request in (the customer, or a sales employee).
    created_by: PyObjectId
    created_by_role: str

    status: RequestStatus = RequestStatus.DRAFT
    items: list[RequestLine] = Field(default_factory=list)
    pricing: PricingSummary | None = None

    validation_errors: list[str] = Field(default_factory=list)
    exceptions: list[RuleException] = Field(default_factory=list)
    requires_approval: bool = False

    #: Cross-references filled in as the workflow progresses.
    last_execution_id: PyObjectId | None = None
    approval_id: PyObjectId | None = None
    quotation_id: PyObjectId | None = None

    expected_delivery_date: datetime | None = None
    customer_notes: str | None = None
    internal_notes: str | None = None

    #: Incremented each time a MODIFICATION_REQUESTED request is resubmitted.
    revision: int = 0

    # ---- Execution bookkeeping, for the workflow boundaries --------------
    #: Pipeline runs this request has consumed, against
    #: execution_policy.max_attempts_per_request.
    attempt_count: int = 0
    #: Transient-failure retries across every attempt.
    retry_count: int = 0
    #: Cumulative engine time, against max_total_execution_ms.
    total_execution_ms: int = 0
    #: Times the engine was asked to run but had nothing to do.
    no_op_count: int = 0
    #: Set when the request is parked for a human.
    escalation_reason: EscalationReason | None = None
    escalated_at: datetime | None = None
    escalation_detail: str | None = None
    #: Set once the success gate has passed end to end.
    completed_at: datetime | None = None
    status_history: list[StatusHistoryEntry] = Field(default_factory=list)

    submitted_at: datetime | None = None
    decided_at: datetime | None = None
    created_at: datetime = Field(default_factory=utc_now)
    updated_at: datetime = Field(default_factory=utc_now)
