"""Issuing, reading and verifying quotations."""

from __future__ import annotations

import asyncio
from datetime import timedelta
from pathlib import Path
from typing import Any

from pymongo import ReturnDocument

from app.core.exceptions import BusinessRuleError, NotFoundError, PermissionDeniedError
from app.db.mongo import Collections, get_collection
from app.models.common import build_page, ensure_utc, object_id, utc_now
from app.models.company_settings import CompanySettings
from app.models.customer import Customer
from app.models.enums import AuditAction, QuotationStatus
from app.models.quotation import PartySnapshot, Quotation
from app.models.quotation_request import QuotationRequest
from app.services import (
    audit_service,
    customer_service,
    numbering,
    pdf_service,
    settings_service,
    verification_service,
)
from app.utils.money import decode_decimals, encode_decimals


def _seller_snapshot(settings_doc: CompanySettings) -> PartySnapshot:
    profile = settings_doc.profile
    return PartySnapshot(
        name=profile.name,
        legal_name=profile.legal_name,
        email=profile.email,
        phone=profile.phone,
        address_lines=list(profile.address_lines),
        tax_id=profile.tax_id,
    )


def _buyer_snapshot(customer: Customer) -> PartySnapshot:
    address_lines: list[str] = []
    if customer.billing_address:
        address = customer.billing_address
        address_lines = [
            part
            for part in [
                address.line1,
                address.line2,
                " ".join(filter(None, [address.city, address.postal_code])).strip(),
                " ".join(filter(None, [address.state, address.country])).strip(),
            ]
            if part
        ]
    return PartySnapshot(
        name=customer.company_name,
        contact_name=customer.contact_name,
        email=customer.email,
        phone=customer.phone,
        address_lines=address_lines,
        tax_id=customer.tax_id,
        code=customer.code,
    )


async def generate_for_request(
    request: QuotationRequest,
    *,
    customer: Customer,
    settings_doc: CompanySettings | None = None,
    auto_approved: bool = False,
    approval_id: str | None = None,
    approved_by: str | None = None,
    approved_by_name: str | None = None,
) -> Quotation:
    """Create the quotation document for an approved request.

    Called by the workflow engine (auto-approved path) and by the approval
    service (manager-approved path), so both routes produce identical documents.
    """
    if request.pricing is None:
        raise BusinessRuleError(
            "A quotation cannot be issued for a request that has not been priced."
        )

    settings_doc = settings_doc or await settings_service.get_settings_document()
    policy = settings_doc.quotation_policy

    quotation_number = await numbering.next_document_number(
        policy.quotation_number_prefix
    )
    verification_code = await _unique_verification_code()
    issued_at = utc_now()

    items_payload = [item.model_dump() for item in request.items]
    pricing_payload = request.pricing.model_dump()

    integrity_hash = verification_service.compute_integrity_hash(
        quotation_number=quotation_number,
        request_number=request.request_number,
        customer_id=str(request.customer_id),
        verification_code=verification_code,
        items=items_payload,
        pricing=pricing_payload,
    )

    quotation = Quotation(
        quotation_number=quotation_number,
        request_id=str(request.id),
        request_number=request.request_number,
        customer_id=str(request.customer_id),
        seller=_seller_snapshot(settings_doc),
        buyer=_buyer_snapshot(customer),
        items=request.items,
        pricing=request.pricing,
        terms=list(policy.terms),
        status=QuotationStatus.ISSUED,
        verification_code=verification_code,
        integrity_hash=integrity_hash,
        approval_id=approval_id,
        approved_by=approved_by,
        approved_by_name=approved_by_name,
        auto_approved=auto_approved,
        issued_at=issued_at,
        valid_until=issued_at + timedelta(days=policy.validity_days),
    )

    result = await get_collection(Collections.QUOTATIONS).insert_one(
        encode_decimals(quotation.model_dump(exclude={"id"}))
    )
    quotation.id = str(result.inserted_id)

    await get_collection(Collections.QUOTATION_REQUESTS).update_one(
        {"_id": object_id(str(request.id))},
        {"$set": {"quotation_id": quotation.id, "updated_at": utc_now()}},
    )

    # Keep the customer's credit exposure in step with the quotations on file.
    await customer_service.recalculate_outstanding(str(request.customer_id))

    await audit_service.record(
        action=AuditAction.QUOTATION_GENERATED,
        entity_type="quotation",
        entity_id=quotation.id,
        summary=(
            f"Quotation {quotation_number} issued for {customer.company_name} "
            f"({pricing_payload['currency']} {request.pricing.final_amount})."
        ),
        actor=(
            {"id": approved_by, "role": "SALES_MANAGER"}
            if approved_by
            else {"id": None, "email": "system", "role": "WORKFLOW"}
        ),
        metadata={
            "request_id": str(request.id),
            "request_number": request.request_number,
            "auto_approved": auto_approved,
            "final_amount": request.pricing.final_amount,
            "verification_code": verification_code,
        },
    )
    return quotation


async def _unique_verification_code(attempts: int = 5) -> str:
    """Draw a verification code that is not already in use."""
    collection = get_collection(Collections.QUOTATIONS)
    for _ in range(attempts):
        code = verification_service.generate_verification_code()
        if await collection.find_one({"verification_code": code}, {"_id": 1}) is None:
            return code
    raise BusinessRuleError(
        "Could not allocate a unique verification code. Please retry."
    )


async def get_quotation(quotation_id: str) -> Quotation:
    raw = await get_collection(Collections.QUOTATIONS).find_one(
        {"_id": object_id(quotation_id)}
    )
    if raw is None:
        raise NotFoundError("Quotation not found.")
    return Quotation.from_mongo(decode_decimals(raw))


async def assert_can_access(quotation: Quotation, principal) -> None:
    """A customer may only read quotations addressed to them."""
    if principal.is_staff:
        return
    if principal.customer_id and str(quotation.customer_id) == principal.customer_id:
        return
    raise PermissionDeniedError("This quotation belongs to another customer.")


async def list_quotations(
    *,
    page: int = 1,
    page_size: int = 20,
    customer_id: str | None = None,
    status: str | None = None,
    search: str | None = None,
):
    query: dict[str, Any] = {}
    if customer_id:
        query["customer_id"] = customer_id
    if status:
        query["status"] = status
    if search:
        pattern = {"$regex": search.strip(), "$options": "i"}
        query["$or"] = [
            {"quotation_number": pattern},
            {"request_number": pattern},
            {"verification_code": pattern},
            {"buyer.name": pattern},
        ]

    collection = get_collection(Collections.QUOTATIONS)
    total = await collection.count_documents(query)
    cursor = (
        collection.find(query)
        .sort("issued_at", -1)
        .skip((page - 1) * page_size)
        .limit(page_size)
    )
    documents = await cursor.to_list(length=page_size)
    items = [Quotation.from_mongo(decode_decimals(doc)) for doc in documents]
    return build_page(items, total, page, page_size)


async def ensure_pdf(quotation: Quotation) -> Path:
    """Return the PDF path, rendering the file if it is not already on disk.

    ReportLab is synchronous and CPU-bound, so the render runs in a worker
    thread to keep the event loop free.
    """
    if quotation.pdf_path:
        existing = Path(quotation.pdf_path)
        if existing.exists():
            return existing

    path = await asyncio.to_thread(pdf_service.render_quotation_pdf, quotation)
    await get_collection(Collections.QUOTATIONS).update_one(
        {"_id": object_id(str(quotation.id))},
        {"$set": {"pdf_path": str(path), "pdf_generated_at": utc_now()}},
    )
    quotation.pdf_path = str(path)
    return path


async def register_download(quotation: Quotation, actor: dict[str, Any]) -> None:
    await get_collection(Collections.QUOTATIONS).update_one(
        {"_id": object_id(str(quotation.id))}, {"$inc": {"download_count": 1}}
    )
    await audit_service.record(
        action=AuditAction.QUOTATION_DOWNLOADED,
        entity_type="quotation",
        entity_id=str(quotation.id),
        summary=f"Quotation {quotation.quotation_number} downloaded.",
        actor=actor,
    )


async def verify_by_code(code: str, *, record_audit: bool = True) -> dict[str, Any]:
    """Public verification: confirm a code and report the document's integrity.

    Deliberately returns a thin payload - enough to confirm what was quoted to
    whom and for how much, without exposing line-level internals to an
    unauthenticated caller.
    """
    normalised = code.strip().upper()
    raw = await get_collection(Collections.QUOTATIONS).find_one(
        {"verification_code": normalised}
    )
    if raw is None:
        return {
            "valid": False,
            "reason": "No quotation matches that verification code.",
        }

    decoded = decode_decimals(raw)
    quotation = Quotation.from_mongo(decoded)
    integrity_ok = verification_service.verify_document(decoded)
    valid_until = ensure_utc(quotation.valid_until)
    expired = valid_until is not None and valid_until < utc_now()

    if record_audit:
        await audit_service.record(
            action=AuditAction.QUOTATION_VERIFIED,
            entity_type="quotation",
            entity_id=str(quotation.id),
            summary=f"Quotation {quotation.quotation_number} verified by code.",
            actor={"id": None, "email": "public", "role": "PUBLIC"},
            metadata={"integrity_ok": integrity_ok, "expired": expired},
        )

    return {
        "valid": integrity_ok,
        "reason": (
            None
            if integrity_ok
            else "The stored amounts do not match the integrity digest issued with "
            "this quotation."
        ),
        "quotation_number": quotation.quotation_number,
        "request_number": quotation.request_number,
        "customer_name": quotation.buyer.name,
        "issued_at": quotation.issued_at,
        "valid_until": quotation.valid_until,
        "expired": expired,
        "status": quotation.status,
        "currency": quotation.pricing.currency,
        "final_amount": quotation.pricing.final_amount,
        "line_count": quotation.pricing.line_count,
        "auto_approved": quotation.auto_approved,
        "approved_by": quotation.approved_by_name,
        "integrity_hash": quotation.integrity_hash,
    }


async def expire_due_quotations() -> int:
    """Flip ISSUED quotations past their validity date to EXPIRED.

    Called on startup and exposed to managers, so the pipeline figures reported
    by analytics do not count stale quotations as live.
    """
    now = utc_now()
    result = await get_collection(Collections.QUOTATIONS).update_many(
        {"status": QuotationStatus.ISSUED.value, "valid_until": {"$lt": now}},
        {"$set": {"status": QuotationStatus.EXPIRED.value, "updated_at": now}},
    )
    return result.modified_count


async def set_status(
    quotation_id: str, status: QuotationStatus, *, actor: dict[str, Any]
) -> Quotation:
    raw = await get_collection(Collections.QUOTATIONS).find_one_and_update(
        {"_id": object_id(quotation_id)},
        {"$set": {"status": status.value, "updated_at": utc_now()}},
        return_document=ReturnDocument.AFTER,
    )
    if raw is None:
        raise NotFoundError("Quotation not found.")
    quotation = Quotation.from_mongo(decode_decimals(raw))
    await customer_service.recalculate_outstanding(str(quotation.customer_id))
    await audit_service.record(
        action=AuditAction.QUOTATION_GENERATED,
        entity_type="quotation",
        entity_id=quotation_id,
        summary=f"Quotation {quotation.quotation_number} marked {status.value}.",
        actor=actor,
    )
    return quotation
