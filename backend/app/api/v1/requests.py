"""Quotation request and workflow endpoints."""

from fastapi import APIRouter, Body, Query, status

from app.core.deps import CurrentUser, RequestContext, StaffUser
from app.models.common import Page, build_page
from app.models.enums import RequestStatus
from app.models.quotation_request import QuotationRequest
from app.schemas.quotation import (
    InternalNoteUpdate,
    QuotationRequestCreate,
    QuotationRequestResponse,
    QuotationRequestUpdate,
    WorkflowExecutionResponse,
    WorkflowRunResponse,
)
from app.services import request_service
from app.services.workflow_engine import WorkflowResult

router = APIRouter(prefix="/quotation-requests", tags=["Quotation requests"])


def _to_response(request: QuotationRequest) -> QuotationRequestResponse:
    return QuotationRequestResponse.model_validate(request.model_dump())


def _run_response(result: WorkflowResult) -> WorkflowRunResponse:
    return WorkflowRunResponse(
        execution_id=result.execution_id,
        outcome=result.outcome,
        resulting_status=result.resulting_status,
        requires_approval=result.request.requires_approval,
        validation_errors=result.validation_errors,
        exceptions=result.exceptions,
        approval_id=result.approval_id,
        quotation_id=result.quotation_id,
        duration_ms=result.duration_ms,
        gate=result.gate,
        attempt_number=result.attempt_number,
        retries_used=result.retries_used,
        escalation_reason=result.escalation_reason,
        escalation_detail=result.escalation_detail,
        check_report=result.check_report,
        request=_to_response(result.request),
    )


@router.get(
    "", response_model=Page[QuotationRequestResponse], summary="List quotation requests"
)
async def list_requests(
    principal: CurrentUser,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    request_status: RequestStatus | None = Query(None, alias="status"),
    customer_id: str | None = Query(None),
    search: str | None = Query(None, max_length=120),
    requires_approval: bool | None = Query(None),
) -> Page[QuotationRequestResponse]:
    """Customers see only their own requests; staff see all of them."""
    result = await request_service.list_requests(
        principal=principal,
        page=page,
        page_size=page_size,
        status=request_status.value if request_status else None,
        customer_id=customer_id,
        search=search,
        requires_approval=requires_approval,
    )
    return build_page(
        [_to_response(item) for item in result.items],
        result.meta.total,
        result.meta.page,
        result.meta.page_size,
    )


@router.post(
    "",
    status_code=status.HTTP_201_CREATED,
    summary="Create a quotation request",
    response_model=None,
)
async def create_request(
    payload: QuotationRequestCreate, principal: CurrentUser, context: RequestContext
) -> dict:
    """Create the request and, unless ``submit`` is false, run the workflow.

    Returns the workflow result when submitted, so a single call tells the
    client whether the quotation is ready or waiting on a manager.
    """
    request = await request_service.create_request(
        payload, principal=principal, request_context=context
    )
    if not payload.submit:
        return {"submitted": False, "request": _to_response(request)}

    result = await request_service.submit_request(
        str(request.id), principal=principal, request_context=context
    )
    return {"submitted": True, "workflow": _run_response(result)}


@router.get(
    "/{request_id}",
    response_model=QuotationRequestResponse,
    summary="Get a quotation request",
)
async def get_request(request_id: str, principal: CurrentUser) -> QuotationRequestResponse:
    request = await request_service.get_request(request_id)
    request_service.assert_can_view(request, principal)
    return _to_response(request)


@router.patch(
    "/{request_id}",
    response_model=QuotationRequestResponse,
    summary="Edit a draft or returned request",
)
async def update_request(
    request_id: str,
    payload: QuotationRequestUpdate,
    principal: CurrentUser,
    context: RequestContext,
) -> QuotationRequestResponse:
    request = await request_service.update_request(
        request_id, payload, principal=principal, request_context=context
    )
    return _to_response(request)


@router.post(
    "/{request_id}/submit",
    response_model=WorkflowRunResponse,
    summary="Submit a request and run the workflow",
)
async def submit_request(
    request_id: str, principal: CurrentUser, context: RequestContext
) -> WorkflowRunResponse:
    result = await request_service.submit_request(
        request_id, principal=principal, request_context=context
    )
    return _run_response(result)


@router.post(
    "/{request_id}/reprocess",
    response_model=WorkflowRunResponse,
    summary="Re-run the workflow for a request",
)
async def reprocess_request(
    request_id: str, principal: StaffUser, context: RequestContext
) -> WorkflowRunResponse:
    """Staff action for requests that failed on stale stock or catalogue data."""
    result = await request_service.rerun_workflow(
        request_id, principal=principal, request_context=context
    )
    return _run_response(result)


@router.post(
    "/{request_id}/cancel",
    response_model=QuotationRequestResponse,
    summary="Cancel a request",
)
async def cancel_request(
    request_id: str,
    principal: CurrentUser,
    context: RequestContext,
    reason: str | None = Body(None, embed=True, max_length=500),
) -> QuotationRequestResponse:
    request = await request_service.cancel_request(
        request_id, principal=principal, reason=reason, request_context=context
    )
    return _to_response(request)


@router.put(
    "/{request_id}/internal-notes",
    response_model=QuotationRequestResponse,
    summary="Set internal notes on a request",
)
async def set_internal_notes(
    request_id: str,
    payload: InternalNoteUpdate,
    principal: StaffUser,
    context: RequestContext,
) -> QuotationRequestResponse:
    request = await request_service.set_internal_notes(
        request_id,
        payload.internal_notes,
        principal=principal,
        request_context=context,
    )
    return _to_response(request)


@router.get(
    "/{request_id}/executions",
    response_model=list[WorkflowExecutionResponse],
    summary="Workflow execution history for a request",
)
async def list_executions(
    request_id: str, principal: CurrentUser
) -> list[WorkflowExecutionResponse]:
    """The step-by-step trace of every pipeline run for this request."""
    request = await request_service.get_request(request_id)
    request_service.assert_can_view(request, principal)
    executions = await request_service.list_executions(request_id)
    return [
        WorkflowExecutionResponse.model_validate(execution.model_dump())
        for execution in executions
    ]
