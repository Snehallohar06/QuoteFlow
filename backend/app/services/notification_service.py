"""In-app notifications raised by the workflow and approval services.

Like audit logging, delivery is best-effort: a notification failure never breaks
the operation that triggered it.
"""

from __future__ import annotations

import logging
from typing import Any

from bson import ObjectId
from pymongo import ReturnDocument
from pymongo.errors import PyMongoError

from app.core.exceptions import NotFoundError
from app.db.mongo import Collections, get_collection
from app.models.common import build_page, object_id, utc_now
from app.models.enums import NotificationType, UserRole, UserStatus
from app.models.notification import Notification

logger = logging.getLogger(__name__)


async def notify(
    *,
    user_id: str | ObjectId,
    notification_type: NotificationType,
    title: str,
    message: str,
    entity_type: str | None = None,
    entity_id: str | None = None,
) -> str | None:
    notification = Notification(
        user_id=str(user_id),
        type=notification_type,
        title=title,
        message=message,
        entity_type=entity_type,
        entity_id=entity_id,
        created_at=utc_now(),
    )
    try:
        result = await get_collection(Collections.NOTIFICATIONS).insert_one(
            notification.model_dump(exclude={"id"})
        )
    except (PyMongoError, RuntimeError):
        logger.exception("Failed to create a %s notification", notification_type)
        return None
    return str(result.inserted_id)


async def notify_role(
    *,
    role: UserRole,
    notification_type: NotificationType,
    title: str,
    message: str,
    entity_type: str | None = None,
    entity_id: str | None = None,
) -> int:
    """Fan a notification out to every active holder of a role.

    Used for the manager approval queue, where the task belongs to the role
    rather than to one named person.
    """
    cursor = get_collection(Collections.USERS).find(
        {"role": role.value, "status": UserStatus.ACTIVE.value}, {"_id": 1}
    )
    recipients = await cursor.to_list(length=200)
    delivered = 0
    for recipient in recipients:
        created = await notify(
            user_id=recipient["_id"],
            notification_type=notification_type,
            title=title,
            message=message,
            entity_type=entity_type,
            entity_id=entity_id,
        )
        if created:
            delivered += 1
    return delivered


async def list_for_user(
    user_id: str,
    *,
    page: int = 1,
    page_size: int = 20,
    unread_only: bool = False,
):
    query: dict[str, Any] = {"user_id": user_id}
    if unread_only:
        query["read"] = False

    collection = get_collection(Collections.NOTIFICATIONS)
    total = await collection.count_documents(query)
    cursor = (
        collection.find(query)
        .sort("created_at", -1)
        .skip((page - 1) * page_size)
        .limit(page_size)
    )
    documents = await cursor.to_list(length=page_size)
    items = [Notification.from_mongo(doc) for doc in documents]
    return build_page(items, total, page, page_size)


async def unread_count(user_id: str) -> int:
    return await get_collection(Collections.NOTIFICATIONS).count_documents(
        {"user_id": user_id, "read": False}
    )


async def mark_read(notification_id: str, user_id: str) -> Notification:
    """Mark one notification read. Scoped by user so nobody can touch another inbox."""
    result = await get_collection(Collections.NOTIFICATIONS).find_one_and_update(
        {"_id": object_id(notification_id), "user_id": user_id},
        {"$set": {"read": True, "read_at": utc_now()}},
        return_document=ReturnDocument.AFTER,
    )
    if result is None:
        raise NotFoundError("Notification not found.")
    return Notification.from_mongo(result)


async def mark_all_read(user_id: str) -> int:
    result = await get_collection(Collections.NOTIFICATIONS).update_many(
        {"user_id": user_id, "read": False},
        {"$set": {"read": True, "read_at": utc_now()}},
    )
    return result.modified_count
