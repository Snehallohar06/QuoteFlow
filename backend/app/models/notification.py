"""`notifications` collection - in-app messages raised by the workflow."""

from datetime import datetime

from pydantic import Field

from app.models.common import DocumentModel, PyObjectId, utc_now
from app.models.enums import NotificationChannel, NotificationType


class Notification(DocumentModel):
    user_id: PyObjectId
    type: NotificationType
    title: str
    message: str
    channel: NotificationChannel = NotificationChannel.IN_APP

    #: Deep-link target for the frontend, e.g. ("quotation_request", "<id>").
    entity_type: str | None = None
    entity_id: str | None = None

    read: bool = False
    read_at: datetime | None = None
    created_at: datetime = Field(default_factory=utc_now)
