"""`products` collection - the sellable catalogue."""

from datetime import datetime

from pydantic import Field

from app.models.common import DocumentModel, Money, Rate, utc_now
from app.models.enums import ProductStatus


class Product(DocumentModel):
    sku: str
    name: str
    description: str | None = None
    category: str
    unit: str = "pcs"
    unit_price: Money
    #: Floor price; a discount may never take the line below this.
    cost_price: Money = Field(default="0.00")
    tax_rate: Rate | None = None  # None -> fall back to the company default
    stock_quantity: int = Field(default=0, ge=0)
    #: Stock held back from quotations (allocated to confirmed orders).
    reserved_quantity: int = Field(default=0, ge=0)
    reorder_level: int = Field(default=0, ge=0)
    lead_time_days: int = Field(default=0, ge=0)
    #: Per-product override of the tiered discount ceiling, when set.
    max_discount_percent: Rate | None = None
    status: ProductStatus = ProductStatus.ACTIVE
    created_at: datetime = Field(default_factory=utc_now)
    updated_at: datetime = Field(default_factory=utc_now)

    @property
    def available_quantity(self) -> int:
        return max(self.stock_quantity - self.reserved_quantity, 0)
