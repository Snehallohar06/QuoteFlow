"""Quotation endpoints, including PDF download and public verification."""

from fastapi import APIRouter, Path, Query
from fastapi.responses import FileResponse

from app.core.deps import CurrentUser, ManagerUser, StaffUser
from app.models.common import Page, build_page
from app.models.enums import QuotationStatus
from app.models.quotation import Quotation
from app.schemas.quotation import QuotationResponse, VerificationResponse
from app.services import quotation_service

router = APIRouter(prefix="/quotations", tags=["Quotations"])

#: Mounted separately so verification needs no authentication.
public_router = APIRouter(prefix="/verify", tags=["Verification"])


def _to_response(quotation: Quotation) -> QuotationResponse:
    return QuotationResponse.model_validate(quotation.model_dump())


@router.get("", response_model=Page[QuotationResponse], summary="List quotations")
async def list_quotations(
    principal: CurrentUser,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    quotation_status: QuotationStatus | None = Query(None, alias="status"),
    customer_id: str | None = Query(None),
    search: str | None = Query(None, max_length=120),
) -> Page[QuotationResponse]:
    """Customers see only their own quotations."""
    scoped_customer = (
        principal.customer_id if principal.is_customer else customer_id
    )
    result = await quotation_service.list_quotations(
        page=page,
        page_size=page_size,
        customer_id=scoped_customer,
        status=quotation_status.value if quotation_status else None,
        search=search,
    )
    return build_page(
        [_to_response(item) for item in result.items],
        result.meta.total,
        result.meta.page,
        result.meta.page_size,
    )


@router.get("/{quotation_id}", response_model=QuotationResponse, summary="Get a quotation")
async def get_quotation(quotation_id: str, principal: CurrentUser) -> QuotationResponse:
    quotation = await quotation_service.get_quotation(quotation_id)
    await quotation_service.assert_can_access(quotation, principal)
    return _to_response(quotation)


@router.get(
    "/{quotation_id}/pdf",
    summary="Download the quotation PDF",
    response_class=FileResponse,
)
async def download_pdf(quotation_id: str, principal: CurrentUser) -> FileResponse:
    """Render on first request, then serve the stored file."""
    quotation = await quotation_service.get_quotation(quotation_id)
    await quotation_service.assert_can_access(quotation, principal)

    path = await quotation_service.ensure_pdf(quotation)
    await quotation_service.register_download(quotation, principal.as_actor())

    return FileResponse(
        path=path,
        media_type="application/pdf",
        filename=f"{quotation.quotation_number}.pdf",
    )


@router.post(
    "/{quotation_id}/status",
    response_model=QuotationResponse,
    summary="Mark a quotation accepted, withdrawn or expired",
)
async def set_status(
    quotation_id: str, new_status: QuotationStatus, principal: ManagerUser
) -> QuotationResponse:
    quotation = await quotation_service.set_status(
        quotation_id, new_status, actor=principal.as_actor()
    )
    return _to_response(quotation)


@router.post("/expire-due", summary="Expire quotations past their validity date")
async def expire_due(_: StaffUser) -> dict:
    """Housekeeping action; also runs automatically at application startup."""
    return {"expired": await quotation_service.expire_due_quotations()}


@public_router.get(
    "/{code}",
    response_model=VerificationResponse,
    summary="Verify a quotation by its printed code",
)
async def verify(
    code: str = Path(
        ...,
        min_length=4,
        max_length=32,
        description="The verification code printed on the quotation PDF",
    ),
) -> VerificationResponse:
    """Unauthenticated check that a quotation is genuine and unaltered.

    The response reports whether the stored amounts still match the integrity
    digest issued with the document, and whether it is still within validity.
    """
    result = await quotation_service.verify_by_code(code)
    return VerificationResponse.model_validate(result)
