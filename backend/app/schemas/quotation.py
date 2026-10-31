"""Request/response schemas for quotation requests, quotations and approvals."""

from datetime import datetime

from pydantic import Field, field_validator

from app.models.common import AppModel, JsonDict, Money, PyObjectId, Rate
from app.models.enums import (
    ApprovalDecision,
    ApprovalStatus,
    EscalationReason,
    QuotationStatus,
    RequestStatus,
    StepStatus,
    WorkflowOutcome,
    WorkflowStep,
)
from app.models.quotation import PartySnapshot
from app.models.quotation_request import (
    PricingSummary,
    RequestLine,
    RuleException,
    StatusHistoryEntry,
)


class RequestItemInput(AppModel):
    """One line as the customer submits it."""

    product_id: PyObjectId
    quantity: int = Field(ge=1, le=1_000_000)
    requested_discount_percent: Rate = Field(default="0", ge=0, le=100)
    notes: str | None = Field(default=None, max_length=500)


class QuotationRequestCreate(AppModel):
    items: list[RequestItemInput] = Field(min_length=1, max_length=50)
    #: Staff only: the customer the request is being keyed in for. A customer
    #: user's own record is used instead and this field is ignored.
    customer_id: PyObjectId | None = None
    expected_delivery_date: datetime | None = None
    customer_notes: str | None = Field(default=None, max_length=1000)
    #: Submit immediately instead of saving a draft.
    submit: bool = True

    @field_validator("items")
    @classmethod
    def _no_duplicate_products(cls, items: list[RequestItemInput]):
        seen = {item.product_id for item in items}
        if len(seen) != len(items):
            raise ValueError(
                "Each product may appear only once; combine duplicate lines into "
                "a single line with the total quantity."
            )
        return items


class QuotationRequestUpdate(AppModel):
    """Edit a draft, or a request sent back for modification."""

    items: list[RequestItemInput] | None = Field(default=None, min_length=1, max_length=50)
    expected_delivery_date: datetime | None = None
    customer_notes: str | None = Field(default=None, max_length=1000)

    @field_validator("items")
    @classmethod
    def _no_duplicate_products(cls, items: list[RequestItemInput] | None):
        if items is None:
            return items
        if len({item.product_id for item in items}) != len(items):
            raise ValueError(
                "Each product may appear only once; combine duplicate lines into "
                "a single line with the total quantity."
            )
        return items


class InternalNoteUpdate(AppModel):
    internal_notes: str = Field(max_length=2000)


class QuotationRequestResponse(AppModel):
    id: PyObjectId
    request_number: str
    customer_id: PyObjectId
    customer_code: str
    customer_name: str
    created_by: PyObjectId
    created_by_role: str
    status: RequestStatus
    items: list[RequestLine]
    pricing: PricingSummary | None = None
    validation_errors: list[str] = Field(default_factory=list)
    exceptions: list[RuleException] = Field(default_factory=list)
    requires_approval: bool
    last_execution_id: PyObjectId | None = None
    approval_id: PyObjectId | None = None
    quotation_id: PyObjectId | None = None
    expected_delivery_date: datetime | None = None
    customer_notes: str | None = None
    internal_notes: str | None = None
    revision: int
    status_history: list[StatusHistoryEntry] = Field(default_factory=list)
    attempt_count: int = 0
    retry_count: int = 0
    total_execution_ms: int = 0
    no_op_count: int = 0
    escalation_reason: EscalationReason | None = None
    escalation_detail: str | None = None
    escalated_at: datetime | None = None
    completed_at: datetime | None = None
    submitted_at: datetime | None = None
    decided_at: datetime | None = None
    created_at: datetime
    updated_at: datetime


class StepExecutionResponse(AppModel):
    step: WorkflowStep
    status: StepStatus
    message: str | None = None
    retries: int = 0
    output: JsonDict = Field(default_factory=dict)
    errors: list[str] = Field(default_factory=list)
    started_at: datetime
    completed_at: datetime | None = None
    duration_ms: int


class WorkflowExecutionResponse(AppModel):
    id: PyObjectId
    request_id: PyObjectId
    request_number: str
    triggered_by: PyObjectId | None = None
    trigger: str
    engine_version: str
    outcome: WorkflowOutcome | None = None
    steps: list[StepExecutionResponse]
    resulting_status: str | None = None
    attempt_number: int = 1
    retries_used: int = 0
    budget: JsonDict = Field(default_factory=dict)
    gate: JsonDict = Field(default_factory=dict)
    escalation_reason: EscalationReason | None = None
    escalation_detail: str | None = None
    started_at: datetime
    completed_at: datetime | None = None
    duration_ms: int


class WorkflowRunResponse(AppModel):
    """What the client gets back after a submission or a re-run."""

    execution_id: PyObjectId
    outcome: WorkflowOutcome
    resulting_status: RequestStatus
    requires_approval: bool
    validation_errors: list[str] = Field(default_factory=list)
    exceptions: list[RuleException] = Field(default_factory=list)
    approval_id: PyObjectId | None = None
    quotation_id: PyObjectId | None = None
    duration_ms: int

    # ---- Workflow boundaries ---------------------------------------------
    #: Which of the six success-gate conditions were satisfied.
    gate: JsonDict = Field(default_factory=dict)
    #: This request's lifetime attempt number.
    attempt_number: int = 1
    #: Transient-failure retries consumed by this run.
    retries_used: int = 0
    escalation_reason: EscalationReason | None = None
    escalation_detail: str | None = None
    #: The checker tool's report, when the document was verified.
    check_report: JsonDict | None = None

    request: QuotationRequestResponse


class QuotationResponse(AppModel):
    id: PyObjectId
    quotation_number: str
    request_id: PyObjectId
    request_number: str
    customer_id: PyObjectId
    seller: PartySnapshot
    buyer: PartySnapshot
    items: list[RequestLine]
    pricing: PricingSummary
    terms: list[str]
    status: QuotationStatus
    verification_code: str
    integrity_hash: str
    approval_id: PyObjectId | None = None
    approved_by: PyObjectId | None = None
    approved_by_name: str | None = None
    auto_approved: bool
    issued_at: datetime
    valid_until: datetime
    pdf_generated_at: datetime | None = None
    download_count: int
    created_at: datetime


class VerificationResponse(AppModel):
    valid: bool
    reason: str | None = None
    quotation_number: str | None = None
    request_number: str | None = None
    customer_name: str | None = None
    issued_at: datetime | None = None
    valid_until: datetime | None = None
    expired: bool | None = None
    status: QuotationStatus | None = None
    currency: str | None = None
    final_amount: Money | None = None
    line_count: int | None = None
    auto_approved: bool | None = None
    approved_by: str | None = None
    integrity_hash: str | None = None


class ApprovalDecisionRequest(AppModel):
    decision: ApprovalDecision
    comments: str | None = Field(default=None, max_length=2000)
    #: Applied to every line in place of the requested discount, on APPROVE only.
    override_discount_percent: Rate | None = Field(default=None, ge=0, le=100)


class ApprovalResponse(AppModel):
    id: PyObjectId
    request_id: PyObjectId
    request_number: str
    customer_id: PyObjectId
    customer_name: str
    status: ApprovalStatus
    exceptions: list[RuleException]
    pricing_snapshot: PricingSummary | None = None
    requested_amount: Money
    requested_discount_percent: Rate
    decision: ApprovalDecision | None = None
    decided_by: PyObjectId | None = None
    decided_by_name: str | None = None
    decided_at: datetime | None = None
    comments: str | None = None
    override_discount_percent: Rate | None = None
    sla_due_at: datetime | None = None
    created_at: datetime
    updated_at: datetime


class ApprovalDecisionResponse(AppModel):
    approval: ApprovalResponse
    request: QuotationRequestResponse
    quotation_id: PyObjectId | None = None
    execution_id: PyObjectId | None = None
