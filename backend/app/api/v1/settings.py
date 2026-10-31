"""Company settings endpoints: the editable rule book."""

from typing import Any

from fastapi import APIRouter, Body

from app.core.deps import CurrentUser, ManagerUser, RequestContext
from app.models.common import jsonable
from app.models.company_settings import CompanySettings
from app.models.enums import AuditAction
from app.services import audit_service, settings_service

router = APIRouter(prefix="/settings", tags=["Company settings"])


@router.get("", response_model=CompanySettings, summary="Read the active rule book")
async def get_settings(_: CurrentUser) -> CompanySettings:
    """Readable by every role so the UI can show the limits that apply."""
    return await settings_service.get_settings_document()


@router.get("/discount-policy", summary="Discount tiers and ceilings")
async def get_discount_policy(_: CurrentUser) -> dict:
    """The tier table on its own, for the catalogue and request screens."""
    document = await settings_service.get_settings_document()
    policy = document.discount_policy
    # jsonable(): this is a schema-less dict, so the money serialiser on the
    # models does not apply and Decimals would otherwise come out as strings.
    return jsonable(
        {
            "tiers": [tier.model_dump() for tier in policy.tiers],
            "tier_bonus_percent": policy.tier_bonus_percent,
            "absolute_max_discount_percent": policy.absolute_max_discount_percent,
            "enforce_cost_floor": policy.enforce_cost_floor,
            "approval_policy": document.approval_policy.model_dump(),
            "tax_policy": document.tax_policy.model_dump(),
        }
    )


@router.patch("", response_model=CompanySettings, summary="Update the rule book")
async def update_settings(
    principal: ManagerUser,
    context: RequestContext,
    patch: dict[str, Any] = Body(
        ...,
        description=(
            "Partial update. Nested objects are merged field by field; lists "
            "such as the discount tier table are replaced wholesale."
        ),
        examples=[
            {
                "discount_policy": {
                    "tiers": [
                        {
                            "min_quantity": 1,
                            "max_quantity": 5,
                            "max_discount_percent": 3,
                            "label": "1-5 units",
                        },
                        {
                            "min_quantity": 6,
                            "max_quantity": None,
                            "max_discount_percent": 12,
                            "label": "6+ units",
                        },
                    ]
                },
                "approval_policy": {"order_value_threshold": 250000},
            }
        ],
    ),
) -> CompanySettings:
    """Re-tune the deployed workflow without a code change.

    The patch is validated against the settings model before it is written, so
    an invalid tier table is rejected rather than breaking the engines.
    """
    before = await settings_service.get_settings_document()
    updated = await settings_service.update_settings(patch, actor_id=principal.id)

    await audit_service.record(
        action=AuditAction.SETTINGS_UPDATED,
        entity_type="company_settings",
        entity_id=str(updated.id),
        summary=f"Company settings updated by {principal.full_name}.",
        actor=principal.as_actor(),
        changes=audit_service.diff(
            before.model_dump(mode="json"),
            updated.model_dump(mode="json"),
            list(patch.keys()),
        ),
        **context,
    )
    return updated
