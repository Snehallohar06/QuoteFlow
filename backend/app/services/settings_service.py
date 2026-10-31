"""Reads and writes the single `company_settings` document.

Every engine takes its thresholds from here, so this module is the one place the
deployed workflow's behaviour is configured.
"""

from __future__ import annotations

from typing import Any

from pydantic import ValidationError as PydanticValidationError

from app.core.exceptions import ValidationError
from app.db.mongo import Collections, get_collection
from app.models.common import utc_now
from app.models.company_settings import DEFAULT_SETTINGS_KEY, CompanySettings
from app.utils.money import decode_decimals, encode_decimals


async def get_settings_document() -> CompanySettings:
    """Return the active settings, creating the defaults on first access."""
    collection = get_collection(Collections.COMPANY_SETTINGS)
    raw = await collection.find_one({"key": DEFAULT_SETTINGS_KEY})
    if raw is None:
        return await initialise_settings()
    return CompanySettings.from_mongo(decode_decimals(raw))


async def initialise_settings() -> CompanySettings:
    """Insert the default rule book if it is not already present."""
    collection = get_collection(Collections.COMPANY_SETTINGS)
    defaults = CompanySettings()
    payload = defaults.model_dump(exclude={"id"})
    await collection.update_one(
        {"key": DEFAULT_SETTINGS_KEY},
        {"$setOnInsert": encode_decimals(payload)},
        upsert=True,
    )
    stored = await collection.find_one({"key": DEFAULT_SETTINGS_KEY})
    return CompanySettings.from_mongo(decode_decimals(stored))


def _flatten(prefix: str, value: Any) -> dict[str, Any]:
    """Turn a nested patch into dotted MongoDB ``$set`` paths.

    A partial update of ``{"tax_policy": {"rate_percent": 12}}`` must not wipe the
    other tax fields, so nested dicts become ``tax_policy.rate_percent``. Lists
    are replaced wholesale, which is the intent for things like discount tiers.
    """
    flat: dict[str, Any] = {}
    for key, item in value.items():
        path = f"{prefix}.{key}" if prefix else key
        if isinstance(item, dict) and item and not _is_rate_map(key):
            flat.update(_flatten(path, item))
        else:
            flat[path] = item
    return flat


def _is_rate_map(key: str) -> bool:
    """Maps keyed by data (not by schema) are replaced whole, not merged."""
    return key == "tier_bonus_percent"


async def update_settings(patch: dict[str, Any], *, actor_id: str | None) -> CompanySettings:
    """Apply a partial update and return the stored result.

    The patch is validated by merging it into the current document and
    re-running the Pydantic model, so an invalid tier table is rejected before it
    reaches the database.
    """
    current = await get_settings_document()
    merged = current.model_dump(exclude={"id"})
    _deep_merge(merged, patch)
    try:
        CompanySettings.model_validate(merged)
    except PydanticValidationError as exc:
        # Surface a 422 with the offending fields rather than a 500: an invalid
        # rule book is a client error, and nothing has been written yet.
        raise ValidationError(
            "The settings patch is not valid.",
            details=[
                {"field": ".".join(str(part) for part in error["loc"]),
                 "message": error["msg"]}
                for error in exc.errors()
            ],
        ) from exc

    updates = _flatten("", patch)
    updates["updated_at"] = utc_now()
    updates["updated_by"] = actor_id

    await get_collection(Collections.COMPANY_SETTINGS).update_one(
        {"key": DEFAULT_SETTINGS_KEY},
        {"$set": encode_decimals(updates)},
        upsert=True,
    )

    # Re-read so the response reflects exactly what is stored, including any
    # defaults the model filled in.
    return await get_settings_document()


def _deep_merge(target: dict, patch: dict) -> None:
    for key, value in patch.items():
        if isinstance(value, dict) and isinstance(target.get(key), dict):
            _deep_merge(target[key], value)
        else:
            target[key] = value
