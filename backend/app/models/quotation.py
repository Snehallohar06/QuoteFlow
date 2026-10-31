"""`quotations` collection - the immutable document issued to a customer.

A quotation is a snapshot: it copies the customer and company details that were
true at issue time, so reprinting the PDF years later reproduces the original.
The integrity hash makes tampering detectable.
"""

from datetime import datetime

from pydantic import Field

from app.models.common import DocumentModel, PyObjectId, utc_now
from app.models.enums import QuotationStatus
from app.models.quotation_request import PricingSummary, RequestLine


class PartySnapshot(DocumentModel):
    """Frozen copy of a company / customer block as printed on the document."""

    name: str
    legal_name: str | None = None
    contact_name: str | None = None
    email: str | None = None
    phone: str | None = None
    address_lines: list[str] = Field(default_factory=list)
    tax_id: str | None = None
    code: str | None = None


class Quotation(DocumentModel):
    quotation_number: str
    request_id: PyObjectId
    request_number: str
    customer_id: PyObjectId

    seller: PartySnapshot
    buyer: PartySnapshot

    items: list[RequestLine]
    pricing: PricingSummary
    terms: list[str] = Field(default_factory=list)

    status: QuotationStatus = QuotationStatus.ISSUED
    #: Short code printed on the PDF and used by the public verify endpoint.
    verification_code: str
    #: HMAC-SHA256 over the canonical financial payload.
    integrity_hash: str
    #: Set when approval was needed; absent for auto-approved quotations.
    approval_id: PyObjectId | None = None
    approved_by: PyObjectId | None = None
    approved_by_name: str | None = None
    auto_approved: bool = False

    issued_at: datetime = Field(default_factory=utc_now)
    valid_until: datetime
    pdf_path: str | None = None
    pdf_generated_at: datetime | None = None
    download_count: int = 0
    created_at: datetime = Field(default_factory=utc_now)
    updated_at: datetime = Field(default_factory=utc_now)
