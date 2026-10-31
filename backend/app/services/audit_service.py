"""Append-only audit logging.

Writes are fire-and-forget from the caller's point of view: a logging failure
must never fail the business operation that triggered it, so errors are swallowed
and reported to the application log instead.
"""

from __future__ import annotations

import logging
from typing import Any

from pymongo.errors import PyMongoError

from app.db.mongo import Collections, get_collection
from app.models.audit import AuditLog
from app.models.common import build_page, object_id, utc_now
from app.models.enums import AuditAction
from app.utils.money import decode_decimals, encode_decimals

logger = logging.getLogger(__name__)


async def record(
    *,
    action: AuditAction,
    entity_type: str,
    summary: str,
    entity_id: str | None = None,
    actor: dict[str, Any] | None = None,
    changes: dict | None = None,
    metadata: dict | None = None,
    ip_address: str | None = None,
    user_agent: str | None = None,
) -> str | None:
    """Append one audit entry. Returns its id, or ``None`` if logging failed."""
    entry = AuditLog(
        action=action,
        entity_type=entity_type,
        entity_id=entity_id,
        summary=summary,
        actor_id=(actor or {}).get("id"),
        actor_email=(actor or {}).get("email"),
        actor_role=(actor or {}).get("role"),
        changes=changes or {},
        metadata=metadata or {},
        ip_address=ip_address,
        user_agent=user_agent,
        created_at=utc_now(),
    )
    try:
        result = await get_collection(Collections.AUDIT_LOGS).insert_one(
            encode_decimals(entry.model_dump(exclude={"id"}))
        )
    except (PyMongoError, RuntimeError):
        logger.exception("Failed to write an audit entry for %s", action)
        return None
    return str(result.inserted_id)


def diff(before: dict | None, after: dict | None, fields: list[str] | None = None) -> dict:
    """Build a field-level ``{field: {before, after}}`` diff for an audit entry."""
    before = before or {}
    after = after or {}
    keys = fields if fields is not None else sorted(set(before) | set(after))
    changes: dict[str, dict] = {}
    for key in keys:
        old, new = before.get(key), after.get(key)
        if old != new:
            changes[key] = {"before": old, "after": new}
    return changes


async def list_logs(
    *,
    page: int = 1,
    page_size: int = 25,
    action: str | None = None,
    entity_type: str | None = None,
    entity_id: str | None = None,
    actor_id: str | None = None,
):
    """Paginated audit trail, newest first."""
    query: dict[str, Any] = {}
    if action:
        query["action"] = action
    if entity_type:
        query["entity_type"] = entity_type
    if entity_id:
        query["entity_id"] = entity_id
    if actor_id:
        query["actor_id"] = actor_id

    collection = get_collection(Collections.AUDIT_LOGS)
    total = await collection.count_documents(query)
    cursor = (
        collection.find(query)
        .sort("created_at", -1)
        .skip((page - 1) * page_size)
        .limit(page_size)
    )
    documents = await cursor.to_list(length=page_size)
    items = [AuditLog.from_mongo(decode_decimals(doc)) for doc in documents]
    return build_page(items, total, page, page_size)


async def get_entity_trail(entity_type: str, entity_id: str) -> list[AuditLog]:
    """Full chronological history for one entity, oldest first."""
    object_id(entity_id)  # reject malformed identifiers early
    cursor = (
        get_collection(Collections.AUDIT_LOGS)
        .find({"entity_type": entity_type, "entity_id": entity_id})
        .sort("created_at", 1)
    )
    documents = await cursor.to_list(length=500)
    return [AuditLog.from_mongo(decode_decimals(doc)) for doc in documents]
