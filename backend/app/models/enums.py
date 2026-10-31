"""Enumerations shared by the data model, the workflow engine and the API."""

from enum import StrEnum


class UserRole(StrEnum):
    CUSTOMER = "CUSTOMER"
    SALES_EMPLOYEE = "SALES_EMPLOYEE"
    SALES_MANAGER = "SALES_MANAGER"


class UserStatus(StrEnum):
    ACTIVE = "ACTIVE"
    SUSPENDED = "SUSPENDED"


class CustomerTier(StrEnum):
    STANDARD = "STANDARD"
    SILVER = "SILVER"
    GOLD = "GOLD"
    PLATINUM = "PLATINUM"


class CustomerStatus(StrEnum):
    ACTIVE = "ACTIVE"
    ON_HOLD = "ON_HOLD"
    BLOCKED = "BLOCKED"


class ProductStatus(StrEnum):
    ACTIVE = "ACTIVE"
    DISCONTINUED = "DISCONTINUED"


class MasterDataEntity(StrEnum):
    """What a sales employee is asking to have added to the master data."""

    CUSTOMER = "CUSTOMER"
    PRODUCT = "PRODUCT"


class MasterDataRequestStatus(StrEnum):
    PENDING = "PENDING"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"
    #: Withdrawn by the employee who raised it, before a manager decided.
    WITHDRAWN = "WITHDRAWN"


#: A request in one of these statuses has been settled and cannot be decided
#: again; the second decision is refused rather than silently overwriting the
#: first.
SETTLED_MASTER_DATA_STATUSES = {
    MasterDataRequestStatus.APPROVED,
    MasterDataRequestStatus.REJECTED,
    MasterDataRequestStatus.WITHDRAWN,
}


class RequestStatus(StrEnum):
    """Lifecycle of a quotation request."""

    DRAFT = "DRAFT"
    SUBMITTED = "SUBMITTED"
    UNDER_VALIDATION = "UNDER_VALIDATION"
    VALIDATION_FAILED = "VALIDATION_FAILED"
    PRICED = "PRICED"
    PENDING_APPROVAL = "PENDING_APPROVAL"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"
    MODIFICATION_REQUESTED = "MODIFICATION_REQUESTED"
    #: The success gate passed: document generated and independently verified.
    COMPLETED = "COMPLETED"
    #: Parked for a human because the workflow cannot proceed on its own.
    ESCALATED = "ESCALATED"
    CANCELLED = "CANCELLED"


#: Statuses that accept no further transition, named before the table below so
#: the escalation pass can skip them.
TERMINAL_CANDIDATES = {
    RequestStatus.COMPLETED,
    RequestStatus.REJECTED,
    RequestStatus.CANCELLED,
    RequestStatus.ESCALATED,
}

#: Allowed state transitions. The workflow engine refuses anything not listed
#: here, which keeps the lifecycle auditable and makes illegal states
#: unreachable regardless of which API route is called.
REQUEST_TRANSITIONS: dict[RequestStatus, set[RequestStatus]] = {
    RequestStatus.DRAFT: {RequestStatus.SUBMITTED, RequestStatus.CANCELLED},
    RequestStatus.SUBMITTED: {
        RequestStatus.UNDER_VALIDATION,
        RequestStatus.CANCELLED,
    },
    RequestStatus.UNDER_VALIDATION: {
        RequestStatus.VALIDATION_FAILED,
        RequestStatus.PRICED,
    },
    RequestStatus.VALIDATION_FAILED: {
        RequestStatus.SUBMITTED,
        RequestStatus.CANCELLED,
    },
    RequestStatus.PRICED: {
        RequestStatus.PENDING_APPROVAL,
        RequestStatus.APPROVED,
        RequestStatus.CANCELLED,
    },
    RequestStatus.PENDING_APPROVAL: {
        RequestStatus.APPROVED,
        RequestStatus.REJECTED,
        RequestStatus.MODIFICATION_REQUESTED,
        RequestStatus.CANCELLED,
        # Reachable when the approval re-run finds the request no longer valid,
        # e.g. a product was discontinued while the task sat in the queue.
        RequestStatus.VALIDATION_FAILED,
    },
    RequestStatus.MODIFICATION_REQUESTED: {
        RequestStatus.SUBMITTED,
        RequestStatus.CANCELLED,
    },
    # APPROVED is not terminal: the document still has to be generated and
    # independently verified before the request may be COMPLETED.
    RequestStatus.APPROVED: {
        RequestStatus.COMPLETED,
    },
    RequestStatus.ESCALATED: {
        RequestStatus.SUBMITTED,
        RequestStatus.COMPLETED,
        RequestStatus.REJECTED,
        RequestStatus.CANCELLED,
    },
    RequestStatus.COMPLETED: set(),
    RequestStatus.REJECTED: set(),
    RequestStatus.CANCELLED: set(),
}

# Escalation parks a request for a human, and the engine can hit an escalation
# condition at any point - including before validation, when a budget is
# already spent. So ESCALATED is reachable from every live status rather than
# from a hand-picked few; an earlier version omitted SUBMITTED and left such a
# request stranded with a reason recorded but its status unchanged.
for _live in set(RequestStatus) - TERMINAL_CANDIDATES:
    REQUEST_TRANSITIONS[_live].add(RequestStatus.ESCALATED)
del _live

#: Statuses from which no further transition is possible.
TERMINAL_REQUEST_STATUSES = {
    RequestStatus.COMPLETED,
    RequestStatus.REJECTED,
    RequestStatus.CANCELLED,
}

#: Statuses that mean "the workflow has nothing left to do here". Re-running the
#: pipeline on one of these is a no-op rather than an error.
SETTLED_REQUEST_STATUSES = TERMINAL_REQUEST_STATUSES | {RequestStatus.ESCALATED}


class QuotationStatus(StrEnum):
    ISSUED = "ISSUED"
    EXPIRED = "EXPIRED"
    ACCEPTED = "ACCEPTED"
    WITHDRAWN = "WITHDRAWN"


class ApprovalStatus(StrEnum):
    PENDING = "PENDING"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"
    MODIFICATION_REQUESTED = "MODIFICATION_REQUESTED"


class ApprovalDecision(StrEnum):
    APPROVE = "APPROVE"
    REJECT = "REJECT"
    REQUEST_MODIFICATION = "REQUEST_MODIFICATION"


class WorkflowStep(StrEnum):
    """The deterministic pipeline executed for every submitted request."""

    VALIDATE_REQUEST = "VALIDATE_REQUEST"
    CHECK_AVAILABILITY = "CHECK_AVAILABILITY"
    CALCULATE_PRICING = "CALCULATE_PRICING"
    EVALUATE_DISCOUNT_RULES = "EVALUATE_DISCOUNT_RULES"
    DETERMINE_APPROVAL_ROUTE = "DETERMINE_APPROVAL_ROUTE"
    #: The action tool: issue the quotation and render its PDF.
    GENERATE_DOCUMENT = "GENERATE_DOCUMENT"
    #: The checker tool: independently recalculate and verify the result.
    VERIFY_DOCUMENT = "VERIFY_DOCUMENT"
    FINALISE = "FINALISE"


#: Canonical execution order of the pipeline.
WORKFLOW_PIPELINE: tuple[WorkflowStep, ...] = (
    WorkflowStep.VALIDATE_REQUEST,
    WorkflowStep.CHECK_AVAILABILITY,
    WorkflowStep.CALCULATE_PRICING,
    WorkflowStep.EVALUATE_DISCOUNT_RULES,
    WorkflowStep.DETERMINE_APPROVAL_ROUTE,
    WorkflowStep.GENERATE_DOCUMENT,
    WorkflowStep.VERIFY_DOCUMENT,
    WorkflowStep.FINALISE,
)


class StepStatus(StrEnum):
    SUCCESS = "SUCCESS"
    FAILED = "FAILED"
    SKIPPED = "SKIPPED"


class WorkflowOutcome(StrEnum):
    #: The success gate passed end to end: document issued and verified.
    COMPLETED = "COMPLETED"
    AUTO_APPROVED = "AUTO_APPROVED"
    PENDING_APPROVAL = "PENDING_APPROVAL"
    VALIDATION_FAILED = "VALIDATION_FAILED"
    #: Parked for a human; see the execution's escalation_reason.
    ESCALATED = "ESCALATED"
    #: Nothing left to do - the request was already settled.
    NO_OP = "NO_OP"
    #: A configured execution budget was reached before the work finished.
    BUDGET_EXCEEDED = "BUDGET_EXCEEDED"


class FailureClass(StrEnum):
    """Whether a failure is worth retrying.

    Only TRANSIENT failures are retried. A PERMANENT failure is a verdict - the
    input or the policy says no - and retrying it would just burn the budget to
    reach the same answer.
    """

    TRANSIENT = "TRANSIENT"
    PERMANENT = "PERMANENT"


class EscalationReason(StrEnum):
    """Why a request was parked for a human."""

    MISSING_CUSTOMER_INFORMATION = "MISSING_CUSTOMER_INFORMATION"
    PRODUCT_UNAVAILABLE = "PRODUCT_UNAVAILABLE"
    DISCOUNT_EXCEPTION = "DISCOUNT_EXCEPTION"
    MANAGER_REJECTION = "MANAGER_REJECTION"
    REPEATED_PROCESSING_FAILURE = "REPEATED_PROCESSING_FAILURE"
    VERIFICATION_MISMATCH = "VERIFICATION_MISMATCH"
    BUDGET_EXCEEDED = "BUDGET_EXCEEDED"


class AvailabilityStatus(StrEnum):
    IN_STOCK = "IN_STOCK"
    PARTIAL = "PARTIAL"
    OUT_OF_STOCK = "OUT_OF_STOCK"


class ExceptionType(StrEnum):
    """Reasons a request cannot be auto-approved."""

    DISCOUNT_LIMIT_EXCEEDED = "DISCOUNT_LIMIT_EXCEEDED"
    ORDER_VALUE_THRESHOLD = "ORDER_VALUE_THRESHOLD"
    CREDIT_LIMIT_EXCEEDED = "CREDIT_LIMIT_EXCEEDED"
    STOCK_SHORTFALL = "STOCK_SHORTFALL"


class AuditAction(StrEnum):
    USER_REGISTERED = "USER_REGISTERED"
    USER_LOGGED_IN = "USER_LOGGED_IN"
    CUSTOMER_CREATED = "CUSTOMER_CREATED"
    CUSTOMER_UPDATED = "CUSTOMER_UPDATED"
    MASTER_DATA_REQUESTED = "MASTER_DATA_REQUESTED"
    MASTER_DATA_APPROVED = "MASTER_DATA_APPROVED"
    MASTER_DATA_REJECTED = "MASTER_DATA_REJECTED"
    MASTER_DATA_WITHDRAWN = "MASTER_DATA_WITHDRAWN"
    PRODUCT_CREATED = "PRODUCT_CREATED"
    PRODUCT_UPDATED = "PRODUCT_UPDATED"
    PRODUCT_DELETED = "PRODUCT_DELETED"
    REQUEST_CREATED = "REQUEST_CREATED"
    REQUEST_UPDATED = "REQUEST_UPDATED"
    REQUEST_SUBMITTED = "REQUEST_SUBMITTED"
    REQUEST_CANCELLED = "REQUEST_CANCELLED"
    WORKFLOW_EXECUTED = "WORKFLOW_EXECUTED"
    WORKFLOW_RETRIED = "WORKFLOW_RETRIED"
    WORKFLOW_NO_OP = "WORKFLOW_NO_OP"
    WORKFLOW_ESCALATED = "WORKFLOW_ESCALATED"
    WORKFLOW_BUDGET_EXCEEDED = "WORKFLOW_BUDGET_EXCEEDED"
    QUOTATION_VERIFICATION_FAILED = "QUOTATION_VERIFICATION_FAILED"
    APPROVAL_DECIDED = "APPROVAL_DECIDED"
    QUOTATION_GENERATED = "QUOTATION_GENERATED"
    QUOTATION_DOWNLOADED = "QUOTATION_DOWNLOADED"
    QUOTATION_VERIFIED = "QUOTATION_VERIFIED"
    SETTINGS_UPDATED = "SETTINGS_UPDATED"


class NotificationType(StrEnum):
    REQUEST_SUBMITTED = "REQUEST_SUBMITTED"
    VALIDATION_FAILED = "VALIDATION_FAILED"
    APPROVAL_REQUIRED = "APPROVAL_REQUIRED"
    QUOTATION_READY = "QUOTATION_READY"
    REQUEST_REJECTED = "REQUEST_REJECTED"
    MODIFICATION_REQUESTED = "MODIFICATION_REQUESTED"
    WORKFLOW_ESCALATED = "WORKFLOW_ESCALATED"
    #: An employee is asking a manager to authorise new master data.
    MASTER_DATA_REQUESTED = "MASTER_DATA_REQUESTED"
    #: The manager has decided; the employee who asked is told either way.
    MASTER_DATA_DECIDED = "MASTER_DATA_DECIDED"


class NotificationChannel(StrEnum):
    IN_APP = "IN_APP"
