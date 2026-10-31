"""Manager approval handling.

On APPROVE the workflow pipeline is re-run with ``auto_approve=True`` (and the
manager's override discount, if any) rather than the quotation being built here.
That way an approved quotation is priced by exactly the same code as an
auto-approved one, and the decision leaves its own execution trace.
"""

from __future__ import annotations

from typing import Any

from pymongo import ReturnDocument

from app.core.exceptions import BusinessRuleError, NotFoundError, WorkflowError
from app.db.mongo import Collections, get_collection
from app.models.approval import Approval
from app.models.common import build_page, object_id, utc_now
from app.models.customer import Customer
from app.models.enums import (
    ApprovalDecision,
    ApprovalStatus,
    AuditAction,
    NotificationType,
    RequestStatus,
)
from app.models.quotation_request import StatusHistoryEntry
from app.schemas.quotation import ApprovalDecisionRequest
from app.services import (
    audit_service,
    notification_service,
    quotation_service,
    request_service,
    settings_service,
    workflow_engine,
)
from app.utils.money import decode_decimals, encode_decimals, rate


async def get_approval(approval_id: str) -> Approval:
    raw = await get_collection(Collections.APPROVALS).find_one(
        {"_id": object_id(approval_id)}
    )
    if raw is None:
        raise NotFoundError("Approval task not found.")
    return Approval.from_mongo(decode_decimals(raw))


async def list_approvals(
    *,
    page: int = 1,
    page_size: int = 20,
    status: str | None = None,
    customer_id: str | None = None,
    overdue_only: bool = False,
):
    query: dict[str, Any] = {}
    if status:
        query["status"] = status
    if customer_id:
        query["customer_id"] = customer_id
    if overdue_only:
        query["status"] = ApprovalStatus.PENDING.value
        query["sla_due_at"] = {"$lt": utc_now()}

    collection = get_collection(Collections.APPROVALS)
    total = await collection.count_documents(query)
    cursor = (
        collection.find(query)
        .sort([("status", 1), ("created_at", -1)])
        .skip((page - 1) * page_size)
        .limit(page_size)
    )
    documents = await cursor.to_list(length=page_size)
    items = [Approval.from_mongo(decode_decimals(doc)) for doc in documents]
    return build_page(items, total, page, page_size)


async def pending_count() -> int:
    return await get_collection(Collections.APPROVALS).count_documents(
        {"status": ApprovalStatus.PENDING.value}
    )


async def decide(
    approval_id: str,
    payload: ApprovalDecisionRequest,
    *,
    principal,
    request_context: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Record a manager decision and carry out its consequences."""
    approval = await get_approval(approval_id)
    if approval.status != ApprovalStatus.PENDING:
        raise WorkflowError(
            f"This approval has already been resolved ({approval.status}).",
            details={"decided_at": approval.decided_at},
        )

    if payload.decision in {
        ApprovalDecision.REJECT,
        ApprovalDecision.REQUEST_MODIFICATION,
    } and not (payload.comments or "").strip():
        raise BusinessRuleError(
            "A comment explaining the decision is required when rejecting a "
            "request or asking for modifications."
        )

    if (
        payload.override_discount_percent is not None
        and payload.decision != ApprovalDecision.APPROVE
    ):
        raise BusinessRuleError(
            "A discount override can only accompany an approval."
        )

    settings_doc = await settings_service.get_settings_document()
    absolute_max = rate(settings_doc.discount_policy.absolute_max_discount_percent)
    if (
        payload.override_discount_percent is not None
        and rate(payload.override_discount_percent) > absolute_max
    ):
        raise BusinessRuleError(
            f"An override of {rate(payload.override_discount_percent)}% exceeds the "
            f"{absolute_max}% maximum that company policy permits."
        )

    request = await request_service.get_request(approval.request_id)
    if RequestStatus(request.status) != RequestStatus.PENDING_APPROVAL:
        raise WorkflowError(
            f"The request behind this approval is in status {request.status} and "
            f"is no longer awaiting a decision."
        )

    handlers = {
        ApprovalDecision.APPROVE: _handle_approve,
        ApprovalDecision.REJECT: _handle_reject,
        ApprovalDecision.REQUEST_MODIFICATION: _handle_modification,
    }
    return await handlers[payload.decision](
        approval, payload, principal=principal, request_context=request_context
    )


async def _close_approval(
    approval: Approval,
    *,
    status: ApprovalStatus,
    decision: ApprovalDecision,
    principal,
    comments: str | None,
    override: Any = None,
) -> Approval:
    now = utc_now()
    raw = await get_collection(Collections.APPROVALS).find_one_and_update(
        {"_id": object_id(str(approval.id)), "status": ApprovalStatus.PENDING.value},
        {
            "$set": encode_decimals(
                {
                    "status": status.value,
                    "decision": decision.value,
                    "decided_by": principal.id,
                    "decided_by_name": principal.full_name,
                    "decided_at": now,
                    "comments": comments,
                    "override_discount_percent": (
                        rate(override) if override is not None else None
                    ),
                    "updated_at": now,
                }
            )
        },
        return_document=ReturnDocument.AFTER,
    )
    if raw is None:
        # Another manager resolved it between the read and the write.
        raise WorkflowError("This approval was resolved by another user. Refresh.")
    return Approval.from_mongo(decode_decimals(raw))


async def _handle_approve(
    approval: Approval,
    payload: ApprovalDecisionRequest,
    *,
    principal,
    request_context: dict[str, Any] | None,
) -> dict[str, Any]:
    closed = await _close_approval(
        approval,
        status=ApprovalStatus.APPROVED,
        decision=ApprovalDecision.APPROVE,
        principal=principal,
        comments=payload.comments,
        override=payload.override_discount_percent,
    )

    # Re-run the pipeline so the quotation is priced by the normal code path.
    result = await workflow_engine.execute(
        approval.request_id,
        triggered_by=principal.id,
        trigger="APPROVAL",
        override_discount_percent=payload.override_discount_percent,
        auto_approve=True,
    )

    if result.resulting_status == RequestStatus.VALIDATION_FAILED:
        # The request went stale while it sat in the queue; reopen the task so
        # the decision is not silently lost.
        await get_collection(Collections.APPROVALS).update_one(
            {"_id": object_id(str(closed.id))},
            {
                "$set": {
                    "status": ApprovalStatus.PENDING.value,
                    "decision": None,
                    "decided_by": None,
                    "decided_by_name": None,
                    "decided_at": None,
                    "comments": (
                        "Approval could not be applied: the request no longer "
                        "passes validation."
                    ),
                    "updated_at": utc_now(),
                }
            },
        )
        raise BusinessRuleError(
            "This request can no longer be approved because it no longer passes "
            "validation.",
            details={"validation_errors": result.validation_errors},
        )

    quotation_id = result.quotation_id
    if quotation_id:
        await get_collection(Collections.QUOTATIONS).update_one(
            {"_id": object_id(quotation_id)},
            {
                "$set": {
                    "approval_id": str(closed.id),
                    "approved_by": principal.id,
                    "approved_by_name": principal.full_name,
                    "auto_approved": False,
                    "updated_at": utc_now(),
                }
            },
        )

    await audit_service.record(
        action=AuditAction.APPROVAL_DECIDED,
        entity_type="approval",
        entity_id=str(closed.id),
        summary=(
            f"Request {approval.request_number} approved by {principal.full_name}."
        ),
        actor=principal.as_actor(),
        metadata={
            "request_id": approval.request_id,
            "decision": ApprovalDecision.APPROVE.value,
            "override_discount_percent": payload.override_discount_percent,
            "quotation_id": quotation_id,
            "execution_id": result.execution_id,
        },
        **(request_context or {}),
    )

    await notification_service.notify(
        user_id=result.request.created_by,
        notification_type=NotificationType.QUOTATION_READY,
        title=f"Request {approval.request_number} approved",
        message=(
            f"{principal.full_name} approved your request. The quotation is ready "
            f"to download."
        ),
        entity_type="quotation",
        entity_id=quotation_id,
    )

    return {
        "approval": closed,
        "request": result.request,
        "quotation_id": quotation_id,
        "execution_id": result.execution_id,
    }


async def _handle_reject(
    approval: Approval,
    payload: ApprovalDecisionRequest,
    *,
    principal,
    request_context: dict[str, Any] | None,
) -> dict[str, Any]:
    closed = await _close_approval(
        approval,
        status=ApprovalStatus.REJECTED,
        decision=ApprovalDecision.REJECT,
        principal=principal,
        comments=payload.comments,
    )
    request = await _move_request(
        approval,
        RequestStatus.REJECTED,
        principal=principal,
        note=payload.comments or "Rejected by the sales manager.",
    )

    await audit_service.record(
        action=AuditAction.APPROVAL_DECIDED,
        entity_type="approval",
        entity_id=str(closed.id),
        summary=(
            f"Request {approval.request_number} rejected by {principal.full_name}."
        ),
        actor=principal.as_actor(),
        metadata={
            "request_id": approval.request_id,
            "decision": ApprovalDecision.REJECT.value,
            "comments": payload.comments,
        },
        **(request_context or {}),
    )
    await notification_service.notify(
        user_id=request.created_by,
        notification_type=NotificationType.REQUEST_REJECTED,
        title=f"Request {approval.request_number} was not approved",
        message=payload.comments or "The sales manager did not approve this request.",
        entity_type="quotation_request",
        entity_id=approval.request_id,
    )
    return {
        "approval": closed,
        "request": request,
        "quotation_id": None,
        "execution_id": None,
    }


async def _handle_modification(
    approval: Approval,
    payload: ApprovalDecisionRequest,
    *,
    principal,
    request_context: dict[str, Any] | None,
) -> dict[str, Any]:
    closed = await _close_approval(
        approval,
        status=ApprovalStatus.MODIFICATION_REQUESTED,
        decision=ApprovalDecision.REQUEST_MODIFICATION,
        principal=principal,
        comments=payload.comments,
    )
    request = await _move_request(
        approval,
        RequestStatus.MODIFICATION_REQUESTED,
        principal=principal,
        note=payload.comments or "Modifications requested by the sales manager.",
    )

    await audit_service.record(
        action=AuditAction.APPROVAL_DECIDED,
        entity_type="approval",
        entity_id=str(closed.id),
        summary=(
            f"Modifications requested on {approval.request_number} by "
            f"{principal.full_name}."
        ),
        actor=principal.as_actor(),
        metadata={
            "request_id": approval.request_id,
            "decision": ApprovalDecision.REQUEST_MODIFICATION.value,
            "comments": payload.comments,
        },
        **(request_context or {}),
    )
    await notification_service.notify(
        user_id=request.created_by,
        notification_type=NotificationType.MODIFICATION_REQUESTED,
        title=f"Changes requested on {approval.request_number}",
        message=(
            payload.comments
            or "The sales manager has asked for changes before this can be approved."
        ),
        entity_type="quotation_request",
        entity_id=approval.request_id,
    )
    return {
        "approval": closed,
        "request": request,
        "quotation_id": None,
        "execution_id": None,
    }


async def _move_request(
    approval: Approval,
    target: RequestStatus,
    *,
    principal,
    note: str,
):
    current = RequestStatus.PENDING_APPROVAL
    workflow_engine.assert_transition(current, target)

    now = utc_now()
    update: dict[str, Any] = {
        "status": target.value,
        "requires_approval": False,
        "updated_at": now,
    }
    if target == RequestStatus.REJECTED:
        update["decided_at"] = now

    await get_collection(Collections.QUOTATION_REQUESTS).update_one(
        {"_id": object_id(approval.request_id)},
        {
            "$set": update,
            "$push": {
                "status_history": StatusHistoryEntry(
                    from_status=current,
                    to_status=target,
                    actor_id=principal.id,
                    actor_name=principal.full_name,
                    note=note,
                    at=now,
                ).model_dump()
            },
        },
    )
    return await request_service.get_request(approval.request_id)


async def get_queue_context(approval: Approval) -> dict[str, Any]:
    """Everything a manager needs on the decision screen, in one read."""
    request = await request_service.get_request(approval.request_id)
    raw_customer = await get_collection(Collections.CUSTOMERS).find_one(
        {"_id": object_id(approval.customer_id)}
    )
    customer = (
        Customer.from_mongo(decode_decimals(raw_customer)) if raw_customer else None
    )
    executions = await request_service.list_executions(approval.request_id)
    history = await quotation_service.list_quotations(
        customer_id=approval.customer_id, page=1, page_size=5
    )
    return {
        "approval": approval,
        "request": request,
        "customer": customer,
        "latest_execution": executions[0] if executions else None,
        "recent_quotations": history.items,
    }
