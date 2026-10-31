"""`company_settings` collection - the rule book the engines read at runtime.

Nothing in the pricing, discount or approval engines hard-codes a threshold:
every number lives here and is editable by a sales manager, so the deployed
workflow can be re-tuned without a code change.
"""

from datetime import datetime

from pydantic import Field, field_validator, model_validator

from app.models.common import DocumentModel, Money, PyObjectId, Rate, utc_now
from app.models.enums import CustomerTier

#: There is exactly one active settings document, found by this key.
DEFAULT_SETTINGS_KEY = "default"


class DiscountTier(DocumentModel):
    """A quantity band and the discount ceiling that applies inside it."""

    min_quantity: int = Field(ge=1)
    #: ``None`` means "and above" - the open-ended top band.
    max_quantity: int | None = None
    max_discount_percent: Rate
    label: str | None = None

    @model_validator(mode="after")
    def _check_band(self):
        if self.max_quantity is not None and self.max_quantity < self.min_quantity:
            raise ValueError("max_quantity must be greater than or equal to min_quantity")
        return self

    def matches(self, quantity: int) -> bool:
        if quantity < self.min_quantity:
            return False
        return self.max_quantity is None or quantity <= self.max_quantity


class DiscountPolicy(DocumentModel):
    """Tiered discount ceilings plus the loyalty bonus layered on top."""

    tiers: list[DiscountTier] = Field(
        default_factory=lambda: [
            DiscountTier(
                min_quantity=1, max_quantity=5, max_discount_percent="2", label="1-5 units"
            ),
            DiscountTier(
                min_quantity=6,
                max_quantity=20,
                max_discount_percent="5",
                label="6-20 units",
            ),
            DiscountTier(
                min_quantity=21,
                max_quantity=50,
                max_discount_percent="10",
                label="21-50 units",
            ),
            DiscountTier(
                min_quantity=51,
                max_quantity=None,
                max_discount_percent="15",
                label="51+ units",
            ),
        ]
    )
    #: Extra percentage points granted by customer tier, added to the band ceiling.
    tier_bonus_percent: dict[str, Rate] = Field(
        default_factory=lambda: {
            CustomerTier.STANDARD.value: "0",
            CustomerTier.SILVER.value: "1",
            CustomerTier.GOLD.value: "2",
            CustomerTier.PLATINUM.value: "3",
        }
    )
    #: Hard ceiling a manager cannot override; requests above it are auto-rejected.
    absolute_max_discount_percent: Rate = Field(default="40")
    #: Refuse any discount that would price a line below its cost price.
    enforce_cost_floor: bool = True

    @field_validator("tiers")
    @classmethod
    def _tiers_not_empty(cls, value: list[DiscountTier]) -> list[DiscountTier]:
        if not value:
            raise ValueError("At least one discount tier must be configured.")
        return sorted(value, key=lambda tier: tier.min_quantity)

    def tier_for(self, quantity: int) -> DiscountTier | None:
        for tier in self.tiers:
            if tier.matches(quantity):
                return tier
        return None

    def bonus_for(self, customer_tier: str) -> Rate:
        from app.utils.money import rate

        return rate(self.tier_bonus_percent.get(customer_tier, 0))


class TaxPolicy(DocumentModel):
    name: str = "GST"
    #: Default rate, applied when a product does not define its own.
    rate_percent: Rate = Field(default="18")
    #: EXCLUSIVE: tax is added on top of the discounted amount.
    mode: str = "EXCLUSIVE"


class ApprovalPolicy(DocumentModel):
    """When a priced request must stop for a human decision."""

    require_on_discount_exception: bool = True
    #: Requests whose final amount reaches this value always need a manager.
    order_value_threshold: Money = Field(default="500000.00")
    require_on_stock_shortfall: bool = True
    require_on_credit_breach: bool = True
    #: Hours a manager has to decide; drives the analytics SLA figure.
    approval_sla_hours: int = Field(default=24, ge=1)


class QuotationPolicy(DocumentModel):
    validity_days: int = Field(default=30, ge=1)
    request_number_prefix: str = "QR"
    quotation_number_prefix: str = "QT"
    currency: str = "INR"
    currency_symbol: str = "Rs."
    #: Printed on every generated PDF.
    terms: list[str] = Field(
        default_factory=lambda: [
            "Prices are valid until the quotation expiry date shown above.",
            "Taxes are charged as applicable at the time of invoicing.",
            "Delivery timelines are indicative and subject to stock availability.",
            "Payment terms: 30 days from the date of invoice.",
        ]
    )
    #: Allow quoting more units than are currently in stock.
    allow_backorder: bool = True


class ExecutionPolicy(DocumentModel):
    """Budget limits that stop the workflow running away.

    Every boundary the engine enforces is a number here, so a deployment can be
    tightened or loosened without a code change - and so a test can shrink a
    limit to one and prove the limit is real.
    """

    #: Retries of a single step after a TRANSIENT failure. Permanent failures
    #: are never retried, however much budget is left.
    max_retries_per_step: int = Field(default=3, ge=0, le=10)
    #: Pipeline runs allowed for one request across its whole life. Guards
    #: against a resubmit loop.
    max_attempts_per_request: int = Field(default=10, ge=1, le=100)
    #: Wall-clock ceiling for one pipeline run.
    max_execution_ms: int = Field(default=30_000, ge=100)
    #: Wall-clock ceiling across every run for one request.
    max_total_execution_ms: int = Field(default=180_000, ge=100)
    #: Resource ceilings, checked during validation.
    max_lines_per_request: int = Field(default=50, ge=1, le=500)
    max_quantity_per_line: int = Field(default=1_000_000, ge=1)
    #: Pause between retries, in milliseconds. Doubles each attempt.
    retry_backoff_ms: int = Field(default=50, ge=0, le=5_000)

    def backoff_for(self, attempt: int) -> float:
        """Seconds to wait before retry number ``attempt`` (1-based)."""
        if self.retry_backoff_ms <= 0:
            return 0.0
        return (self.retry_backoff_ms * (2 ** (attempt - 1))) / 1000


class CompanyProfile(DocumentModel):
    name: str = "Northwind Industrial Supplies"
    legal_name: str = "Northwind Industrial Supplies Pvt. Ltd."
    address_lines: list[str] = Field(
        default_factory=lambda: [
            "Plot 14, MIDC Industrial Area",
            "Pune, Maharashtra 411019",
            "India",
        ]
    )
    email: str = "sales@northwind-supplies.example"
    phone: str = "+91 20 4000 1200"
    website: str = "www.northwind-supplies.example"
    tax_id: str = "27AABCN1234A1ZV"


class CompanySettings(DocumentModel):
    key: str = DEFAULT_SETTINGS_KEY
    profile: CompanyProfile = Field(default_factory=CompanyProfile)
    discount_policy: DiscountPolicy = Field(default_factory=DiscountPolicy)
    tax_policy: TaxPolicy = Field(default_factory=TaxPolicy)
    approval_policy: ApprovalPolicy = Field(default_factory=ApprovalPolicy)
    quotation_policy: QuotationPolicy = Field(default_factory=QuotationPolicy)
    execution_policy: ExecutionPolicy = Field(default_factory=ExecutionPolicy)
    updated_by: PyObjectId | None = None
    created_at: datetime = Field(default_factory=utc_now)
    updated_at: datetime = Field(default_factory=utc_now)
