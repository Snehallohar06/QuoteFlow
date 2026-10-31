"""Request/response schemas for customer management."""

from datetime import datetime

from pydantic import EmailStr, Field

from app.models.common import AppModel, Money, PyObjectId
from app.models.customer import Address
from app.models.enums import CustomerStatus, CustomerTier


class CustomerCreateRequest(AppModel):
    company_name: str = Field(min_length=2, max_length=160)
    contact_name: str = Field(min_length=2, max_length=120)
    email: EmailStr
    phone: str = Field(min_length=6, max_length=24)
    tier: CustomerTier = CustomerTier.STANDARD
    billing_address: Address | None = None
    tax_id: str | None = Field(default=None, max_length=32)
    credit_limit: Money = Field(default="0.00", ge=0)
    notes: str | None = Field(default=None, max_length=1000)


class CustomerUpdateRequest(AppModel):
    company_name: str | None = Field(default=None, min_length=2, max_length=160)
    contact_name: str | None = Field(default=None, min_length=2, max_length=120)
    email: EmailStr | None = None
    phone: str | None = Field(default=None, min_length=6, max_length=24)
    tier: CustomerTier | None = None
    status: CustomerStatus | None = None
    billing_address: Address | None = None
    tax_id: str | None = Field(default=None, max_length=32)
    credit_limit: Money | None = Field(default=None, ge=0)
    notes: str | None = Field(default=None, max_length=1000)


class CustomerResponse(AppModel):
    id: PyObjectId
    code: str
    company_name: str
    contact_name: str
    email: EmailStr
    phone: str
    tier: CustomerTier
    status: CustomerStatus
    billing_address: Address | None = None
    tax_id: str | None = None
    credit_limit: Money
    outstanding_amount: Money
    available_credit: Money
    notes: str | None = None
    created_at: datetime
    updated_at: datetime


class CustomerSummaryResponse(AppModel):
    """Aggregated activity for one customer, shown on the sales console."""

    customer: CustomerResponse
    total_requests: int
    requests_by_status: dict[str, int]
    total_quotations: int
    quoted_value: Money
    last_request_at: datetime | None = None
