"""`customers` collection - the commercial party a quotation is addressed to."""

from datetime import datetime

from pydantic import EmailStr, Field

from app.models.common import DocumentModel, Money, utc_now
from app.models.enums import CustomerStatus, CustomerTier


class Address(DocumentModel):
    line1: str
    line2: str | None = None
    city: str
    state: str
    postal_code: str
    country: str = "India"


class Customer(DocumentModel):
    #: Human-readable identifier shown on documents, e.g. CUST-0007.
    code: str
    company_name: str
    contact_name: str
    email: EmailStr
    phone: str
    tier: CustomerTier = CustomerTier.STANDARD
    status: CustomerStatus = CustomerStatus.ACTIVE
    billing_address: Address | None = None
    tax_id: str | None = None
    #: Maximum open quotation value allowed before manager review.
    credit_limit: Money = Field(default="0.00")
    #: Sum of issued, unexpired quotations; maintained by the quotation service.
    outstanding_amount: Money = Field(default="0.00")
    notes: str | None = None
    created_at: datetime = Field(default_factory=utc_now)
    updated_at: datetime = Field(default_factory=utc_now)

    @property
    def available_credit(self) -> Money:
        return self.credit_limit - self.outstanding_amount
