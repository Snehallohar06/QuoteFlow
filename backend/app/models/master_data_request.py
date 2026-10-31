"""``master_data_requests`` collection - an employee's proposal to add master data.

A sales employee may not create a customer or a product outright. They submit
the record here and a sales manager authorises it; only then is the customer or
product written to its own collection. The proposal keeps the submitted values
verbatim, so a rejected request still shows exactly what was asked for.
"""

from datetime import datetime

from pydantic import Field

from app.models.common import DocumentModel, JsonDict, PyObjectId, utc_now
from app.models.enums import MasterDataEntity, MasterDataRequestStatus


class MasterDataRequest(DocumentModel):
    reference: str
    entity_type: MasterDataEntity
    status: MasterDataRequestStatus = MasterDataRequestStatus.PENDING

    #: The create payload as submitted, validated against the same schema the
    #: direct endpoint uses. Stored rather than applied, and re-validated at
    #: approval time so a stale proposal cannot bypass the current rules.
    payload: JsonDict = Field(default_factory=dict)
    #: Human-readable identity of the proposed record, for queues and audit
    #: entries: a company name, or a SKU and product name.
    label: str
    #: The field two proposals would collide on - a customer's email address or
    #: a product's SKU, normalised. Backs the partial unique index that stops
    #: the same record being queued twice.
    dedupe_key: str
    #: Why the employee needs it, in their own words. Optional.
    reason: str | None = None

    requested_by: PyObjectId
    requested_by_name: str
    requested_by_email: str

    decided_by: PyObjectId | None = None
    decided_by_name: str | None = None
    decided_at: datetime | None = None
    decision_comments: str | None = None

    #: Set once approved: the record that was actually created.
    created_entity_id: PyObjectId | None = None
    created_entity_label: str | None = None

    created_at: datetime = Field(default_factory=utc_now)
    updated_at: datetime = Field(default_factory=utc_now)

    @property
    def is_open(self) -> bool:
        return self.status == MasterDataRequestStatus.PENDING
