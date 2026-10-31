"""Product availability verification.

Availability is computed from ``stock_quantity - reserved_quantity``, never from
raw stock, so units already committed to confirmed orders are not quoted twice.
"""

from __future__ import annotations

from app.core.exceptions import NotFoundError
from app.models.enums import AvailabilityStatus
from app.models.product import Product
from app.models.quotation_request import LineAvailability
from app.schemas.product import (
    AvailabilityCheckRequest,
    AvailabilityCheckResponse,
    AvailabilityLineResponse,
)
from app.services import product_service, settings_service


def evaluate(
    product: Product, quantity: int, *, allow_backorder: bool
) -> LineAvailability:
    """Classify one line as in stock, partially available or out of stock."""
    available = product.available_quantity

    if available >= quantity:
        status = AvailabilityStatus.IN_STOCK
        shortfall = 0
    elif available > 0:
        status = AvailabilityStatus.PARTIAL
        shortfall = quantity - available
    else:
        status = AvailabilityStatus.OUT_OF_STOCK
        shortfall = quantity

    return LineAvailability(
        status=status,
        available_quantity=available,
        shortfall=shortfall,
        lead_time_days=product.lead_time_days if shortfall else 0,
        backorder_allowed=allow_backorder,
    )


def describe(product: Product, quantity: int, availability: LineAvailability) -> str:
    """Plain-language explanation shown next to the line in the UI."""
    if availability.status == AvailabilityStatus.IN_STOCK:
        return f"All {quantity} {product.unit} are available from stock."
    if availability.status == AvailabilityStatus.PARTIAL:
        detail = (
            f"{availability.available_quantity} of {quantity} {product.unit} are in "
            f"stock; {availability.shortfall} short"
        )
    else:
        detail = f"None of the {quantity} {product.unit} requested are in stock"

    if availability.backorder_allowed:
        return (
            f"{detail}. The balance can be backordered with a lead time of "
            f"{availability.lead_time_days} day(s)."
        )
    return f"{detail}, and backorders are not permitted."


async def check_items(payload: AvailabilityCheckRequest) -> AvailabilityCheckResponse:
    """Stand-alone availability check, used before a request is submitted."""
    settings_doc = await settings_service.get_settings_document()
    allow_backorder = settings_doc.quotation_policy.allow_backorder

    product_ids = [item.product_id for item in payload.items]
    products = await product_service.get_products_by_ids(product_ids)

    missing = [pid for pid in product_ids if pid not in products]
    if missing:
        raise NotFoundError(
            "One or more products in the request could not be found.",
            details={"missing_product_ids": missing},
        )

    lines: list[AvailabilityLineResponse] = []
    all_available = True
    for item in payload.items:
        product = products[item.product_id]
        availability = evaluate(product, item.quantity, allow_backorder=allow_backorder)
        if availability.status != AvailabilityStatus.IN_STOCK:
            all_available = False
        lines.append(
            AvailabilityLineResponse(
                product_id=item.product_id,
                sku=product.sku,
                name=product.name,
                requested_quantity=item.quantity,
                available_quantity=availability.available_quantity,
                status=availability.status,
                shortfall=availability.shortfall,
                lead_time_days=availability.lead_time_days,
                backorder_allowed=availability.backorder_allowed,
                message=describe(product, item.quantity, availability),
            )
        )

    return AvailabilityCheckResponse(all_available=all_available, lines=lines)
