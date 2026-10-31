"""`approvals` collection - one task per request that needs a manager decision."""

from datetime import datetime

from pydantic import Field

from app.models.common import DocumentModel, Money, PyObjectId, Rate, utc_now
from app.models.enums import ApprovalDecision, ApprovalStatus
from app.models.quotation_request import PricingSummary, RuleException


class Approval(DocumentModel):
    request_id: PyObjectId
    request_number: str
    customer_id: PyObjectId
    customer_name: str

    status: ApprovalStatus = ApprovalStatus.PENDING
    #: Snapshot of the exceptions that forced the review, so the task stays
    #: meaningful even after the request is edited and re-run.
    exceptions: list[RuleException] = Field(default_factory=list)
    pricing_snapshot: PricingSummary | None = None
    requested_amount: Money = Field(default="0.00")
    requested_discount_percent: Rate = Field(default="0")

    decision: ApprovalDecision | None = None
    decided_by: PyObjectId | None = None
    decided_by_name: str | None = None
    decided_at: datetime | None = None
    comments: str | None = None
    #: Manager-imposed discount applied to every line in place of the request.
    override_discount_percent: Rate | None = None

    #: Deadline derived from approval_sla_hours; feeds the analytics SLA metric.
    sla_due_at: datetime | None = None
    created_at: datetime = Field(default_factory=utc_now)
    updated_at: datetime = Field(default_factory=utc_now)

    @property
    def is_open(self) -> bool:
        return self.status == ApprovalStatus.PENDING
