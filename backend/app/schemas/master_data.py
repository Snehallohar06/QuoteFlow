"""Request/response schemas for master-data authorisation.

A sales employee proposes a customer or a product; a sales manager decides. The
proposal carries the *same* create payload the direct endpoint takes, wrapped
rather than re-declared, so the two routes can never drift apart in what they
accept.
"""

from datetime import datetime

from pydantic import Field

from app.models.common import AppModel, JsonDict, PyObjectId
from app.models.enums import MasterDataEntity, MasterDataRequestStatus
from app.schemas.customer import CustomerCreateRequest, CustomerResponse
from app.schemas.product import ProductCreateRequest, ProductResponse


class CustomerProposalRequest(AppModel):
    customer: CustomerCreateRequest
    reason: str | None = Field(
        default=None,
        max_length=500,
        description="Why this customer is needed; shown to the manager deciding.",
    )


class ProductProposalRequest(AppModel):
    product: ProductCreateRequest
    reason: str | None = Field(default=None, max_length=500)


class MasterDataDecisionRequest(AppModel):
    approve: bool = Field(description="True authorises the record; false refuses it.")
    comments: str | None = Field(
        default=None,
        max_length=1000,
        description="Required when refusing, so the employee is told why.",
    )


class MasterDataRequestResponse(AppModel):
    id: PyObjectId
    reference: str
    entity_type: MasterDataEntity
    status: MasterDataRequestStatus
    label: str
    payload: JsonDict
    reason: str | None = None

    requested_by: PyObjectId
    requested_by_name: str
    requested_by_email: str

    decided_by: PyObjectId | None = None
    decided_by_name: str | None = None
    decided_at: datetime | None = None
    decision_comments: str | None = None

    created_entity_id: PyObjectId | None = None
    created_entity_label: str | None = None

    created_at: datetime
    updated_at: datetime


class MasterDataDecisionResponse(AppModel):
    """The settled proposal, plus whatever it created."""

    request: MasterDataRequestResponse
    customer: CustomerResponse | None = None
    product: ProductResponse | None = None
