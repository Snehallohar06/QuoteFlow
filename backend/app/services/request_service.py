"""Quotation request management: create, edit, submit, cancel, read."""

from __future__ import annotations

from typing import Any

from pymongo import ReturnDocument

from app.core.exceptions import (
    BusinessRuleError,
    NotFoundError,
    PermissionDeniedError,
    WorkflowError,
)
from app.db.mongo import Collections, get_collection
from app.models.common import build_page, object_id, utc_now
from app.models.customer import Customer
from app.models.enums import (
    TERMINAL_REQUEST_STATUSES,
    ApprovalStatus,
    AuditAction,
    CustomerStatus,
    RequestStatus,
)
from app.models.quotation_request import (
    QuotationRequest,
    RequestLine,
    StatusHistoryEntry,
)
from app.models.workflow import WorkflowExecution
from app.schemas.quotation import (
    QuotationRequestCreate,
    QuotationRequestUpdate,
    RequestItemInput,
)
from app.services import audit_service, numbering, product_service, workflow_engine
from app.services.settings_service import get_settings_document
from app.utils.money import decode_decimals, encode_decimals

#: Statuses whose lines a submitter is still allowed to edit.
EDITABLE_STATUSES = {
    RequestStatus.DRAFT,
    RequestStatus.VALIDATION_FAILED,
    RequestStatus.MODIFICATION_REQUESTED,
}


async def _resolve_customer(
    principal, requested_customer_id: str | None
) -> Customer:
    """Work out which customer a new request belongs to.

    A customer user may only ever create requests for themselves; staff must
    name the customer explicitly.
    """
    if principal.is_customer:
        if not principal.customer_id:
            raise BusinessRuleError(
                "This account is not linked to a customer record. Contact sales."
            )
        customer_id = principal.customer_id
    else:
        if not requested_customer_id:
            raise BusinessRuleError(
                "A customer must be selected when raising a request on their behalf."
            )
        customer_id = requested_customer_id

    raw = await get_collection(Collections.CUSTOMERS).find_one(
        {"_id": object_id(customer_id)}
    )
    if raw is None:
        raise NotFoundError("Customer not found.")

    customer = Customer.from_mongo(decode_decimals(raw))
    if customer.status == CustomerStatus.BLOCKED:
        raise BusinessRuleError(
            f"Customer {customer.code} is blocked and cannot raise new requests."
        )
    return customer


async def _build_lines(items: list[RequestItemInput]) -> list[RequestLine]:
    """Turn submitted items into request lines, snapshotting catalogue data.

    Amounts are left at zero here: pricing is the workflow engine's job, so a
    saved draft never carries figures that were never validated.
    """
    products = await product_service.get_products_by_ids(
        [item.product_id for item in items]
    )
    missing = [item.product_id for item in items if item.product_id not in products]
    if missing:
        raise NotFoundError(
            "One or more of the products requested could not be found.",
            details={"missing_product_ids": missing},
        )

    lines: list[RequestLine] = []
    for item in items:
        product = products[item.product_id]
        lines.append(
            RequestLine(
                product_id=item.product_id,
                sku=product.sku,
                name=product.name,
                unit=product.unit,
                quantity=item.quantity,
                unit_price=product.unit_price,
                requested_discount_percent=item.requested_discount_percent,
                notes=item.notes,
            )
        )
    return lines


async def create_request(
    payload: QuotationRequestCreate,
    *,
    principal,
    request_context: dict[str, Any] | None = None,
) -> QuotationRequest:
    """Create a request as a draft. Submission is a separate step."""
    customer = await _resolve_customer(principal, payload.customer_id)
    lines = await _build_lines(payload.items)

    settings_doc = await get_settings_document()
    request = QuotationRequest(
        request_number=await numbering.next_document_number(
            settings_doc.quotation_policy.request_number_prefix
        ),
        customer_id=str(customer.id),
        customer_code=customer.code,
        customer_name=customer.company_name,
        created_by=principal.id,
        created_by_role=principal.role.value,
        status=RequestStatus.DRAFT,
        items=lines,
        expected_delivery_date=payload.expected_delivery_date,
        customer_notes=payload.customer_notes,
        status_history=[
            StatusHistoryEntry(
                to_status=RequestStatus.DRAFT,
                actor_id=principal.id,
                actor_name=principal.full_name,
                note="Request created.",
            )
        ],
    )

    result = await get_collection(Collections.QUOTATION_REQUESTS).insert_one(
        encode_decimals(request.model_dump(exclude={"id"}))
    )
    request.id = str(result.inserted_id)

    await audit_service.record(
        action=AuditAction.REQUEST_CREATED,
        entity_type="quotation_request",
        entity_id=request.id,
        summary=(
            f"Request {request.request_number} created for {customer.company_name} "
            f"with {len(lines)} line(s)."
        ),
        actor=principal.as_actor(),
        metadata={"customer_code": customer.code, "line_count": len(lines)},
        **(request_context or {}),
    )
    return request


async def get_request(request_id: str) -> QuotationRequest:
    raw = await get_collection(Collections.QUOTATION_REQUESTS).find_one(
        {"_id": object_id(request_id)}
    )
    if raw is None:
        raise NotFoundError("Quotation request not found.")
    return QuotationRequest.from_mongo(decode_decimals(raw))


def assert_can_view(request: QuotationRequest, principal) -> None:
    if principal.is_staff:
        return
    if principal.customer_id and str(request.customer_id) == principal.customer_id:
        return
    raise PermissionDeniedError("This request belongs to another customer.")


def assert_can_edit(request: QuotationRequest, principal) -> None:
    assert_can_view(request, principal)
    if RequestStatus(request.status) not in EDITABLE_STATUSES:
        raise WorkflowError(
            f"A request in status {request.status} can no longer be edited.",
            details={
                "editable_statuses": sorted(
                    status.value for status in EDITABLE_STATUSES
                )
            },
        )


async def list_requests(
    *,
    principal,
    page: int = 1,
    page_size: int = 20,
    status: str | None = None,
    customer_id: str | None = None,
    search: str | None = None,
    requires_approval: bool | None = None,
):
    """List requests, scoped to the caller's role.

    A customer only ever sees their own; staff see everything and can filter.
    """
    query: dict[str, Any] = {}
    if principal.is_customer:
        if not principal.customer_id:
            return build_page([], 0, page, page_size)
        query["customer_id"] = principal.customer_id
    elif customer_id:
        query["customer_id"] = customer_id

    if status:
        query["status"] = status
    if requires_approval is not None:
        query["requires_approval"] = requires_approval
    if search:
        pattern = {"$regex": search.strip(), "$options": "i"}
        query["$or"] = [
            {"request_number": pattern},
            {"customer_name": pattern},
            {"customer_code": pattern},
            {"items.sku": pattern},
        ]

    collection = get_collection(Collections.QUOTATION_REQUESTS)
    total = await collection.count_documents(query)
    cursor = (
        collection.find(query)
        .sort("created_at", -1)
        .skip((page - 1) * page_size)
        .limit(page_size)
    )
    documents = await cursor.to_list(length=page_size)
    items = [QuotationRequest.from_mongo(decode_decimals(doc)) for doc in documents]
    return build_page(items, total, page, page_size)


async def update_request(
    request_id: str,
    payload: QuotationRequestUpdate,
    *,
    principal,
    request_context: dict[str, Any] | None = None,
) -> QuotationRequest:
    existing = await get_request(request_id)
    assert_can_edit(existing, principal)

    updates: dict[str, Any] = {}
    fields = payload.model_dump(exclude_unset=True)

    if payload.items is not None:
        lines = await _build_lines(payload.items)
        updates["items"] = [line.model_dump() for line in lines]
        # The lines changed, so any earlier pricing and verdicts are void.
        updates["pricing"] = None
        updates["exceptions"] = []
        updates["validation_errors"] = []
        updates["requires_approval"] = False
    if "expected_delivery_date" in fields:
        updates["expected_delivery_date"] = payload.expected_delivery_date
    if "customer_notes" in fields:
        updates["customer_notes"] = payload.customer_notes

    if not updates:
        return existing

    updates["updated_at"] = utc_now()
    raw = await get_collection(Collections.QUOTATION_REQUESTS).find_one_and_update(
        {"_id": object_id(request_id)},
        {"$set": encode_decimals(updates)},
        return_document=ReturnDocument.AFTER,
    )

    await audit_service.record(
        action=AuditAction.REQUEST_UPDATED,
        entity_type="quotation_request",
        entity_id=request_id,
        summary=f"Request {existing.request_number} updated.",
        actor=principal.as_actor(),
        changes={
            key: {"before": "(previous)", "after": "(updated)"}
            for key in updates
            if key not in {"updated_at"}
        },
        **(request_context or {}),
    )
    return QuotationRequest.from_mongo(decode_decimals(raw))


async def set_internal_notes(
    request_id: str,
    notes: str,
    *,
    principal,
    request_context: dict[str, Any] | None = None,
) -> QuotationRequest:
    """Staff-only annotation, never shown to the customer."""
    existing = await get_request(request_id)
    raw = await get_collection(Collections.QUOTATION_REQUESTS).find_one_and_update(
        {"_id": object_id(request_id)},
        {"$set": {"internal_notes": notes, "updated_at": utc_now()}},
        return_document=ReturnDocument.AFTER,
    )
    await audit_service.record(
        action=AuditAction.REQUEST_UPDATED,
        entity_type="quotation_request",
        entity_id=request_id,
        summary=f"Internal notes updated on request {existing.request_number}.",
        actor=principal.as_actor(),
        **(request_context or {}),
    )
    return QuotationRequest.from_mongo(decode_decimals(raw))


async def submit_request(
    request_id: str,
    *,
    principal,
    request_context: dict[str, Any] | None = None,
) -> workflow_engine.WorkflowResult:
    """Move a request to SUBMITTED and run the workflow pipeline."""
    existing = await get_request(request_id)
    assert_can_view(existing, principal)

    current = RequestStatus(existing.status)
    if current not in EDITABLE_STATUSES:
        raise WorkflowError(
            f"A request in status {existing.status} cannot be submitted.",
            details={
                "submittable_statuses": sorted(
                    status.value for status in EDITABLE_STATUSES
                )
            },
        )
    if not existing.items:
        raise BusinessRuleError(
            "A request must contain at least one product line before submission."
        )

    workflow_engine.assert_transition(current, RequestStatus.SUBMITTED)

    now = utc_now()
    update: dict[str, Any] = {
        "status": RequestStatus.SUBMITTED.value,
        "submitted_at": now,
        "updated_at": now,
        "validation_errors": [],
    }
    # A resubmission after a modification request is a new revision.
    increment = (
        {"revision": 1}
        if current in {RequestStatus.MODIFICATION_REQUESTED, RequestStatus.VALIDATION_FAILED}
        else {}
    )
    history = StatusHistoryEntry(
        from_status=current,
        to_status=RequestStatus.SUBMITTED,
        actor_id=principal.id,
        actor_name=principal.full_name,
        note="Request submitted for processing.",
        at=now,
    )

    operation: dict[str, Any] = {
        "$set": update,
        "$push": {"status_history": history.model_dump()},
    }
    if increment:
        operation["$inc"] = increment

    await get_collection(Collections.QUOTATION_REQUESTS).update_one(
        {"_id": object_id(request_id)}, operation
    )

    await audit_service.record(
        action=AuditAction.REQUEST_SUBMITTED,
        entity_type="quotation_request",
        entity_id=request_id,
        summary=f"Request {existing.request_number} submitted.",
        actor=principal.as_actor(),
        metadata={"previous_status": current.value},
        **(request_context or {}),
    )

    result = await workflow_engine.execute(
        request_id, triggered_by=principal.id, trigger="SUBMISSION"
    )

    await audit_service.record(
        action=AuditAction.WORKFLOW_EXECUTED,
        entity_type="quotation_request",
        entity_id=request_id,
        summary=(
            f"Workflow completed for {existing.request_number}: "
            f"{result.outcome} ({result.duration_ms} ms)."
        ),
        actor=principal.as_actor(),
        metadata={
            "execution_id": result.execution_id,
            "outcome": result.outcome,
            "resulting_status": result.resulting_status.value,
            "exception_count": len(result.exceptions),
            "validation_error_count": len(result.validation_errors),
        },
        **(request_context or {}),
    )
    return result


async def rerun_workflow(
    request_id: str,
    *,
    principal,
    request_context: dict[str, Any] | None = None,
) -> workflow_engine.WorkflowResult:
    """Staff-triggered re-run, used after stock or catalogue corrections.

    The request is returned to SUBMITTED first so the re-run follows exactly the
    same path as a fresh submission.
    """
    existing = await get_request(request_id)
    current = RequestStatus(existing.status)

    if current in TERMINAL_REQUEST_STATUSES:
        raise WorkflowError(
            f"A request in status {existing.status} cannot be reprocessed."
        )
    if current == RequestStatus.PENDING_APPROVAL:
        raise WorkflowError(
            "This request is awaiting a manager decision. Resolve the approval "
            "task instead of reprocessing it."
        )

    if current != RequestStatus.SUBMITTED:
        workflow_engine.assert_transition(current, RequestStatus.SUBMITTED)
        now = utc_now()
        await get_collection(Collections.QUOTATION_REQUESTS).update_one(
            {"_id": object_id(request_id)},
            {
                "$set": {
                    "status": RequestStatus.SUBMITTED.value,
                    "updated_at": now,
                    "validation_errors": [],
                },
                "$push": {
                    "status_history": StatusHistoryEntry(
                        from_status=current,
                        to_status=RequestStatus.SUBMITTED,
                        actor_id=principal.id,
                        actor_name=principal.full_name,
                        note="Reprocessed by sales staff.",
                        at=now,
                    ).model_dump()
                },
            },
        )

    result = await workflow_engine.execute(
        request_id, triggered_by=principal.id, trigger="REPROCESS"
    )
    await audit_service.record(
        action=AuditAction.WORKFLOW_EXECUTED,
        entity_type="quotation_request",
        entity_id=request_id,
        summary=(
            f"Workflow re-run for {existing.request_number}: {result.outcome}."
        ),
        actor=principal.as_actor(),
        metadata={"execution_id": result.execution_id, "outcome": result.outcome},
        **(request_context or {}),
    )
    return result


async def cancel_request(
    request_id: str,
    *,
    principal,
    reason: str | None = None,
    request_context: dict[str, Any] | None = None,
) -> QuotationRequest:
    existing = await get_request(request_id)
    assert_can_view(existing, principal)

    current = RequestStatus(existing.status)
    workflow_engine.assert_transition(current, RequestStatus.CANCELLED)

    now = utc_now()
    await get_collection(Collections.QUOTATION_REQUESTS).update_one(
        {"_id": object_id(request_id)},
        {
            "$set": {
                "status": RequestStatus.CANCELLED.value,
                "requires_approval": False,
                "decided_at": now,
                "updated_at": now,
            },
            "$push": {
                "status_history": StatusHistoryEntry(
                    from_status=current,
                    to_status=RequestStatus.CANCELLED,
                    actor_id=principal.id,
                    actor_name=principal.full_name,
                    note=reason or "Request cancelled.",
                    at=now,
                ).model_dump()
            },
        },
    )

    # Withdraw any open approval task so it leaves the manager's queue.
    await get_collection(Collections.APPROVALS).update_many(
        {"request_id": request_id, "status": ApprovalStatus.PENDING.value},
        {
            "$set": {
                "status": ApprovalStatus.REJECTED.value,
                "comments": "The request was cancelled by the submitter.",
                "updated_at": now,
            }
        },
    )

    await audit_service.record(
        action=AuditAction.REQUEST_CANCELLED,
        entity_type="quotation_request",
        entity_id=request_id,
        summary=f"Request {existing.request_number} cancelled.",
        actor=principal.as_actor(),
        metadata={"reason": reason} if reason else {},
        **(request_context or {}),
    )
    return await get_request(request_id)


async def list_executions(request_id: str) -> list[WorkflowExecution]:
    """Every pipeline run for one request, newest first."""
    cursor = (
        get_collection(Collections.WORKFLOW_EXECUTIONS)
        .find({"request_id": request_id})
        .sort("started_at", -1)
    )
    documents = await cursor.to_list(length=50)
    return [WorkflowExecution.from_mongo(decode_decimals(doc)) for doc in documents]


async def get_execution(execution_id: str) -> WorkflowExecution:
    raw = await get_collection(Collections.WORKFLOW_EXECUTIONS).find_one(
        {"_id": object_id(execution_id)}
    )
    if raw is None:
        raise NotFoundError("Workflow execution not found.")
    return WorkflowExecution.from_mongo(decode_decimals(raw))
