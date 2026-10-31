"""Request/response schemas for the product catalogue."""

from datetime import datetime

from pydantic import Field

from app.models.common import AppModel, Money, PyObjectId, Rate
from app.models.enums import AvailabilityStatus, ProductStatus


class ProductCreateRequest(AppModel):
    sku: str = Field(min_length=2, max_length=40)
    name: str = Field(min_length=2, max_length=160)
    description: str | None = Field(default=None, max_length=1000)
    category: str = Field(min_length=2, max_length=60)
    unit: str = Field(default="pcs", max_length=16)
    unit_price: Money = Field(gt=0)
    cost_price: Money = Field(default="0.00", ge=0)
    tax_rate: Rate | None = Field(default=None, ge=0, le=100)
    stock_quantity: int = Field(default=0, ge=0)
    reserved_quantity: int = Field(default=0, ge=0)
    reorder_level: int = Field(default=0, ge=0)
    lead_time_days: int = Field(default=0, ge=0)
    max_discount_percent: Rate | None = Field(default=None, ge=0, le=100)
    status: ProductStatus = ProductStatus.ACTIVE


class ProductUpdateRequest(AppModel):
    name: str | None = Field(default=None, min_length=2, max_length=160)
    description: str | None = Field(default=None, max_length=1000)
    category: str | None = Field(default=None, min_length=2, max_length=60)
    unit: str | None = Field(default=None, max_length=16)
    unit_price: Money | None = Field(default=None, gt=0)
    cost_price: Money | None = Field(default=None, ge=0)
    tax_rate: Rate | None = Field(default=None, ge=0, le=100)
    stock_quantity: int | None = Field(default=None, ge=0)
    reserved_quantity: int | None = Field(default=None, ge=0)
    reorder_level: int | None = Field(default=None, ge=0)
    lead_time_days: int | None = Field(default=None, ge=0)
    max_discount_percent: Rate | None = Field(default=None, ge=0, le=100)
    status: ProductStatus | None = None


class ProductResponse(AppModel):
    id: PyObjectId
    sku: str
    name: str
    description: str | None = None
    category: str
    unit: str
    unit_price: Money
    cost_price: Money
    tax_rate: Rate | None = None
    stock_quantity: int
    reserved_quantity: int
    available_quantity: int
    reorder_level: int
    lead_time_days: int
    max_discount_percent: Rate | None = None
    status: ProductStatus
    created_at: datetime
    updated_at: datetime


class CatalogueProductResponse(ProductResponse):
    """Catalogue view for customers: hides cost, adds their discount entitlement."""

    cost_price: Money = Field(default="0.00", exclude=True)
    #: Maximum discount this viewer could request at ``quantity`` = 1.
    indicative_max_discount_percent: Rate = Field(default="0")
    low_stock: bool = False


class AvailabilityCheckItem(AppModel):
    product_id: PyObjectId
    quantity: int = Field(ge=1)


class AvailabilityCheckRequest(AppModel):
    items: list[AvailabilityCheckItem] = Field(min_length=1, max_length=50)


class AvailabilityLineResponse(AppModel):
    product_id: PyObjectId
    sku: str
    name: str
    requested_quantity: int
    available_quantity: int
    status: AvailabilityStatus
    shortfall: int
    lead_time_days: int
    backorder_allowed: bool
    message: str


class AvailabilityCheckResponse(AppModel):
    all_available: bool
    lines: list[AvailabilityLineResponse]
