"""In-app notification endpoints."""

from fastapi import APIRouter, Query, status

from app.core.deps import CurrentUser
from app.models.common import Page
from app.models.notification import Notification
from app.services import notification_service

router = APIRouter(prefix="/notifications", tags=["Notifications"])


@router.get("", response_model=Page[Notification], summary="Your notifications")
async def list_notifications(
    principal: CurrentUser,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    unread_only: bool = Query(False),
) -> Page[Notification]:
    return await notification_service.list_for_user(
        principal.id, page=page, page_size=page_size, unread_only=unread_only
    )


@router.get("/unread-count", summary="Number of unread notifications")
async def unread_count(principal: CurrentUser) -> dict:
    return {"unread": await notification_service.unread_count(principal.id)}


@router.post(
    "/{notification_id}/read",
    response_model=Notification,
    summary="Mark one notification read",
)
async def mark_read(notification_id: str, principal: CurrentUser) -> Notification:
    return await notification_service.mark_read(notification_id, principal.id)


@router.post(
    "/read-all", status_code=status.HTTP_200_OK, summary="Mark everything read"
)
async def mark_all_read(principal: CurrentUser) -> dict:
    return {"updated": await notification_service.mark_all_read(principal.id)}
