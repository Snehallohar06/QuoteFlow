"""Audit trail endpoints (read-only by design)."""

from fastapi import APIRouter, Query

from app.core.deps import ManagerUser, StaffUser
from app.models.audit import AuditLog
from app.models.common import Page
from app.models.enums import AuditAction
from app.services import audit_service

router = APIRouter(prefix="/audit-logs", tags=["Audit"])


@router.get("", response_model=Page[AuditLog], summary="Search the audit trail")
async def list_logs(
    _: ManagerUser,
    page: int = Query(1, ge=1),
    page_size: int = Query(25, ge=1, le=100),
    action: AuditAction | None = Query(None),
    entity_type: str | None = Query(None, max_length=40),
    entity_id: str | None = Query(None, max_length=40),
    actor_id: str | None = Query(None, max_length=40),
) -> Page[AuditLog]:
    """The trail is append-only; there is no endpoint that edits or deletes it."""
    return await audit_service.list_logs(
        page=page,
        page_size=page_size,
        action=action.value if action else None,
        entity_type=entity_type,
        entity_id=entity_id,
        actor_id=actor_id,
    )


@router.get(
    "/{entity_type}/{entity_id}",
    response_model=list[AuditLog],
    summary="Full history for one entity",
)
async def entity_trail(
    entity_type: str, entity_id: str, _: StaffUser
) -> list[AuditLog]:
    return await audit_service.get_entity_trail(entity_type, entity_id)
