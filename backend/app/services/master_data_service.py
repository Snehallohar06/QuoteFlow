"""Master-data authorisation: an employee proposes, a manager decides.

A sales employee cannot write to the ``customers`` or ``products`` collections.
They submit the record here; it waits in the manager's queue; and the customer
or product is created only when a manager authorises it. The record is created
by the *existing* create services with the manager as the actor, so an
authorised addition is indistinguishable in the data from one a manager typed
in themselves - and the audit trail names both the proposer and the authoriser.
"""

from __future__ import annotations

from typing import Any

from pymongo import ReturnDocument
from pymongo.errors import DuplicateKeyError

from app.core.exceptions import (
    BusinessRuleError,
    ConflictError,
    NotFoundError,
    PermissionDeniedError,
)
from app.db.mongo import Collections, get_collection
from app.models.common import build_page, object_id, utc_now
from app.models.enums import (
    AuditAction,
    MasterDataEntity,
    MasterDataRequestStatus,
    NotificationType,
    UserRole,
)
from app.models.master_data_request import MasterDataRequest
from app.schemas.customer import CustomerCreateRequest
from app.schemas.master_data import (
    CustomerProposalRequest,
    MasterDataRequestResponse,
    ProductProposalRequest,
)
from app.schemas.product import ProductCreateRequest
from app.services import (
    audit_service,
    customer_service,
    notification_service,
    numbering,
    product_service,
)
from app.utils.money import decode_decimals, encode_decimals

#: Audit action per decision, so the trail distinguishes an authorised addition
#: from a refused one without the reader parsing a summary line.
_DECISION_ACTIONS = {
    MasterDataRequestStatus.APPROVED: AuditAction.MASTER_DATA_APPROVED,
    MasterDataRequestStatus.REJECTED: AuditAction.MASTER_DATA_REJECTED,
}

_ENTITY_LABELS = {
    MasterDataEntity.CUSTOMER: "customer",
    MasterDataEntity.PRODUCT: "product",
}


def to_response(request: MasterDataRequest) -> MasterDataRequestResponse:
    return MasterDataRequestResponse.model_validate(request.model_dump())


def _entity_word(entity_type: str) -> str:
    return _ENTITY_LABELS.get(MasterDataEntity(entity_type), "record")


async def get_request(request_id: str) -> MasterDataRequest:
    raw = await get_collection(Collections.MASTER_DATA_REQUESTS).find_one(
        {"_id": object_id(request_id)}
    )
    if raw is None:
        raise NotFoundError("Master-data request not found.")
    return MasterDataRequest.from_mongo(decode_decimals(raw))


async def get_request_for(request_id: str, *, principal) -> MasterDataRequest:
    """Fetch one proposal, scoped to what the caller may see.

    A manager sees every proposal because they decide them. An employee sees
    only their own: another employee's draft customer record is not theirs to
    read, and a 404 rather than a 403 keeps the existence of the row private.
    """
    request = await get_request(request_id)
    if not principal.is_manager and request.requested_by != principal.id:
        raise NotFoundError("Master-data request not found.")
    return request


# ---------------------------------------------------------------------------
# Submission
# ---------------------------------------------------------------------------


async def _insert(
    *,
    entity_type: MasterDataEntity,
    payload: dict[str, Any],
    label: str,
    dedupe_key: str,
    reason: str | None,
    principal,
    request_context: dict[str, Any] | None,
) -> MasterDataRequest:
    request = MasterDataRequest(
        reference=await numbering.next_document_number("MDR", width=5),
        entity_type=entity_type,
        payload=payload,
        label=label,
        dedupe_key=dedupe_key,
        reason=reason,
        requested_by=principal.id,
        requested_by_name=principal.full_name,
        requested_by_email=principal.email,
    )
    try:
        result = await get_collection(Collections.MASTER_DATA_REQUESTS).insert_one(
            encode_decimals(request.model_dump(exclude={"id"}))
        )
    except DuplicateKeyError as exc:
        # The partial unique index on (entity_type, dedupe_key) over PENDING
        # rows: somebody has already queued this exact record.
        raise ConflictError(
            f"A request to add that {_entity_word(entity_type)} is already waiting "
            "for a manager's approval."
        ) from exc

    request.id = str(result.inserted_id)

    await audit_service.record(
        action=AuditAction.MASTER_DATA_REQUESTED,
        entity_type="master_data_request",
        entity_id=request.id,
        summary=(
            f"{principal.full_name} requested approval to add the "
            f"{_entity_word(entity_type)} {label} ({request.reference})."
        ),
        actor=principal.as_actor(),
        metadata={
            "reference": request.reference,
            "entity_type": str(entity_type),
            "label": label,
        },
        **(request_context or {}),
    )
    await notification_service.notify_role(
        role=UserRole.SALES_MANAGER,
        notification_type=NotificationType.MASTER_DATA_REQUESTED,
        title=f"Approval needed: new {_entity_word(entity_type)}",
        message=(
            f"{principal.full_name} is asking to add the "
            f"{_entity_word(entity_type)} {label}."
        ),
        entity_type="master_data_request",
        entity_id=request.id,
    )
    return request


async def submit_customer(
    proposal: CustomerProposalRequest,
    *,
    principal,
    request_context: dict[str, Any] | None = None,
) -> MasterDataRequest:
    """Queue a proposed customer for a manager's approval."""
    email = proposal.customer.email.strip().lower()

    # Fail now rather than after a manager has spent a decision on it.
    if await get_collection(Collections.CUSTOMERS).find_one({"email": email}):
        raise ConflictError("A customer with that email address already exists.")

    payload = proposal.customer.model_dump()
    payload["email"] = email
    return await _insert(
        entity_type=MasterDataEntity.CUSTOMER,
        payload=payload,
        label=proposal.customer.company_name,
        dedupe_key=email,
        reason=proposal.reason,
        principal=principal,
        request_context=request_context,
    )


async def submit_product(
    proposal: ProductProposalRequest,
    *,
    principal,
    request_context: dict[str, Any] | None = None,
) -> MasterDataRequest:
    """Queue a proposed product for a manager's approval."""
    sku = proposal.product.sku.strip().upper()

    if await get_collection(Collections.PRODUCTS).find_one({"sku": sku}):
        raise ConflictError(f"A product with SKU {sku} already exists.")

    payload = proposal.product.model_dump()
    payload["sku"] = sku
    return await _insert(
        entity_type=MasterDataEntity.PRODUCT,
        payload=payload,
        label=f"{sku} — {proposal.product.name}",
        dedupe_key=sku,
        reason=proposal.reason,
        principal=principal,
        request_context=request_context,
    )


# ---------------------------------------------------------------------------
# Queue
# ---------------------------------------------------------------------------


async def list_requests(
    *,
    page: int = 1,
    page_size: int = 20,
    status: str | None = None,
    entity_type: str | None = None,
    requested_by: str | None = None,
):
    query: dict[str, Any] = {}
    if status:
        query["status"] = status
    if entity_type:
        query["entity_type"] = entity_type
    if requested_by:
        query["requested_by"] = requested_by

    collection = get_collection(Collections.MASTER_DATA_REQUESTS)
    total = await collection.count_documents(query)
    cursor = (
        collection.find(query)
        # Open proposals first - the queue exists to be worked through - then
        # newest first within each status.
        .sort([("status", 1), ("created_at", -1)])
        .skip((page - 1) * page_size)
        .limit(page_size)
    )
    documents = await cursor.to_list(length=page_size)
    items = [
        to_response(MasterDataRequest.from_mongo(decode_decimals(doc)))
        for doc in documents
    ]
    return build_page(items, total, page, page_size)


async def pending_count() -> int:
    return await get_collection(Collections.MASTER_DATA_REQUESTS).count_documents(
        {"status": MasterDataRequestStatus.PENDING.value}
    )


# ---------------------------------------------------------------------------
# Decision
# ---------------------------------------------------------------------------


async def _settle(
    request: MasterDataRequest,
    *,
    status: MasterDataRequestStatus,
    principal,
    comments: str | None,
    created_entity_id: str | None = None,
    created_entity_label: str | None = None,
) -> MasterDataRequest:
    """Write the decision, but only onto a proposal that is still open.

    The status is part of the filter rather than checked beforehand, so two
    managers deciding at the same moment cannot both record a decision: the
    second update matches nothing and is reported as the conflict it is.
    """
    updates: dict[str, Any] = {
        "status": status.value,
        "decided_by": principal.id,
        "decided_by_name": principal.full_name,
        "decided_at": utc_now(),
        "decision_comments": comments,
        "updated_at": utc_now(),
    }
    if created_entity_id:
        updates["created_entity_id"] = created_entity_id
        updates["created_entity_label"] = created_entity_label

    raw = await get_collection(Collections.MASTER_DATA_REQUESTS).find_one_and_update(
        {
            "_id": object_id(request.id),
            "status": MasterDataRequestStatus.PENDING.value,
        },
        {"$set": updates},
        return_document=ReturnDocument.AFTER,
    )
    if raw is None:
        raise ConflictError(
            f"Master-data request {request.reference} has already been decided."
        )
    return MasterDataRequest.from_mongo(decode_decimals(raw))


async def decide(
    request_id: str,
    *,
    approve: bool,
    comments: str | None,
    principal,
    request_context: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Authorise or refuse a proposed record.

    On approval the payload is re-validated against the current create schema
    before anything is written: a proposal that has been sitting in the queue
    must still satisfy today's rules, not the ones in force when it was raised.
    """
    request = await get_request(request_id)
    if not request.is_open:
        raise ConflictError(
            f"Master-data request {request.reference} has already been decided."
        )

    if not approve:
        if not (comments or "").strip():
            raise BusinessRuleError(
                "A reason is required when refusing a master-data request."
            )
        settled = await _settle(
            request,
            status=MasterDataRequestStatus.REJECTED,
            principal=principal,
            comments=comments,
        )
        await _audit_decision(settled, principal=principal, context=request_context)
        await _notify_requester(settled)
        return {"request": settled, "customer": None, "product": None}

    entity_type = MasterDataEntity(request.entity_type)
    created_customer = None
    created_product = None

    # The record is created first and the proposal settled second. If the create
    # fails - a SKU taken while the proposal waited, a rule that has since
    # tightened - the proposal is left PENDING and the error surfaces, so
    # nothing is lost and the manager can decide again once it is fixed.
    if entity_type == MasterDataEntity.CUSTOMER:
        created_customer = await customer_service.create_customer(
            CustomerCreateRequest.model_validate(request.payload),
            actor=principal.as_actor(),
            request_context=request_context,
        )
        created_id = created_customer.id
        created_label = f"{created_customer.code} — {created_customer.company_name}"
    else:
        created_product = await product_service.create_product(
            ProductCreateRequest.model_validate(request.payload),
            actor=principal.as_actor(),
            request_context=request_context,
        )
        created_id = created_product.id
        created_label = f"{created_product.sku} — {created_product.name}"

    settled = await _settle(
        request,
        status=MasterDataRequestStatus.APPROVED,
        principal=principal,
        comments=comments,
        created_entity_id=created_id,
        created_entity_label=created_label,
    )
    await _audit_decision(settled, principal=principal, context=request_context)
    await _notify_requester(settled)
    return {
        "request": settled,
        "customer": created_customer,
        "product": created_product,
    }


async def withdraw(
    request_id: str,
    *,
    principal,
    request_context: dict[str, Any] | None = None,
) -> MasterDataRequest:
    """Let the employee who raised a proposal take it back while it is open."""
    request = await get_request(request_id)
    if request.requested_by != principal.id:
        raise PermissionDeniedError(
            "Only the employee who raised a master-data request may withdraw it."
        )
    if not request.is_open:
        raise ConflictError(
            f"Master-data request {request.reference} has already been decided."
        )

    settled = await _settle(
        request,
        status=MasterDataRequestStatus.WITHDRAWN,
        principal=principal,
        comments=None,
    )
    await audit_service.record(
        action=AuditAction.MASTER_DATA_WITHDRAWN,
        entity_type="master_data_request",
        entity_id=settled.id,
        summary=(
            f"{principal.full_name} withdrew the request to add "
            f"{settled.label} ({settled.reference})."
        ),
        actor=principal.as_actor(),
        metadata={"reference": settled.reference},
        **(request_context or {}),
    )
    return settled


async def _audit_decision(
    request: MasterDataRequest, *, principal, context: dict[str, Any] | None
) -> None:
    status = MasterDataRequestStatus(request.status)
    verb = "approved" if status == MasterDataRequestStatus.APPROVED else "refused"
    await audit_service.record(
        action=_DECISION_ACTIONS[status],
        entity_type="master_data_request",
        entity_id=request.id,
        summary=(
            f"{principal.full_name} {verb} the request to add "
            f"{request.label} ({request.reference})."
        ),
        actor=principal.as_actor(),
        metadata={
            "reference": request.reference,
            "entity_type": request.entity_type,
            "requested_by": request.requested_by_name,
            "created_entity_id": request.created_entity_id,
            "comments": request.decision_comments,
        },
        **(context or {}),
    )


async def _notify_requester(request: MasterDataRequest) -> None:
    status = MasterDataRequestStatus(request.status)
    word = _entity_word(request.entity_type)
    if status == MasterDataRequestStatus.APPROVED:
        title = f"Approved: new {word}"
        message = (
            f"{request.decided_by_name} approved {request.label}. "
            f"It is now in the {word} list."
        )
    else:
        title = f"Not approved: new {word}"
        message = (
            f"{request.decided_by_name} did not approve {request.label}. "
            f"{request.decision_comments or ''}".strip()
        )

    await notification_service.notify(
        user_id=request.requested_by,
        notification_type=NotificationType.MASTER_DATA_DECIDED,
        title=title,
        message=message,
        entity_type="master_data_request",
        entity_id=request.id,
    )
