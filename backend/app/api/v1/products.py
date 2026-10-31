"""Product catalogue endpoints."""

from fastapi import APIRouter, Body, Query, status

from app.core.deps import (
    CurrentUser,
    ManagerUser,
    ProductAuthority,
    RequestContext,
    StaffUser,
)
from app.models.common import Page
from app.models.customer import Customer
from app.models.enums import CustomerTier, ProductStatus
from app.schemas.product import (
    AvailabilityCheckRequest,
    AvailabilityCheckResponse,
    CatalogueProductResponse,
    ProductCreateRequest,
    ProductResponse,
    ProductUpdateRequest,
)
from app.services import availability_service, customer_service, product_service

router = APIRouter(prefix="/products", tags=["Products"])


@router.get(
    "/catalogue",
    response_model=Page[CatalogueProductResponse],
    summary="Browse the catalogue",
)
async def browse_catalogue(
    principal: CurrentUser,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    search: str | None = Query(None, max_length=120),
    category: str | None = Query(None, max_length=60),
    in_stock_only: bool = Query(False),
) -> Page[CatalogueProductResponse]:
    """Active products with the discount the caller is entitled to ask for.

    Available to every role; a customer's own tier drives the figure shown.
    """
    tier = CustomerTier.STANDARD.value
    if principal.customer_id:
        customer: Customer = await customer_service.get_customer(principal.customer_id)
        tier = customer.tier

    return await product_service.list_catalogue(
        customer_tier=tier,
        page=page,
        page_size=page_size,
        search=search,
        category=category,
        in_stock_only=in_stock_only,
    )


@router.get("/categories", summary="Catalogue categories with counts")
async def list_categories(_: CurrentUser) -> list[dict]:
    return await product_service.list_categories()


@router.post(
    "/check-availability",
    response_model=AvailabilityCheckResponse,
    summary="Check stock for a set of lines",
)
async def check_availability(
    payload: AvailabilityCheckRequest, _: CurrentUser
) -> AvailabilityCheckResponse:
    """Pre-flight stock check, so a customer can adjust before submitting."""
    return await availability_service.check_items(payload)


@router.get(
    "", response_model=Page[ProductResponse], summary="List products (internal view)"
)
async def list_products(
    _: StaffUser,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    search: str | None = Query(None, max_length=120),
    category: str | None = Query(None, max_length=60),
    product_status: ProductStatus | None = Query(None, alias="status"),
    in_stock_only: bool = Query(False),
) -> Page[ProductResponse]:
    """Full product records including cost price, for staff only."""
    return await product_service.list_products(
        page=page,
        page_size=page_size,
        search=search,
        category=category,
        status=product_status.value if product_status else None,
        in_stock_only=in_stock_only,
    )


@router.post(
    "",
    response_model=ProductResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Add a product",
)
async def create_product(
    payload: ProductCreateRequest,
    principal: ProductAuthority,
    context: RequestContext,
) -> ProductResponse:
    """Manager only.

    A sales employee submits the record to
    ``POST /master-data-requests/products`` instead, and it is created here once
    they authorise it.
    """
    return await product_service.create_product(
        payload, actor=principal.as_actor(), request_context=context
    )


@router.get("/{product_id}", response_model=ProductResponse, summary="Get a product")
async def get_product(product_id: str, _: StaffUser) -> ProductResponse:
    product = await product_service.get_product(product_id)
    return product_service.to_response(product)


@router.patch("/{product_id}", response_model=ProductResponse, summary="Update a product")
async def update_product(
    product_id: str,
    payload: ProductUpdateRequest,
    principal: StaffUser,
    context: RequestContext,
) -> ProductResponse:
    return await product_service.update_product(
        product_id, payload, actor=principal.as_actor(), request_context=context
    )


@router.post(
    "/{product_id}/stock",
    response_model=ProductResponse,
    summary="Apply a stock movement",
)
async def adjust_stock(
    product_id: str,
    principal: StaffUser,
    context: RequestContext,
    delta: int = Body(..., embed=True, description="Relative change, may be negative"),
    reason: str | None = Body(None, embed=True, max_length=200),
) -> ProductResponse:
    return await product_service.adjust_stock(
        product_id,
        delta,
        actor=principal.as_actor(),
        reason=reason,
        request_context=context,
    )


@router.delete(
    "/{product_id}", response_model=ProductResponse, summary="Discontinue a product"
)
async def discontinue_product(
    product_id: str, principal: ManagerUser, context: RequestContext
) -> ProductResponse:
    """Soft delete: the product is marked discontinued, never removed."""
    return await product_service.discontinue_product(
        product_id, actor=principal.as_actor(), request_context=context
    )
