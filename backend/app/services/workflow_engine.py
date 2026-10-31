"""The deterministic quotation workflow.

Every submitted request runs through the same six-step pipeline, in the same
order, with every decision recorded in ``workflow_executions``:

1. ``VALIDATE_REQUEST``        - structural and commercial validity.
2. ``CHECK_AVAILABILITY``      - stock position per line.
3. ``CALCULATE_PRICING``       - the arithmetic (Decimal throughout).
4. ``EVALUATE_DISCOUNT_RULES`` - policy judgement on the discounts asked for.
5. ``DETERMINE_APPROVAL_ROUTE``- auto-approve, or raise a manager task.
6. ``FINALISE``                - persist the outcome and notify.

Steps 3 and 4 are deliberately separate: step 3 only computes numbers, step 4
only applies policy to them. That split keeps the arithmetic testable without a
rule book and the rules testable without re-deriving totals.

There is no AI or inference anywhere in this module. Identical inputs always
produce an identical execution trace.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import timedelta
from decimal import Decimal

from app.core.exceptions import NotFoundError, WorkflowError
from app.db.mongo import Collections, get_collection
from app.models.approval import Approval
from app.models.common import object_id, utc_now
from app.models.company_settings import CompanySettings
from app.models.customer import Customer
from app.models.enums import (
    REQUEST_TRANSITIONS,
    SETTLED_REQUEST_STATUSES,
    WORKFLOW_PIPELINE,
    ApprovalStatus,
    AuditAction,
    CustomerStatus,
    EscalationReason,
    ExceptionType,
    NotificationType,
    ProductStatus,
    RequestStatus,
    StepStatus,
    UserRole,
    WorkflowOutcome,
    WorkflowStep,
)
from app.models.quotation_request import (
    PricingSummary,
    QuotationRequest,
    RuleException,
    StatusHistoryEntry,
)
from app.models.workflow import ENGINE_VERSION, StepExecution, WorkflowExecution
from app.services import (
    action_tool,
    audit_service,
    availability_service,
    checker_tool,
    notification_service,
    pricing_engine,
    product_service,
    settings_service,
)
from app.services.discount_engine import (
    DiscountEvaluation,
    DiscountVerdict,
    evaluate_line_discount,
)
from app.services.execution_budget import BudgetExceeded, ExecutionBudget
from app.utils.money import ZERO, decode_decimals, encode_decimals, rate, to_decimal

logger = logging.getLogger(__name__)


#: The six conditions that must all hold before a request may be COMPLETED.
#: Declared as data so the gate is auditable: the engine records the state of
#: each one on the execution, and a request cannot reach COMPLETED with any of
#: them false.
SUCCESS_GATE_CONDITIONS = (
    "input_validation_passed",
    "product_verification_passed",
    "pricing_validation_passed",
    "approval_recorded",
    "document_generated",
    "independent_verification_passed",
)


def empty_gate() -> dict:
    """Every gate condition unproven - the state before any step has run."""
    return dict.fromkeys(SUCCESS_GATE_CONDITIONS, False)


def evaluate_success_gate(gate: dict) -> tuple[bool, list[str]]:
    """``(passed, unmet)`` for a gate state.

    A condition that was never evaluated counts as unmet - the gate is
    allow-on-proof, not allow-by-default.
    """
    unmet = [name for name in SUCCESS_GATE_CONDITIONS if not gate.get(name)]
    return (not unmet), unmet


async def _reload(request_id: str) -> QuotationRequest:
    """Re-read a request so the returned model matches what was stored.

    The pipeline mutates its in-memory copy as it goes; re-reading at the end
    means callers can never observe a response that disagrees with the database
    (status history and quotation_id in particular are written by later steps).
    """
    raw = await get_collection(Collections.QUOTATION_REQUESTS).find_one(
        {"_id": object_id(request_id)}
    )
    if raw is None:
        raise NotFoundError("Quotation request not found.")
    return QuotationRequest.from_mongo(decode_decimals(raw))


def assert_transition(current: RequestStatus, target: RequestStatus) -> None:
    """Refuse any transition the state machine does not allow."""
    allowed = REQUEST_TRANSITIONS.get(RequestStatus(current), set())
    if RequestStatus(target) not in allowed:
        raise WorkflowError(
            f"A request in status {current} cannot move to {target}.",
            details={
                "current_status": current,
                "requested_status": target,
                "allowed": sorted(status.value for status in allowed),
            },
        )


@dataclass(slots=True)
class WorkflowResult:
    """What one pipeline run produced."""

    execution_id: str
    outcome: WorkflowOutcome
    resulting_status: RequestStatus
    request: QuotationRequest
    steps: list[StepExecution] = field(default_factory=list)
    approval_id: str | None = None
    quotation_id: str | None = None
    validation_errors: list[str] = field(default_factory=list)
    exceptions: list[RuleException] = field(default_factory=list)

    # ---- Boundary controls ------------------------------------------------
    attempt_number: int = 1
    retries_used: int = 0
    #: Which success-gate conditions were satisfied; see SUCCESS_GATE_CONDITIONS.
    gate: dict = field(default_factory=dict)
    escalation_reason: EscalationReason | None = None
    escalation_detail: str | None = None
    #: The checker tool's report, when the document was verified.
    check_report: dict | None = None

    @property
    def duration_ms(self) -> int:
        return sum(step.duration_ms for step in self.steps)

    @property
    def completed(self) -> bool:
        return self.resulting_status == RequestStatus.COMPLETED

    @property
    def escalated(self) -> bool:
        return self.resulting_status == RequestStatus.ESCALATED


class _StepRecorder:
    """Collects per-step timing and output into :class:`StepExecution` records."""

    def __init__(self) -> None:
        self.steps: list[StepExecution] = []

    def start(self, step: WorkflowStep) -> StepExecution:
        execution = StepExecution(step=step, status=StepStatus.SUCCESS)
        self.steps.append(execution)
        return execution

    @staticmethod
    def finish(
        execution: StepExecution,
        *,
        status: StepStatus = StepStatus.SUCCESS,
        message: str | None = None,
        output: dict | None = None,
        errors: list[str] | None = None,
        retries: int = 0,
    ) -> StepExecution:
        execution.status = status
        execution.message = message
        execution.output = output or {}
        execution.errors = errors or []
        execution.retries = retries
        execution.completed_at = utc_now()
        delta = execution.completed_at - execution.started_at
        execution.duration_ms = max(int(delta.total_seconds() * 1000), 0)
        return execution

    def skip(self, step: WorkflowStep, reason: str) -> StepExecution:
        execution = self.start(step)
        return self.finish(execution, status=StepStatus.SKIPPED, message=reason)


async def execute(
    request_id: str,
    *,
    triggered_by: str | None = None,
    trigger: str = "SUBMISSION",
    override_discount_percent: Decimal | None = None,
    auto_approve: bool = False,
) -> WorkflowResult:
    """Run the pipeline for one request and persist everything it decided.

    ``override_discount_percent`` and ``auto_approve`` are set when a manager
    approves a request: the pipeline is re-run so the final quotation is priced
    by the same code path as every other quotation, rather than by a special case
    in the approval handler.
    """
    requests = get_collection(Collections.QUOTATION_REQUESTS)
    raw_request = await requests.find_one({"_id": object_id(request_id)})
    if raw_request is None:
        raise NotFoundError("Quotation request not found.")

    request = QuotationRequest.from_mongo(decode_decimals(raw_request))
    settings_doc = await settings_service.get_settings_document()
    recorder = _StepRecorder()
    started_at = utc_now()

    # ---- No-op condition --------------------------------------------------
    # A settled request has nothing left for the engine to do. Running the
    # pipeline again would burn budget and could issue a second document, so
    # the run stops here and records why.
    if RequestStatus(request.status) in SETTLED_REQUEST_STATUSES:
        return await _finalise_no_op(
            request, recorder, triggered_by, trigger, started_at
        )

    # ---- Budget limit -----------------------------------------------------
    budget = ExecutionBudget(
        policy=settings_doc.execution_policy,
        attempt_number=request.attempt_count + 1,
        prior_elapsed_ms=request.total_execution_ms,
    )
    spent, reason = budget.exceeded()
    if spent:
        return await _finalise_escalation(
            request,
            recorder,
            reason=EscalationReason.BUDGET_EXCEEDED,
            detail=reason or "The execution budget is exhausted.",
            outcome=WorkflowOutcome.BUDGET_EXCEEDED,
            triggered_by=triggered_by,
            trigger=trigger,
            started_at=started_at,
            budget=budget,
            gate=empty_gate(),
        )

    # This attempt is now committed, so it counts even if the process dies.
    await requests.update_one(
        {"_id": object_id(request_id)}, {"$inc": {"attempt_count": 1}}
    )
    request.attempt_count = budget.attempt_number

    # Any run that starts from SUBMITTED enters validation first - that covers a
    # fresh submission and a staff reprocess alike. Gating this on the *status*
    # rather than the trigger name matters: a reprocess that skipped the hop
    # stayed on SUBMITTED, and the state machine then refused the legitimate
    # SUBMITTED -> VALIDATION_FAILED move if the re-run failed validation again.
    # An approval re-run keeps its PENDING_APPROVAL status and is closed out by
    # the finalise step.
    if RequestStatus(request.status) == RequestStatus.SUBMITTED:
        assert_transition(RequestStatus(request.status), RequestStatus.UNDER_VALIDATION)
        await requests.update_one(
            {"_id": object_id(request_id)},
            {
                "$set": {
                    "status": RequestStatus.UNDER_VALIDATION.value,
                    "updated_at": started_at,
                }
            },
        )
        request.status = RequestStatus.UNDER_VALIDATION

    # ---- Step 1: validation -------------------------------------------------
    step = recorder.start(WorkflowStep.VALIDATE_REQUEST)
    # Retried on a transient database fault. Steps 3-5 are pure arithmetic over
    # data already in memory, so they are deliberately not retried - a retry
    # would recompute the identical answer.
    retries_before = budget.retries_used
    try:
        customer, products, validation_errors = await budget.run_step(
            WorkflowStep.VALIDATE_REQUEST.value,
            lambda: _validate_request(request, settings_doc),
        )
    except BudgetExceeded as error:
        # The budget ran out mid-step. Park the request rather than leaving the
        # caller with an unhandled fault.
        recorder.finish(
            step,
            status=StepStatus.FAILED,
            message="The execution budget ran out during validation.",
            errors=[str(error)],
            retries=budget.retries_used - retries_before,
        )
        return await _finalise_escalation(
            request,
            recorder,
            reason=EscalationReason.BUDGET_EXCEEDED,
            detail=str(error),
            outcome=WorkflowOutcome.BUDGET_EXCEEDED,
            triggered_by=triggered_by,
            trigger=trigger,
            started_at=started_at,
            budget=budget,
            gate=empty_gate(),
        )
    except Exception as error:  # noqa: BLE001 - recorded, then escalated
        # A transient fault that survived every retry is an infrastructure
        # problem, not a verdict on the request. It is recorded and escalated so
        # the information is preserved and a human is told, rather than
        # surfacing to the submitter as an unhandled server error.
        consumed = budget.retries_used - retries_before
        recorder.finish(
            step,
            status=StepStatus.FAILED,
            message="Validation could not be completed.",
            errors=[f"{type(error).__name__}: {error}"],
            retries=consumed,
        )
        logger.exception("Validation failed for %s", request.request_number)
        return await _finalise_escalation(
            request,
            recorder,
            reason=EscalationReason.REPEATED_PROCESSING_FAILURE,
            detail=(
                f"Validation could not be completed after {consumed} retry(ies): "
                f"{error}"
            ),
            outcome=WorkflowOutcome.ESCALATED,
            triggered_by=triggered_by,
            trigger=trigger,
            started_at=started_at,
            budget=budget,
            gate=empty_gate(),
        )
    validate_retries = budget.retries_used - retries_before
    if validation_errors:
        recorder.finish(
            step,
            status=StepStatus.FAILED,
            message=f"{len(validation_errors)} validation issue(s) found.",
            output={"checked_lines": len(request.items)},
            errors=validation_errors,
            retries=validate_retries,
        )
        for remaining in (
            WorkflowStep.CHECK_AVAILABILITY,
            WorkflowStep.CALCULATE_PRICING,
            WorkflowStep.EVALUATE_DISCOUNT_RULES,
            WorkflowStep.DETERMINE_APPROVAL_ROUTE,
            WorkflowStep.GENERATE_DOCUMENT,
            WorkflowStep.VERIFY_DOCUMENT,
        ):
            recorder.skip(remaining, "Skipped because validation failed.")
        return await _finalise_validation_failure(
            request,
            recorder,
            validation_errors,
            triggered_by,
            trigger,
            started_at,
            budget,
        )

    recorder.finish(
        step,
        message=f"Validated {len(request.items)} line(s) for {customer.company_name}.",
        output={
            "customer_code": customer.code,
            "customer_tier": customer.tier,
            "line_count": len(request.items),
        },
        retries=validate_retries,
    )

    # ---- Step 2: availability ----------------------------------------------
    step = recorder.start(WorkflowStep.CHECK_AVAILABILITY)
    allow_backorder = settings_doc.quotation_policy.allow_backorder
    availability_errors: list[str] = []
    shortfall_lines: list[dict] = []

    for line in request.items:
        product = products[line.product_id]
        availability = availability_service.evaluate(
            product, line.quantity, allow_backorder=allow_backorder
        )
        line.availability = availability
        if availability.shortfall > 0:
            shortfall_lines.append(
                {
                    "sku": line.sku,
                    "requested": line.quantity,
                    "available": availability.available_quantity,
                    "shortfall": availability.shortfall,
                    "lead_time_days": availability.lead_time_days,
                }
            )
            if not allow_backorder:
                availability_errors.append(
                    f"{line.sku}: only {availability.available_quantity} of "
                    f"{line.quantity} {product.unit} are available and backorders "
                    f"are not permitted."
                )

    if availability_errors:
        recorder.finish(
            step,
            status=StepStatus.FAILED,
            message="One or more lines cannot be fulfilled.",
            output={"shortfall_lines": shortfall_lines},
            errors=availability_errors,
        )
        for remaining in (
            WorkflowStep.CALCULATE_PRICING,
            WorkflowStep.EVALUATE_DISCOUNT_RULES,
            WorkflowStep.DETERMINE_APPROVAL_ROUTE,
            WorkflowStep.GENERATE_DOCUMENT,
            WorkflowStep.VERIFY_DOCUMENT,
        ):
            recorder.skip(remaining, "Skipped because the availability check failed.")
        return await _finalise_validation_failure(
            request,
            recorder,
            availability_errors,
            triggered_by,
            trigger,
            started_at,
            budget,
        )

    recorder.finish(
        step,
        message=(
            "All lines are available from stock."
            if not shortfall_lines
            else f"{len(shortfall_lines)} line(s) require a backorder."
        ),
        output={
            "shortfall_lines": shortfall_lines,
            "backorder_allowed": allow_backorder,
        },
    )

    # ---- Step 3: pricing ----------------------------------------------------
    step = recorder.start(WorkflowStep.CALCULATE_PRICING)
    evaluations = _price_lines(
        request,
        products,
        customer,
        settings_doc,
        override_discount_percent=override_discount_percent,
    )
    totals = pricing_engine.summarise_lines(
        [line.model_dump() for line in request.items],
        currency=settings_doc.quotation_policy.currency,
        tax_label=settings_doc.tax_policy.name,
    )
    request.pricing = PricingSummary.model_validate(totals.as_dict())

    recorder.finish(
        step,
        message=(
            f"Priced {totals.line_count} line(s): "
            f"{settings_doc.quotation_policy.currency} {totals.final_amount}."
        ),
        output={
            "subtotal": totals.subtotal,
            "total_discount": totals.total_discount,
            "taxable_amount": totals.taxable_amount,
            "total_tax": totals.total_tax,
            "final_amount": totals.final_amount,
            "effective_discount_percent": totals.effective_discount_percent,
            "tax_label": totals.tax_label,
        },
    )

    # ---- Step 4: discount rules --------------------------------------------
    step = recorder.start(WorkflowStep.EVALUATE_DISCOUNT_RULES)
    discount_errors, discount_exceptions, rule_trace = _apply_discount_rules(
        request, evaluations
    )

    if discount_errors:
        recorder.finish(
            step,
            status=StepStatus.FAILED,
            message="One or more requested discounts breach company policy.",
            output={"rules": rule_trace},
            errors=discount_errors,
        )
        for remaining in (
            WorkflowStep.DETERMINE_APPROVAL_ROUTE,
            WorkflowStep.GENERATE_DOCUMENT,
            WorkflowStep.VERIFY_DOCUMENT,
        ):
            recorder.skip(remaining, "Skipped because a discount breached policy.")
        return await _finalise_validation_failure(
            request,
            recorder,
            discount_errors,
            triggered_by,
            trigger,
            started_at,
            budget,
        )

    recorder.finish(
        step,
        message=(
            "All requested discounts are within policy."
            if not discount_exceptions
            else f"{len(discount_exceptions)} line(s) exceed the discount ceiling."
        ),
        output={"rules": rule_trace, "exception_count": len(discount_exceptions)},
    )

    # ---- Step 5: approval routing ------------------------------------------
    step = recorder.start(WorkflowStep.DETERMINE_APPROVAL_ROUTE)
    exceptions = list(discount_exceptions)
    exceptions.extend(
        _evaluate_non_discount_exceptions(
            request, customer, settings_doc, shortfall_lines
        )
    )
    requires_approval = bool(exceptions) and not auto_approve

    request.exceptions = exceptions
    request.requires_approval = requires_approval

    recorder.finish(
        step,
        message=(
            "Manager approval is required."
            if requires_approval
            else "No exceptions raised; the request can be approved automatically."
        ),
        output={
            "requires_approval": requires_approval,
            "exception_types": [exception.type for exception in exceptions],
            "auto_approve_override": auto_approve,
        },
    )

    # ---- Step 6: finalise ---------------------------------------------------
    return await _finalise_success(
        request=request,
        customer=customer,
        settings_doc=settings_doc,
        recorder=recorder,
        requires_approval=requires_approval,
        exceptions=exceptions,
        triggered_by=triggered_by,
        trigger=trigger,
        started_at=started_at,
        budget=budget,
    )


async def _validate_request(
    request: QuotationRequest,
    settings_doc: CompanySettings,
) -> tuple[Customer | None, dict, list[str]]:
    """Check the customer, the products, the line structure and the limits."""
    errors: list[str] = []
    limits = settings_doc.execution_policy

    raw_customer = await get_collection(Collections.CUSTOMERS).find_one(
        {"_id": object_id(request.customer_id)}
    )
    if raw_customer is None:
        return None, {}, ["The customer on this request no longer exists."]

    customer = Customer.from_mongo(decode_decimals(raw_customer))

    # Missing customer information is an escalation condition in its own right:
    # a quotation cannot be addressed to a party we cannot identify or contact.
    missing = [
        label
        for label, value in (
            ("company name", customer.company_name),
            ("contact name", customer.contact_name),
            ("email address", customer.email),
            ("telephone number", customer.phone),
        )
        if not (value or "").strip()
    ]
    if missing:
        errors.append(
            f"Customer {customer.code} is missing required information: "
            f"{', '.join(missing)}. A quotation cannot be addressed without it."
        )

    if customer.status == CustomerStatus.BLOCKED:
        errors.append(
            f"Customer {customer.code} is blocked and cannot be quoted. "
            f"Contact the sales manager."
        )
    elif customer.status == CustomerStatus.ON_HOLD:
        errors.append(
            f"Customer {customer.code} is on hold; the account must be reactivated "
            f"before a quotation can be issued."
        )

    if not request.items:
        errors.append("A quotation request must contain at least one product line.")
        return customer, {}, errors

    # Resource ceilings from execution_policy. These bound the work one request
    # can ask the engine to do, which is the other half of a budget limit.
    if len(request.items) > limits.max_lines_per_request:
        errors.append(
            f"This request has {len(request.items)} lines, above the "
            f"{limits.max_lines_per_request} permitted on one quotation."
        )
        return customer, {}, errors

    seen: set[str] = set()
    for index, line in enumerate(request.items, start=1):
        if line.quantity < 1:
            errors.append(f"Line {index} ({line.sku}): the quantity must be at least 1.")
        elif line.quantity > limits.max_quantity_per_line:
            errors.append(
                f"Line {index} ({line.sku}): a quantity of {line.quantity} exceeds "
                f"the {limits.max_quantity_per_line} permitted on one line."
            )
        if line.product_id in seen:
            errors.append(
                f"Line {index} ({line.sku}): this product appears more than once. "
                f"Combine the quantities into a single line."
            )
        seen.add(line.product_id)

    products = await product_service.get_products_by_ids(
        [line.product_id for line in request.items]
    )
    for index, line in enumerate(request.items, start=1):
        product = products.get(line.product_id)
        if product is None:
            errors.append(
                f"Line {index}: the product referenced by this line no longer exists."
            )
        elif product.status != ProductStatus.ACTIVE:
            errors.append(
                f"Line {index} ({product.sku}): this product has been discontinued "
                f"and cannot be quoted."
            )

    return customer, products, errors


def _price_lines(
    request: QuotationRequest,
    products: dict,
    customer: Customer,
    settings_doc: CompanySettings,
    *,
    override_discount_percent: Decimal | None = None,
) -> dict[str, DiscountEvaluation]:
    """Resolve each line's discount ceiling, then compute its amounts.

    Mutates ``request.items`` in place and returns the per-line discount
    evaluations for step 4 to judge.
    """
    evaluations: dict[str, DiscountEvaluation] = {}
    default_tax = settings_doc.tax_policy.rate_percent

    for line in request.items:
        product = products[line.product_id]

        # Re-read the catalogue price and name at pricing time: a request keyed
        # last week must be quoted at today's price, not a stale copy.
        line.unit_price = product.unit_price
        line.sku = product.sku
        line.name = product.name
        line.unit = product.unit

        evaluation = evaluate_line_discount(
            quantity=line.quantity,
            requested_percent=line.requested_discount_percent,
            unit_price=product.unit_price,
            cost_price=product.cost_price,
            customer_tier=customer.tier,
            policy=settings_doc.discount_policy,
            product_max_percent=product.max_discount_percent,
            override_percent=override_discount_percent,
        )
        evaluations[line.product_id] = evaluation

        line.max_allowed_discount_percent = evaluation.max_allowed_percent
        line.applied_discount_percent = evaluation.applied_percent
        line.discount_exception = evaluation.verdict == DiscountVerdict.NEEDS_APPROVAL

        tax_rate = pricing_engine.resolve_tax_rate(product.tax_rate, default_tax)
        amounts = pricing_engine.price_line(
            unit_price=product.unit_price,
            quantity=line.quantity,
            discount_percent=evaluation.applied_percent,
            tax_rate=tax_rate,
        )
        for field_name, value in amounts.as_dict().items():
            setattr(line, field_name, value)

    return evaluations


def _apply_discount_rules(
    request: QuotationRequest, evaluations: dict[str, DiscountEvaluation]
) -> tuple[list[str], list[RuleException], list[dict]]:
    """Turn the per-line discount verdicts into errors and exceptions."""
    errors: list[str] = []
    exceptions: list[RuleException] = []
    trace: list[dict] = []

    for line in request.items:
        evaluation = evaluations[line.product_id]
        trace.append(
            {
                "sku": line.sku,
                "quantity": line.quantity,
                **evaluation.as_context(),
                "reasons": evaluation.reasons,
            }
        )

        if evaluation.verdict == DiscountVerdict.REJECTED:
            errors.extend(f"{line.sku}: {reason}" for reason in evaluation.reasons)
        elif evaluation.verdict == DiscountVerdict.NEEDS_APPROVAL:
            exceptions.append(
                RuleException(
                    type=ExceptionType.DISCOUNT_LIMIT_EXCEEDED,
                    message=(
                        f"{line.sku}: a {evaluation.applied_percent}% discount was "
                        f"requested on {line.quantity} unit(s), above the "
                        f"{evaluation.max_allowed_percent}% ceiling."
                    ),
                    context={
                        "sku": line.sku,
                        "product_id": line.product_id,
                        "quantity": line.quantity,
                        **evaluation.as_context(),
                    },
                )
            )

    return errors, exceptions, trace


def _evaluate_non_discount_exceptions(
    request: QuotationRequest,
    customer: Customer,
    settings_doc: CompanySettings,
    shortfall_lines: list[dict],
) -> list[RuleException]:
    """Order value, credit exposure and stock shortfall checks."""
    policy = settings_doc.approval_policy
    exceptions: list[RuleException] = []
    final_amount = request.pricing.final_amount if request.pricing else ZERO
    currency = settings_doc.quotation_policy.currency

    threshold = to_decimal(policy.order_value_threshold)
    if threshold > ZERO and final_amount >= threshold:
        exceptions.append(
            RuleException(
                type=ExceptionType.ORDER_VALUE_THRESHOLD,
                message=(
                    f"The quotation total of {currency} {final_amount} reaches the "
                    f"{currency} {threshold} threshold for manager review."
                ),
                context={"final_amount": final_amount, "threshold": threshold},
            )
        )

    credit_limit = to_decimal(customer.credit_limit)
    if policy.require_on_credit_breach and credit_limit > ZERO:
        exposure = to_decimal(customer.outstanding_amount) + final_amount
        if exposure > credit_limit:
            exceptions.append(
                RuleException(
                    type=ExceptionType.CREDIT_LIMIT_EXCEEDED,
                    message=(
                        f"This quotation takes {customer.code} to {currency} "
                        f"{exposure} against a credit limit of {currency} "
                        f"{credit_limit}."
                    ),
                    context={
                        "outstanding_amount": to_decimal(customer.outstanding_amount),
                        "quotation_amount": final_amount,
                        "projected_exposure": exposure,
                        "credit_limit": credit_limit,
                    },
                )
            )

    if policy.require_on_stock_shortfall and shortfall_lines:
        exceptions.append(
            RuleException(
                type=ExceptionType.STOCK_SHORTFALL,
                message=(
                    f"{len(shortfall_lines)} line(s) cannot be met from stock and "
                    f"would be backordered."
                ),
                context={"lines": shortfall_lines},
            )
        )

    return exceptions


async def _finalise_no_op(
    request: QuotationRequest,
    recorder: _StepRecorder,
    triggered_by: str | None,
    trigger: str,
    started_at,
) -> WorkflowResult:
    """Record a run that had nothing to do, and change nothing else.

    The no-op boundary exists so that re-triggering the engine on a settled
    request is cheap and safe rather than a second document or an error. The
    event is recorded so repeated pointless triggers are visible.
    """
    status = RequestStatus(request.status)
    reason = f"The request is already {status.value}; no further action is required."

    for step in WORKFLOW_PIPELINE:
        recorder.skip(step, reason)

    execution_id = await _persist_execution(
        request,
        recorder,
        WorkflowOutcome.NO_OP,
        status,
        triggered_by,
        trigger,
        started_at,
        budget=None,
    )

    await get_collection(Collections.QUOTATION_REQUESTS).update_one(
        {"_id": object_id(str(request.id))},
        {"$inc": {"no_op_count": 1}, "$set": {"last_execution_id": execution_id}},
    )

    await audit_service.record(
        action=AuditAction.WORKFLOW_NO_OP,
        entity_type="quotation_request",
        entity_id=str(request.id),
        summary=f"Workflow skipped for {request.request_number}: {reason}",
        actor={"id": triggered_by, "email": "system", "role": "WORKFLOW"},
        metadata={
            "execution_id": execution_id,
            "status": status.value,
            "trigger": trigger,
        },
    )

    logger.info("No-op for %s (%s)", request.request_number, status.value)
    return WorkflowResult(
        execution_id=execution_id,
        outcome=WorkflowOutcome.NO_OP,
        resulting_status=status,
        request=await _reload(str(request.id)),
        steps=recorder.steps,
    )


async def _finalise_escalation(
    request: QuotationRequest,
    recorder: _StepRecorder,
    *,
    reason: EscalationReason,
    detail: str,
    outcome: WorkflowOutcome,
    triggered_by: str | None,
    trigger: str,
    started_at,
    budget: ExecutionBudget | None,
    gate: dict | None = None,
    check_report: dict | None = None,
) -> WorkflowResult:
    """Park the request for a human and tell the managers why."""
    current = RequestStatus(request.status)
    target = RequestStatus.ESCALATED

    # Escalation must still obey the state machine. If the current status
    # cannot reach ESCALATED the request is left where it is, and the reason is
    # recorded on the execution instead of being silently dropped.
    escalatable = target in REQUEST_TRANSITIONS.get(current, set())

    for step in WORKFLOW_PIPELINE:
        if not any(recorded.step == step for recorded in recorder.steps):
            recorder.skip(step, f"Skipped: {detail}")

    now = utc_now()
    execution_id = await _persist_execution(
        request,
        recorder,
        outcome,
        target if escalatable else current,
        triggered_by,
        trigger,
        started_at,
        budget=budget,
        escalation_reason=reason,
        escalation_detail=detail,
        gate=gate or empty_gate(),
    )

    update: dict = {
        "last_execution_id": execution_id,
        "escalation_reason": reason.value,
        "escalation_detail": detail,
        "escalated_at": now,
        "requires_approval": True,
        "updated_at": now,
    }
    operation: dict = {"$set": update}
    if budget is not None:
        operation["$inc"] = {
            "retry_count": budget.retries_used,
            "total_execution_ms": budget.elapsed_ms,
        }

    if escalatable:
        update["status"] = target.value
        operation["$push"] = {
            "status_history": StatusHistoryEntry(
                from_status=current,
                to_status=target,
                actor_id=triggered_by,
                note=detail,
                at=now,
            ).model_dump()
        }

    await get_collection(Collections.QUOTATION_REQUESTS).update_one(
        {"_id": object_id(str(request.id))}, operation
    )

    await audit_service.record(
        action=AuditAction.WORKFLOW_ESCALATED
        if outcome is not WorkflowOutcome.BUDGET_EXCEEDED
        else AuditAction.WORKFLOW_BUDGET_EXCEEDED,
        entity_type="quotation_request",
        entity_id=str(request.id),
        summary=f"{request.request_number} escalated: {detail}",
        actor={"id": triggered_by, "email": "system", "role": "WORKFLOW"},
        metadata={
            "execution_id": execution_id,
            "escalation_reason": reason.value,
            "attempt_number": budget.attempt_number if budget else None,
            "retries_used": budget.retries_used if budget else None,
            "previous_status": current.value,
            "new_status": target.value if escalatable else current.value,
        },
    )

    await notification_service.notify_role(
        role=UserRole.SALES_MANAGER,
        notification_type=NotificationType.WORKFLOW_ESCALATED,
        title=f"Escalated: {request.request_number}",
        message=detail,
        entity_type="quotation_request",
        entity_id=str(request.id),
    )

    logger.warning("Escalated %s: %s", request.request_number, detail)
    return WorkflowResult(
        execution_id=execution_id,
        outcome=outcome,
        resulting_status=target if escalatable else current,
        request=await _reload(str(request.id)),
        steps=recorder.steps,
        attempt_number=budget.attempt_number if budget else 1,
        retries_used=budget.retries_used if budget else 0,
        gate=gate or empty_gate(),
        escalation_reason=reason,
        escalation_detail=detail,
        check_report=check_report,
    )


async def _persist_execution(
    request: QuotationRequest,
    recorder: _StepRecorder,
    outcome: WorkflowOutcome,
    resulting_status: RequestStatus,
    triggered_by: str | None,
    trigger: str,
    started_at,
    budget: ExecutionBudget | None = None,
    escalation_reason: EscalationReason | None = None,
    escalation_detail: str | None = None,
    gate: dict | None = None,
) -> str:
    completed_at = utc_now()
    execution = WorkflowExecution(
        request_id=str(request.id),
        request_number=request.request_number,
        triggered_by=triggered_by,
        trigger=trigger,
        engine_version=ENGINE_VERSION,
        outcome=outcome,
        steps=recorder.steps,
        resulting_status=resulting_status.value,
        attempt_number=budget.attempt_number if budget else request.attempt_count or 1,
        retries_used=budget.retries_used if budget else 0,
        budget=budget.as_dict() if budget else {},
        gate=gate or {},
        escalation_reason=escalation_reason,
        escalation_detail=escalation_detail,
        started_at=started_at,
        completed_at=completed_at,
        duration_ms=max(int((completed_at - started_at).total_seconds() * 1000), 0),
    )
    result = await get_collection(Collections.WORKFLOW_EXECUTIONS).insert_one(
        encode_decimals(execution.model_dump(exclude={"id"}))
    )
    return str(result.inserted_id)


async def _finalise_validation_failure(
    request: QuotationRequest,
    recorder: _StepRecorder,
    errors: list[str],
    triggered_by: str | None,
    trigger: str,
    started_at,
    budget: ExecutionBudget | None = None,
) -> WorkflowResult:
    """Write a VALIDATION_FAILED outcome and tell the submitter why."""
    step = recorder.start(WorkflowStep.FINALISE)
    target = RequestStatus.VALIDATION_FAILED
    assert_transition(RequestStatus(request.status), target)

    execution_id = await _persist_execution(
        request,
        recorder,
        WorkflowOutcome.VALIDATION_FAILED,
        target,
        triggered_by,
        trigger,
        started_at,
        budget=budget,
        # A full gate is always reported, so a consumer never has to tell
        # "false" apart from "absent".
        gate=empty_gate(),
    )

    now = utc_now()
    history = StatusHistoryEntry(
        from_status=RequestStatus(request.status),
        to_status=target,
        actor_id=triggered_by,
        note=f"{len(errors)} validation issue(s).",
        at=now,
    )
    await get_collection(Collections.QUOTATION_REQUESTS).update_one(
        {"_id": object_id(str(request.id))},
        {
            "$set": encode_decimals(
                {
                    "status": target.value,
                    "validation_errors": errors,
                    "exceptions": [],
                    "requires_approval": False,
                    "items": [line.model_dump() for line in request.items],
                    "pricing": request.pricing.model_dump() if request.pricing else None,
                    "last_execution_id": execution_id,
                    "updated_at": now,
                }
            ),
            "$push": {"status_history": history.model_dump()},
        },
    )

    request.status = target
    request.validation_errors = errors
    request.requires_approval = False
    request.last_execution_id = execution_id

    recorder.finish(
        step,
        message="Request marked as failing validation.",
        output={"error_count": len(errors)},
    )

    await notification_service.notify(
        user_id=request.created_by,
        notification_type=NotificationType.VALIDATION_FAILED,
        title=f"Request {request.request_number} needs attention",
        message=errors[0] if errors else "The request failed validation.",
        entity_type="quotation_request",
        entity_id=str(request.id),
    )

    return WorkflowResult(
        execution_id=execution_id,
        outcome=WorkflowOutcome.VALIDATION_FAILED,
        resulting_status=target,
        request=await _reload(str(request.id)),
        steps=recorder.steps,
        validation_errors=errors,
        attempt_number=budget.attempt_number if budget else 1,
        retries_used=budget.retries_used if budget else 0,
        gate=empty_gate(),
    )


async def _finalise_success(
    *,
    request: QuotationRequest,
    customer: Customer,
    settings_doc: CompanySettings,
    recorder: _StepRecorder,
    requires_approval: bool,
    exceptions: list[RuleException],
    triggered_by: str | None,
    trigger: str,
    started_at,
    budget: ExecutionBudget,
) -> WorkflowResult:
    """Queue the request for a manager, or run the action and checker tools.

    The approved path is the interesting one: it runs the action tool, then the
    checker tool, then the success gate. Only a request whose gate is fully
    satisfied becomes COMPLETED. A checker rejection escalates instead, so a
    document that does not survive independent recalculation is never delivered
    as though it were sound.
    """
    requests = get_collection(Collections.QUOTATION_REQUESTS)
    now = utc_now()

    # The steps already behind us form the first half of the gate.
    gate: dict = {
        "input_validation_passed": True,
        "product_verification_passed": True,
        "pricing_validation_passed": request.pricing is not None,
        "approval_recorded": False,
        "document_generated": False,
        "independent_verification_passed": False,
    }

    entry_status = RequestStatus(request.status)
    target = (
        RequestStatus.PENDING_APPROVAL if requires_approval else RequestStatus.APPROVED
    )
    # A new submission is priced before it is queued or approved. An approval
    # re-run is already past that point and closes straight out to APPROVED.
    path = (
        [target]
        if entry_status == RequestStatus.PENDING_APPROVAL
        else [RequestStatus.PRICED, target]
    )
    cursor_status = entry_status
    for hop in path:
        assert_transition(cursor_status, hop)
        cursor_status = hop

    approval_id: str | None = None
    if requires_approval:
        approval_id = await _create_approval_task(
            request, customer, settings_doc, exceptions, now
        )

    update: dict = {
        "status": target.value,
        "items": [line.model_dump() for line in request.items],
        "pricing": request.pricing.model_dump() if request.pricing else None,
        "validation_errors": [],
        "exceptions": [exception.model_dump() for exception in exceptions],
        "requires_approval": requires_approval,
        "updated_at": now,
    }
    if approval_id:
        update["approval_id"] = approval_id
    if target == RequestStatus.APPROVED:
        update["decided_at"] = now
        gate["approval_recorded"] = True

    history: list[dict] = []
    previous = entry_status
    for hop in path:
        history.append(
            StatusHistoryEntry(
                from_status=previous,
                to_status=hop,
                actor_id=triggered_by,
                note=(
                    "Pricing and discount rules evaluated."
                    if hop == RequestStatus.PRICED
                    else (
                        f"{len(exceptions)} exception(s) require manager approval."
                        if requires_approval
                        else "Approved: no outstanding exceptions."
                    )
                ),
                at=now,
            ).model_dump()
        )
        previous = hop

    await requests.update_one(
        {"_id": object_id(str(request.id))},
        {
            "$set": encode_decimals(update),
            "$push": {"status_history": {"$each": history}},
        },
    )

    request.status = target
    request.exceptions = exceptions
    request.requires_approval = requires_approval
    # Only overwrite the approval reference when this run raised a task. On an
    # approval re-run no new task is created, and the existing reference is the
    # evidence that a manager authorised the quotation - erasing it would make
    # the checker reject the document for having no traceable approval.
    if approval_id:
        request.approval_id = approval_id
    request.validation_errors = []

    # ---- The queued path stops here --------------------------------------
    if requires_approval:
        for skipped in (WorkflowStep.GENERATE_DOCUMENT, WorkflowStep.VERIFY_DOCUMENT):
            recorder.skip(skipped, "Awaiting a manager decision.")

        step = recorder.start(WorkflowStep.FINALISE)
        execution_id = await _persist_execution(
            request,
            recorder,
            WorkflowOutcome.PENDING_APPROVAL,
            target,
            triggered_by,
            trigger,
            started_at,
            budget=budget,
            gate=gate,
        )
        recorder.finish(
            step,
            message="Approval task raised for the sales manager.",
            output={
                "resulting_status": target.value,
                "approval_id": approval_id,
                "gate": gate,
            },
        )
        await _rewrite_steps(execution_id, recorder.steps, started_at)
        await _record_attempt_cost(request, execution_id, budget)

        if trigger == "SUBMISSION":
            await _send_outcome_notifications(request, True, exceptions, None)

        await _audit_execution(
            request,
            execution_id,
            WorkflowOutcome.PENDING_APPROVAL,
            entry_status,
            target,
            triggered_by,
            budget,
            gate,
        )
        return WorkflowResult(
            execution_id=execution_id,
            outcome=WorkflowOutcome.PENDING_APPROVAL,
            resulting_status=target,
            request=await _reload(str(request.id)),
            steps=recorder.steps,
            approval_id=approval_id,
            exceptions=exceptions,
            attempt_number=budget.attempt_number,
            retries_used=budget.retries_used,
            gate=gate,
        )

    # ---- Step 6: the action tool ------------------------------------------
    # Which approval, if any, authorises this cycle. Read from the task's
    # status so a stale reference cannot stand in for a decision.
    auto_approved, authorising_approval_id = await _resolve_authorisation(
        str(request.id)
    )
    if authorising_approval_id:
        request.approval_id = authorising_approval_id

    step = recorder.start(WorkflowStep.GENERATE_DOCUMENT)
    retries_before = budget.retries_used
    try:
        action_result = await budget.run_step(
            WorkflowStep.GENERATE_DOCUMENT.value,
            lambda: action_tool.execute(
                request,
                customer=customer,
                settings_doc=settings_doc,
                auto_approved=auto_approved,
                approval_id=authorising_approval_id,
            ),
        )
    except BudgetExceeded as error:
        recorder.finish(
            step,
            status=StepStatus.FAILED,
            message="The execution budget ran out before the document was issued.",
            errors=[str(error)],
            retries=budget.retries_used - retries_before,
        )
        return await _finalise_escalation(
            request,
            recorder,
            reason=EscalationReason.BUDGET_EXCEEDED,
            detail=str(error),
            outcome=WorkflowOutcome.BUDGET_EXCEEDED,
            triggered_by=triggered_by,
            trigger=trigger,
            started_at=started_at,
            budget=budget,
            gate=gate,
        )
    except Exception as error:  # noqa: BLE001 - recorded, then escalated
        recorder.finish(
            step,
            status=StepStatus.FAILED,
            message="The quotation document could not be produced.",
            errors=[f"{type(error).__name__}: {error}"],
            retries=budget.retries_used - retries_before,
        )
        logger.exception("Document generation failed for %s", request.request_number)
        return await _finalise_escalation(
            request,
            recorder,
            reason=EscalationReason.REPEATED_PROCESSING_FAILURE,
            detail=(
                f"The quotation document could not be produced after "
                f"{budget.retries_used - retries_before} retry(ies): {error}"
            ),
            outcome=WorkflowOutcome.ESCALATED,
            triggered_by=triggered_by,
            trigger=trigger,
            started_at=started_at,
            budget=budget,
            gate=gate,
        )

    gate["document_generated"] = True
    request.quotation_id = action_result.quotation_id
    recorder.finish(
        step,
        message=(
            f"Reused existing quotation {action_result.quotation_number}."
            if action_result.reused_existing
            else f"Issued quotation {action_result.quotation_number}."
        ),
        output=action_result.as_output(),
        retries=budget.retries_used - retries_before,
    )

    # ---- Step 7: the checker tool -----------------------------------------
    step = recorder.start(WorkflowStep.VERIFY_DOCUMENT)
    retries_before = budget.retries_used
    try:
        report = await budget.run_step(
            WorkflowStep.VERIFY_DOCUMENT.value,
            lambda: checker_tool.verify_quotation(
                action_result.quotation, settings_doc=settings_doc
            ),
        )
        # Belt and braces: a request must never hold two quotations.
        await action_tool.assert_single_quotation(str(request.id))
    except Exception as error:  # noqa: BLE001 - recorded, then escalated
        recorder.finish(
            step,
            status=StepStatus.FAILED,
            message="The independent verification could not be completed.",
            errors=[f"{type(error).__name__}: {error}"],
            retries=budget.retries_used - retries_before,
        )
        return await _finalise_escalation(
            request,
            recorder,
            reason=EscalationReason.VERIFICATION_MISMATCH,
            detail=f"Independent verification could not run: {error}",
            outcome=WorkflowOutcome.ESCALATED,
            triggered_by=triggered_by,
            trigger=trigger,
            started_at=started_at,
            budget=budget,
            gate=gate,
        )

    gate["independent_verification_passed"] = report.passed
    recorder.finish(
        step,
        status=StepStatus.SUCCESS if report.passed else StepStatus.FAILED,
        message=report.summary,
        output=report.as_output(),
        errors=[finding.detail for finding in report.findings],
        retries=budget.retries_used - retries_before,
    )

    if not report.passed:
        # A document that fails independent recalculation is not delivered.
        await audit_service.record(
            action=AuditAction.QUOTATION_VERIFICATION_FAILED,
            entity_type="quotation",
            entity_id=action_result.quotation_id,
            summary=(
                f"{action_result.quotation_number} failed independent "
                f"verification: {report.summary}"
            ),
            actor={"id": triggered_by, "email": "system", "role": "WORKFLOW"},
            metadata={"findings": [f.as_dict() for f in report.findings]},
        )
        return await _finalise_escalation(
            request,
            recorder,
            reason=EscalationReason.VERIFICATION_MISMATCH,
            detail=(
                f"The issued document did not survive independent "
                f"recalculation: {report.summary}"
            ),
            outcome=WorkflowOutcome.ESCALATED,
            triggered_by=triggered_by,
            trigger=trigger,
            started_at=started_at,
            budget=budget,
            gate=gate,
            check_report=report.as_output(),
        )

    # ---- Step 8: finalise, behind the success gate ------------------------
    step = recorder.start(WorkflowStep.FINALISE)
    passed, unmet = evaluate_success_gate(gate)

    if not passed:
        recorder.finish(
            step,
            status=StepStatus.FAILED,
            message=f"The success gate is not satisfied: {', '.join(unmet)}.",
            output={"gate": gate, "unmet": unmet},
        )
        return await _finalise_escalation(
            request,
            recorder,
            reason=EscalationReason.REPEATED_PROCESSING_FAILURE,
            detail=(
                "The request cannot be completed because these gate conditions "
                f"are unmet: {', '.join(unmet)}."
            ),
            outcome=WorkflowOutcome.ESCALATED,
            triggered_by=triggered_by,
            trigger=trigger,
            started_at=started_at,
            budget=budget,
            gate=gate,
            check_report=report.as_output(),
        )

    assert_transition(RequestStatus.APPROVED, RequestStatus.COMPLETED)
    completed_at = utc_now()

    execution_id = await _persist_execution(
        request,
        recorder,
        WorkflowOutcome.COMPLETED,
        RequestStatus.COMPLETED,
        triggered_by,
        trigger,
        started_at,
        budget=budget,
        gate=gate,
    )

    await requests.update_one(
        {"_id": object_id(str(request.id))},
        {
            "$set": {
                "status": RequestStatus.COMPLETED.value,
                "quotation_id": action_result.quotation_id,
                "requires_approval": False,
                "completed_at": completed_at,
                "updated_at": completed_at,
            },
            "$push": {
                "status_history": StatusHistoryEntry(
                    from_status=RequestStatus.APPROVED,
                    to_status=RequestStatus.COMPLETED,
                    actor_id=triggered_by,
                    note=(
                        f"Document {action_result.quotation_number} issued and "
                        f"independently verified."
                    ),
                    at=completed_at,
                ).model_dump()
            },
        },
    )

    recorder.finish(
        step,
        message=f"Completed: {action_result.quotation_number} issued and verified.",
        output={
            "resulting_status": RequestStatus.COMPLETED.value,
            "quotation_id": action_result.quotation_id,
            "gate": gate,
        },
    )
    await _rewrite_steps(execution_id, recorder.steps, started_at)
    await _record_attempt_cost(request, execution_id, budget)

    if trigger == "SUBMISSION":
        await _send_outcome_notifications(
            request, False, exceptions, action_result.quotation_id
        )

    await _audit_execution(
        request,
        execution_id,
        WorkflowOutcome.COMPLETED,
        entry_status,
        RequestStatus.COMPLETED,
        triggered_by,
        budget,
        gate,
    )

    return WorkflowResult(
        execution_id=execution_id,
        outcome=WorkflowOutcome.COMPLETED,
        resulting_status=RequestStatus.COMPLETED,
        request=await _reload(str(request.id)),
        steps=recorder.steps,
        approval_id=request.approval_id,
        quotation_id=action_result.quotation_id,
        exceptions=exceptions,
        attempt_number=budget.attempt_number,
        retries_used=budget.retries_used,
        gate=gate,
        check_report=report.as_output(),
    )


async def _resolve_authorisation(request_id: str) -> tuple[bool, str | None]:
    """``(auto_approved, approval_id)`` for the request's current cycle.

    Authorisation is read from the approval's *status*, not from the presence of
    a reference. A request returned for modification keeps pointing at the task
    that returned it, and that task authorises nothing - treating it as approval
    made the checker reject the resulting document for an approval that was
    never granted.
    """
    raw = await get_collection(Collections.APPROVALS).find_one(
        {"request_id": str(request_id), "status": ApprovalStatus.APPROVED.value},
        sort=[("decided_at", -1)],
    )
    if raw is None:
        return True, None
    return False, str(raw["_id"])


async def _record_attempt_cost(
    request: QuotationRequest, execution_id: str, budget: ExecutionBudget
) -> None:
    """Add this run's retries and elapsed time to the request's running totals."""
    await get_collection(Collections.QUOTATION_REQUESTS).update_one(
        {"_id": object_id(str(request.id))},
        {
            "$set": {"last_execution_id": execution_id},
            "$inc": {
                "retry_count": budget.retries_used,
                "total_execution_ms": budget.elapsed_ms,
            },
        },
    )


async def _audit_execution(
    request: QuotationRequest,
    execution_id: str,
    outcome: WorkflowOutcome,
    previous_status: RequestStatus,
    new_status: RequestStatus,
    triggered_by: str | None,
    budget: ExecutionBudget,
    gate: dict,
) -> None:
    """Record the run with everything needed to reconstruct it afterwards."""
    await audit_service.record(
        action=AuditAction.WORKFLOW_EXECUTED,
        entity_type="quotation_request",
        entity_id=str(request.id),
        summary=(
            f"Workflow {outcome.value} for {request.request_number} "
            f"(attempt {budget.attempt_number}, {budget.retries_used} retry(ies))."
        ),
        actor={"id": triggered_by, "email": "system", "role": "WORKFLOW"},
        metadata={
            "execution_id": execution_id,
            "outcome": outcome.value,
            "previous_status": previous_status.value,
            "new_status": new_status.value,
            "attempt_number": budget.attempt_number,
            "retry_count": budget.retries_used,
            "elapsed_ms": budget.elapsed_ms,
            "gate": gate,
        },
    )


async def _rewrite_steps(execution_id: str, steps: list[StepExecution], started_at) -> None:
    completed_at = utc_now()
    await get_collection(Collections.WORKFLOW_EXECUTIONS).update_one(
        {"_id": object_id(execution_id)},
        {
            "$set": encode_decimals(
                {
                    "steps": [step.model_dump() for step in steps],
                    "completed_at": completed_at,
                    "duration_ms": max(
                        int((completed_at - started_at).total_seconds() * 1000), 0
                    ),
                }
            )
        },
    )


async def _create_approval_task(
    request: QuotationRequest,
    customer: Customer,
    settings_doc: CompanySettings,
    exceptions: list[RuleException],
    now,
) -> str:
    """Raise a pending approval, superseding any earlier open task."""
    approvals = get_collection(Collections.APPROVALS)

    # A resubmitted request must not leave its previous task in the queue.
    await approvals.update_many(
        {"request_id": str(request.id), "status": ApprovalStatus.PENDING.value},
        {
            "$set": {
                "status": ApprovalStatus.MODIFICATION_REQUESTED.value,
                "comments": "Superseded by a newer submission of this request.",
                "updated_at": now,
            }
        },
    )

    max_requested = max(
        (rate(line.applied_discount_percent) for line in request.items),
        default=ZERO,
    )
    approval = Approval(
        request_id=str(request.id),
        request_number=request.request_number,
        customer_id=str(request.customer_id),
        customer_name=customer.company_name,
        status=ApprovalStatus.PENDING,
        exceptions=exceptions,
        pricing_snapshot=request.pricing,
        requested_amount=(
            request.pricing.final_amount if request.pricing else ZERO
        ),
        requested_discount_percent=max_requested,
        sla_due_at=now
        + timedelta(hours=settings_doc.approval_policy.approval_sla_hours),
        created_at=now,
        updated_at=now,
    )
    result = await approvals.insert_one(
        encode_decimals(approval.model_dump(exclude={"id"}))
    )
    return str(result.inserted_id)


async def _send_outcome_notifications(
    request: QuotationRequest,
    requires_approval: bool,
    exceptions: list[RuleException],
    quotation_id: str | None,
) -> None:
    if requires_approval:
        reasons = ", ".join(
            sorted({exception.type for exception in exceptions})
        ).replace("_", " ").lower()
        await notification_service.notify_role(
            role=UserRole.SALES_MANAGER,
            notification_type=NotificationType.APPROVAL_REQUIRED,
            title=f"Approval needed: {request.request_number}",
            message=(
                f"{request.customer_name} requested a quotation that raised "
                f"{len(exceptions)} exception(s): {reasons}."
            ),
            entity_type="quotation_request",
            entity_id=str(request.id),
        )
        await notification_service.notify(
            user_id=request.created_by,
            notification_type=NotificationType.REQUEST_SUBMITTED,
            title=f"Request {request.request_number} is under review",
            message=(
                "Your request has been priced and sent to a sales manager for "
                "approval."
            ),
            entity_type="quotation_request",
            entity_id=str(request.id),
        )
        return

    await notification_service.notify(
        user_id=request.created_by,
        notification_type=NotificationType.QUOTATION_READY,
        title=f"Quotation ready for {request.request_number}",
        message=(
            "Your request was approved automatically and the quotation is ready "
            "to download."
        ),
        entity_type="quotation",
        entity_id=quotation_id,
    )
