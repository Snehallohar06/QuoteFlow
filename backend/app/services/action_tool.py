"""The action tool: performs the approved quotation operation.

Its job is the *doing* — allocate a number, store the quotation, render the PDF,
update the request. It reports what it did and makes no claim about whether the
result is correct; proving that is the checker tool's job, and the checker does
not trust this module's output.

Idempotency is the other responsibility here. A request may only ever have one
quotation, so the tool checks for an existing one before issuing and returns it
unchanged if found. The guarantee is backed by a unique index on
``quotations.request_id``, so two concurrent runs cannot both insert.
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field
from pathlib import Path

from pymongo.errors import DuplicateKeyError

from app.core.exceptions import BusinessRuleError
from app.db.mongo import Collections, get_collection
from app.models.common import object_id, utc_now
from app.models.company_settings import CompanySettings
from app.models.customer import Customer
from app.models.quotation import Quotation
from app.models.quotation_request import QuotationRequest
from app.utils.money import decode_decimals

logger = logging.getLogger(__name__)


@dataclass(slots=True)
class ActionResult:
    """What the action tool did, for the trace and for the checker."""

    quotation: Quotation
    quotation_id: str
    quotation_number: str
    #: True when an existing quotation was returned rather than a new one issued.
    reused_existing: bool = False
    pdf_path: str | None = None
    pdf_bytes: int = 0
    operations: list[str] = field(default_factory=list)

    def as_output(self) -> dict:
        return {
            "quotation_id": self.quotation_id,
            "quotation_number": self.quotation_number,
            "reused_existing": self.reused_existing,
            "pdf_bytes": self.pdf_bytes,
            "operations": self.operations,
        }


async def find_existing(request_id: str) -> Quotation | None:
    """The quotation already issued for this request, if any."""
    raw = await get_collection(Collections.QUOTATIONS).find_one(
        {"request_id": str(request_id)}
    )
    return Quotation.from_mongo(decode_decimals(raw)) if raw else None


async def execute(
    request: QuotationRequest,
    *,
    customer: Customer,
    settings_doc: CompanySettings,
    auto_approved: bool,
    approval_id: str | None = None,
    approved_by: str | None = None,
    approved_by_name: str | None = None,
) -> ActionResult:
    """Issue the quotation for an approved request and render its document.

    Safe to call more than once: a second call returns the quotation the first
    call created.
    """
    # Imported here: quotation_service imports this module's models, and a
    # top-level import would make the pair circular.
    from app.services import quotation_service

    existing = await find_existing(str(request.id))
    if existing is not None:
        logger.info(
            "Quotation %s already exists for %s; reusing it",
            existing.quotation_number,
            request.request_number,
        )
        result = ActionResult(
            quotation=existing,
            quotation_id=str(existing.id),
            quotation_number=existing.quotation_number,
            reused_existing=True,
            operations=["reused_existing_quotation"],
        )
        # Still make sure the document exists on disk - a previous run may have
        # stored the quotation and then failed while rendering.
        path = await _render_pdf(existing)
        result.pdf_path = str(path)
        result.pdf_bytes = path.stat().st_size if path.exists() else 0
        result.operations.append("ensured_pdf")
        return result

    try:
        quotation = await quotation_service.generate_for_request(
            request,
            customer=customer,
            settings_doc=settings_doc,
            auto_approved=auto_approved,
            approval_id=approval_id,
            approved_by=approved_by,
            approved_by_name=approved_by_name,
        )
    except DuplicateKeyError:
        # Lost a race with a concurrent run. The other run's quotation is the
        # one of record, so adopt it rather than failing.
        adopted = await find_existing(str(request.id))
        if adopted is None:
            raise
        logger.info(
            "Concurrent run issued %s for %s; adopting it",
            adopted.quotation_number,
            request.request_number,
        )
        path = await _render_pdf(adopted)
        return ActionResult(
            quotation=adopted,
            quotation_id=str(adopted.id),
            quotation_number=adopted.quotation_number,
            reused_existing=True,
            pdf_path=str(path),
            pdf_bytes=path.stat().st_size if path.exists() else 0,
            operations=["adopted_concurrent_quotation", "ensured_pdf"],
        )

    operations = ["allocated_number", "stored_quotation"]

    path = await _render_pdf(quotation)
    operations.append("rendered_pdf")

    await get_collection(Collections.QUOTATIONS).update_one(
        {"_id": object_id(str(quotation.id))},
        {"$set": {"pdf_path": str(path), "pdf_generated_at": utc_now()}},
    )
    quotation.pdf_path = str(path)
    operations.append("recorded_pdf_path")

    return ActionResult(
        quotation=quotation,
        quotation_id=str(quotation.id),
        quotation_number=quotation.quotation_number,
        pdf_path=str(path),
        pdf_bytes=path.stat().st_size if path.exists() else 0,
        operations=operations,
    )


async def _render_pdf(quotation: Quotation) -> Path:
    """Render the PDF, raising if the file did not end up on disk.

    ReportLab is synchronous and CPU-bound, so it runs in a worker thread. A
    write failure surfaces as OSError, which the budget classifies as transient
    and retries.
    """
    from app.services import pdf_service

    path = await asyncio.to_thread(pdf_service.render_quotation_pdf, quotation)
    if not path.exists() or path.stat().st_size == 0:
        raise OSError(
            f"The quotation PDF for {quotation.quotation_number} was not written."
        )
    return path


async def mark_completed(request_id: str, quotation_id: str) -> None:
    """Record the quotation on the request once the success gate has passed."""
    await get_collection(Collections.QUOTATION_REQUESTS).update_one(
        {"_id": object_id(request_id)},
        {"$set": {"quotation_id": quotation_id, "updated_at": utc_now()}},
    )


async def assert_single_quotation(request_id: str) -> None:
    """Guard against a request ending up with more than one quotation."""
    count = await get_collection(Collections.QUOTATIONS).count_documents(
        {"request_id": str(request_id)}
    )
    if count > 1:
        raise BusinessRuleError(
            f"Request {request_id} has {count} quotations; exactly one is allowed.",
            details={"quotation_count": count},
        )
