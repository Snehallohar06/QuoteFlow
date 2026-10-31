"""Customer management."""

from __future__ import annotations

from typing import Any

from pymongo import ReturnDocument
from pymongo.errors import DuplicateKeyError

from app.core.exceptions import ConflictError, NotFoundError
from app.db.mongo import Collections, get_collection
from app.models.common import build_page, object_id, utc_now
from app.models.customer import Customer
from app.models.enums import AuditAction, CustomerStatus, RequestStatus
from app.schemas.customer import (
    CustomerCreateRequest,
    CustomerResponse,
    CustomerSummaryResponse,
    CustomerUpdateRequest,
)
from app.services import audit_service, numbering
from app.utils.money import ZERO, decode_decimals, encode_decimals, money, to_decimal

#: Statuses that still count towards a customer's open pipeline. ESCALATED is
#: included: the request is parked, not finished.
OPEN_REQUEST_STATUSES = [
    RequestStatus.ESCALATED.value,
    RequestStatus.SUBMITTED.value,
    RequestStatus.UNDER_VALIDATION.value,
    RequestStatus.PRICED.value,
    RequestStatus.PENDING_APPROVAL.value,
]


def to_response(customer: Customer) -> CustomerResponse:
    data = customer.model_dump()
    data["available_credit"] = customer.available_credit
    return CustomerResponse.model_validate(data)


async def get_customer(customer_id: str) -> Customer:
    raw = await get_collection(Collections.CUSTOMERS).find_one(
        {"_id": object_id(customer_id)}
    )
    if raw is None:
        raise NotFoundError("Customer not found.")
    return Customer.from_mongo(decode_decimals(raw))


async def list_customers(
    *,
    page: int = 1,
    page_size: int = 20,
    search: str | None = None,
    status: str | None = None,
    tier: str | None = None,
):
    query: dict[str, Any] = {}
    if status:
        query["status"] = status
    if tier:
        query["tier"] = tier
    if search:
        # Case-insensitive partial match so a fragment of a company name or
        # customer code typed into the search box finds the record.
        pattern = {"$regex": search.strip(), "$options": "i"}
        query["$or"] = [
            {"company_name": pattern},
            {"contact_name": pattern},
            {"code": pattern},
            {"email": pattern},
        ]

    collection = get_collection(Collections.CUSTOMERS)
    total = await collection.count_documents(query)
    cursor = (
        collection.find(query)
        .sort("created_at", -1)
        .skip((page - 1) * page_size)
        .limit(page_size)
    )
    documents = await cursor.to_list(length=page_size)
    items = [
        to_response(Customer.from_mongo(decode_decimals(doc))) for doc in documents
    ]
    return build_page(items, total, page, page_size)


async def create_customer(
    payload: CustomerCreateRequest,
    *,
    actor: dict[str, Any],
    request_context: dict[str, Any] | None = None,
) -> CustomerResponse:
    email = payload.email.strip().lower()
    collection = get_collection(Collections.CUSTOMERS)
    if await collection.find_one({"email": email}):
        raise ConflictError("A customer with that email address already exists.")

    customer = Customer(
        code=await numbering.next_document_number("CUST", width=4),
        company_name=payload.company_name,
        contact_name=payload.contact_name,
        email=email,
        phone=payload.phone,
        tier=payload.tier,
        billing_address=payload.billing_address,
        tax_id=payload.tax_id,
        credit_limit=payload.credit_limit,
        notes=payload.notes,
    )
    try:
        result = await collection.insert_one(
            encode_decimals(customer.model_dump(exclude={"id"}))
        )
    except DuplicateKeyError as exc:
        raise ConflictError(
            "A customer with that email address already exists."
        ) from exc

    customer.id = str(result.inserted_id)
    await audit_service.record(
        action=AuditAction.CUSTOMER_CREATED,
        entity_type="customer",
        entity_id=customer.id,
        summary=f"Customer {customer.code} ({customer.company_name}) created.",
        actor=actor,
        **(request_context or {}),
    )
    return to_response(customer)


async def update_customer(
    customer_id: str,
    payload: CustomerUpdateRequest,
    *,
    actor: dict[str, Any],
    request_context: dict[str, Any] | None = None,
) -> CustomerResponse:
    existing = await get_customer(customer_id)
    updates = payload.model_dump(exclude_unset=True, exclude_none=True)
    if not updates:
        return to_response(existing)

    if "email" in updates:
        updates["email"] = updates["email"].strip().lower()
        clash = await get_collection(Collections.CUSTOMERS).find_one(
            {"email": updates["email"], "_id": {"$ne": object_id(customer_id)}}
        )
        if clash:
            raise ConflictError("Another customer already uses that email address.")

    changed_fields = list(updates)
    updates["updated_at"] = utc_now()
    raw = await get_collection(Collections.CUSTOMERS).find_one_and_update(
        {"_id": object_id(customer_id)},
        {"$set": encode_decimals(updates)},
        return_document=ReturnDocument.AFTER,
    )
    updated = Customer.from_mongo(decode_decimals(raw))

    await audit_service.record(
        action=AuditAction.CUSTOMER_UPDATED,
        entity_type="customer",
        entity_id=customer_id,
        summary=f"Customer {existing.code} updated.",
        actor=actor,
        changes=audit_service.diff(
            existing.model_dump(mode="json"),
            updated.model_dump(mode="json"),
            changed_fields,
        ),
        **(request_context or {}),
    )
    return to_response(updated)


async def set_status(
    customer_id: str,
    status: CustomerStatus,
    *,
    actor: dict[str, Any],
    request_context: dict[str, Any] | None = None,
) -> CustomerResponse:
    """Put a customer on hold or block them. Blocked customers cannot submit."""
    existing = await get_customer(customer_id)
    raw = await get_collection(Collections.CUSTOMERS).find_one_and_update(
        {"_id": object_id(customer_id)},
        {"$set": {"status": status.value, "updated_at": utc_now()}},
        return_document=ReturnDocument.AFTER,
    )
    await audit_service.record(
        action=AuditAction.CUSTOMER_UPDATED,
        entity_type="customer",
        entity_id=customer_id,
        summary=f"Customer {existing.code} status changed to {status.value}.",
        actor=actor,
        changes={"status": {"before": existing.status, "after": status.value}},
        **(request_context or {}),
    )
    return to_response(Customer.from_mongo(decode_decimals(raw)))


async def get_summary(customer_id: str) -> CustomerSummaryResponse:
    """Activity roll-up for one customer."""
    customer = await get_customer(customer_id)
    requests = get_collection(Collections.QUOTATION_REQUESTS)

    status_cursor = await requests.aggregate(
        [
            {"$match": {"customer_id": customer_id}},
            {"$group": {"_id": "$status", "count": {"$sum": 1}}},
        ]
    )
    status_rows = await status_cursor.to_list(length=None)
    requests_by_status = {row["_id"]: row["count"] for row in status_rows}

    latest = await requests.find_one(
        {"customer_id": customer_id}, sort=[("created_at", -1)]
    )

    quotation_cursor = await get_collection(Collections.QUOTATIONS).aggregate(
        [
            {"$match": {"customer_id": customer_id}},
            {
                "$group": {
                    "_id": None,
                    "count": {"$sum": 1},
                    "value": {"$sum": "$pricing.final_amount"},
                }
            },
        ]
    )
    quotation_rows = await quotation_cursor.to_list(length=1)
    quoted_value = (
        money(to_decimal(quotation_rows[0]["value"])) if quotation_rows else ZERO
    )

    return CustomerSummaryResponse(
        customer=to_response(customer),
        total_requests=sum(requests_by_status.values()),
        requests_by_status=requests_by_status,
        total_quotations=quotation_rows[0]["count"] if quotation_rows else 0,
        quoted_value=quoted_value,
        last_request_at=latest.get("created_at") if latest else None,
    )


async def recalculate_outstanding(customer_id: str) -> None:
    """Refresh ``outstanding_amount`` from the live, unexpired quotations.

    Derived rather than incremented, so the figure cannot drift out of step with
    the quotations it summarises.
    """
    cursor = await get_collection(Collections.QUOTATIONS).aggregate(
        [
            {
                "$match": {
                    "customer_id": customer_id,
                    "status": {"$in": ["ISSUED", "ACCEPTED"]},
                    "valid_until": {"$gte": utc_now()},
                }
            },
            {"$group": {"_id": None, "total": {"$sum": "$pricing.final_amount"}}},
        ]
    )
    rows = await cursor.to_list(length=1)

    total = money(to_decimal(rows[0]["total"])) if rows else ZERO
    await get_collection(Collections.CUSTOMERS).update_one(
        {"_id": object_id(customer_id)},
        {
            "$set": {
                "outstanding_amount": encode_decimals(total),
                "updated_at": utc_now(),
            }
        },
    )
