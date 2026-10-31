"""Customer management endpoints (sales staff and managers)."""

from fastapi import APIRouter, Query, status

from app.core.deps import (
    CustomerAuthority,
    ManagerUser,
    RequestContext,
    StaffUser,
)
from app.models.common import Page
from app.models.enums import CustomerStatus
from app.schemas.customer import (
    CustomerCreateRequest,
    CustomerResponse,
    CustomerSummaryResponse,
    CustomerUpdateRequest,
)
from app.services import customer_service

router = APIRouter(prefix="/customers", tags=["Customers"])


@router.get("", response_model=Page[CustomerResponse], summary="List customers")
async def list_customers(
    _: StaffUser,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    search: str | None = Query(None, max_length=120),
    customer_status: CustomerStatus | None = Query(None, alias="status"),
    tier: str | None = Query(None, max_length=20),
) -> Page[CustomerResponse]:
    return await customer_service.list_customers(
        page=page,
        page_size=page_size,
        search=search,
        status=customer_status.value if customer_status else None,
        tier=tier,
    )


@router.post(
    "",
    response_model=CustomerResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create a customer",
)
async def create_customer(
    payload: CustomerCreateRequest,
    principal: CustomerAuthority,
    context: RequestContext,
) -> CustomerResponse:
    """Manager only.

    A sales employee submits the record to
    ``POST /master-data-requests/customers`` instead, and it is created here -
    by the same code, with the manager as the actor - once they authorise it.
    """
    return await customer_service.create_customer(
        payload, actor=principal.as_actor(), request_context=context
    )


@router.get("/{customer_id}", response_model=CustomerResponse, summary="Get a customer")
async def get_customer(customer_id: str, _: StaffUser) -> CustomerResponse:
    customer = await customer_service.get_customer(customer_id)
    return customer_service.to_response(customer)


@router.patch(
    "/{customer_id}", response_model=CustomerResponse, summary="Update a customer"
)
async def update_customer(
    customer_id: str,
    payload: CustomerUpdateRequest,
    principal: StaffUser,
    context: RequestContext,
) -> CustomerResponse:
    return await customer_service.update_customer(
        customer_id, payload, actor=principal.as_actor(), request_context=context
    )


@router.post(
    "/{customer_id}/status",
    response_model=CustomerResponse,
    summary="Activate, hold or block a customer",
)
async def set_customer_status(
    customer_id: str,
    new_status: CustomerStatus,
    principal: ManagerUser,
    context: RequestContext,
) -> CustomerResponse:
    """Blocking a customer stops new requests and fails any in flight."""
    return await customer_service.set_status(
        customer_id, new_status, actor=principal.as_actor(), request_context=context
    )


@router.get(
    "/{customer_id}/summary",
    response_model=CustomerSummaryResponse,
    summary="Activity summary for a customer",
)
async def customer_summary(customer_id: str, _: StaffUser) -> CustomerSummaryResponse:
    return await customer_service.get_summary(customer_id)
