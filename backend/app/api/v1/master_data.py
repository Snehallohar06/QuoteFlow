"""Master-data authorisation endpoints: an employee proposes, a manager decides."""

from fastapi import APIRouter, Query, status

from app.core.deps import ManagerUser, RequestContext, StaffUser
from app.models.common import Page
from app.models.enums import MasterDataEntity, MasterDataRequestStatus
from app.schemas.master_data import (
    CustomerProposalRequest,
    MasterDataDecisionRequest,
    MasterDataDecisionResponse,
    MasterDataRequestResponse,
    ProductProposalRequest,
)
from app.services import master_data_service

router = APIRouter(prefix="/master-data-requests", tags=["Master data approval"])


@router.post(
    "/customers",
    response_model=MasterDataRequestResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Ask a manager to approve a new customer",
)
async def submit_customer(
    payload: CustomerProposalRequest, principal: StaffUser, context: RequestContext
) -> MasterDataRequestResponse:
    """Queue a proposed customer. Nothing is written to ``customers`` yet."""
    request = await master_data_service.submit_customer(
        payload, principal=principal, request_context=context
    )
    return master_data_service.to_response(request)


@router.post(
    "/products",
    response_model=MasterDataRequestResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Ask a manager to approve a new product",
)
async def submit_product(
    payload: ProductProposalRequest, principal: StaffUser, context: RequestContext
) -> MasterDataRequestResponse:
    """Queue a proposed product. Nothing is written to ``products`` yet."""
    request = await master_data_service.submit_product(
        payload, principal=principal, request_context=context
    )
    return master_data_service.to_response(request)


@router.get(
    "",
    response_model=Page[MasterDataRequestResponse],
    summary="List master-data requests",
)
async def list_requests(
    principal: StaffUser,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    request_status: MasterDataRequestStatus | None = Query(None, alias="status"),
    entity_type: MasterDataEntity | None = Query(None),
    mine_only: bool = Query(False, description="Only the caller's own requests"),
) -> Page[MasterDataRequestResponse]:
    """A manager sees the whole queue; an employee sees only what they raised.

    ``mine_only`` is a convenience for a manager who wants their own; for an
    employee the scoping is imposed regardless of what they ask for.
    """
    requested_by = principal.id if (mine_only or not principal.is_manager) else None
    return await master_data_service.list_requests(
        page=page,
        page_size=page_size,
        status=request_status.value if request_status else None,
        entity_type=entity_type.value if entity_type else None,
        requested_by=requested_by,
    )


@router.get("/pending-count", summary="Number of open master-data requests")
async def pending_count(_: StaffUser) -> dict:
    return {"pending": await master_data_service.pending_count()}


@router.get(
    "/{request_id}",
    response_model=MasterDataRequestResponse,
    summary="Get one master-data request",
)
async def get_request(request_id: str, principal: StaffUser) -> MasterDataRequestResponse:
    request = await master_data_service.get_request_for(request_id, principal=principal)
    return master_data_service.to_response(request)


@router.post(
    "/{request_id}/decision",
    response_model=MasterDataDecisionResponse,
    summary="Approve or refuse a proposed record",
)
async def decide(
    request_id: str,
    payload: MasterDataDecisionRequest,
    principal: ManagerUser,
    context: RequestContext,
) -> MasterDataDecisionResponse:
    """Approving creates the customer or product; refusing requires a reason."""
    outcome = await master_data_service.decide(
        request_id,
        approve=payload.approve,
        comments=payload.comments,
        principal=principal,
        request_context=context,
    )
    return MasterDataDecisionResponse(
        request=master_data_service.to_response(outcome["request"]),
        customer=outcome["customer"],
        product=outcome["product"],
    )


@router.post(
    "/{request_id}/withdraw",
    response_model=MasterDataRequestResponse,
    summary="Withdraw a request you raised",
)
async def withdraw(
    request_id: str, principal: StaffUser, context: RequestContext
) -> MasterDataRequestResponse:
    request = await master_data_service.withdraw(
        request_id, principal=principal, request_context=context
    )
    return master_data_service.to_response(request)
