"""Manager approval endpoints."""

from fastapi import APIRouter, Query

from app.core.deps import ManagerUser, RequestContext, StaffUser
from app.models.approval import Approval
from app.models.common import Page, build_page
from app.models.enums import ApprovalStatus
from app.schemas.quotation import (
    ApprovalDecisionRequest,
    ApprovalDecisionResponse,
    ApprovalResponse,
    QuotationRequestResponse,
)
from app.services import approval_service

router = APIRouter(prefix="/approvals", tags=["Approvals"])


def _to_response(approval: Approval) -> ApprovalResponse:
    return ApprovalResponse.model_validate(approval.model_dump())


@router.get("", response_model=Page[ApprovalResponse], summary="List approval tasks")
async def list_approvals(
    _: StaffUser,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    approval_status: ApprovalStatus | None = Query(None, alias="status"),
    customer_id: str | None = Query(None),
    overdue_only: bool = Query(False, description="Only tasks past their SLA"),
) -> Page[ApprovalResponse]:
    """Sales employees may monitor the queue; only managers can decide."""
    result = await approval_service.list_approvals(
        page=page,
        page_size=page_size,
        status=approval_status.value if approval_status else None,
        customer_id=customer_id,
        overdue_only=overdue_only,
    )
    return build_page(
        [_to_response(item) for item in result.items],
        result.meta.total,
        result.meta.page,
        result.meta.page_size,
    )


@router.get("/pending-count", summary="Number of open approval tasks")
async def pending_count(_: StaffUser) -> dict:
    return {"pending": await approval_service.pending_count()}


@router.get("/{approval_id}", summary="Approval task with full decision context")
async def get_approval(approval_id: str, _: StaffUser) -> dict:
    """The task, the request, the customer and the latest execution in one read."""
    approval = await approval_service.get_approval(approval_id)
    context = await approval_service.get_queue_context(approval)
    return {
        "approval": _to_response(context["approval"]),
        "request": QuotationRequestResponse.model_validate(
            context["request"].model_dump()
        ),
        "customer": context["customer"],
        "latest_execution": context["latest_execution"],
        "recent_quotations": context["recent_quotations"],
    }


@router.post(
    "/{approval_id}/decision",
    response_model=ApprovalDecisionResponse,
    summary="Approve, reject or request modifications",
)
async def decide(
    approval_id: str,
    payload: ApprovalDecisionRequest,
    principal: ManagerUser,
    context: RequestContext,
) -> ApprovalDecisionResponse:
    """Record the decision.

    An approval re-runs the workflow (optionally with an override discount) and
    issues the quotation; a rejection or modification request returns the
    request to the submitter with the manager's comment.
    """
    outcome = await approval_service.decide(
        approval_id, payload, principal=principal, request_context=context
    )
    return ApprovalDecisionResponse(
        approval=_to_response(outcome["approval"]),
        request=QuotationRequestResponse.model_validate(
            outcome["request"].model_dump()
        ),
        quotation_id=outcome["quotation_id"],
        execution_id=outcome["execution_id"],
    )
