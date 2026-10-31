"""`audit_logs` collection - append-only record of every state change.

There is deliberately no update or delete path for audit entries anywhere in the
API; the collection is written once and read thereafter.
"""

from datetime import datetime

from pydantic import Field

from app.models.common import DocumentModel, JsonDict, PyObjectId, utc_now
from app.models.enums import AuditAction


class AuditLog(DocumentModel):
    action: AuditAction
    entity_type: str
    entity_id: str | None = None
    summary: str

    actor_id: PyObjectId | None = None
    actor_email: str | None = None
    actor_role: str | None = None

    #: Field-level diff: {"field": {"before": ..., "after": ...}}.
    changes: JsonDict = Field(default_factory=dict)
    #: Any extra facts worth keeping with the event.
    metadata: JsonDict = Field(default_factory=dict)

    ip_address: str | None = None
    user_agent: str | None = None
    created_at: datetime = Field(default_factory=utc_now)
