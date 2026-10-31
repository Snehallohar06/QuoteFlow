"""Gap-free, human-readable document numbers.

Sequences live in the ``counters`` collection and are advanced with a single
atomic ``findAndModify``, so two concurrent submissions can never be handed the
same number. Counters are scoped per prefix and per year, giving numbers of the
form ``QR-2026-00001``.
"""

from __future__ import annotations

from datetime import UTC, datetime

from pymongo import ReturnDocument

from app.db.mongo import Collections, get_collection


async def next_sequence(scope: str) -> int:
    """Atomically increment and return the counter for ``scope``."""
    document = await get_collection(Collections.COUNTERS).find_one_and_update(
        {"_id": scope},
        {"$inc": {"value": 1}},
        upsert=True,
        return_document=ReturnDocument.AFTER,
    )
    return int(document["value"])


async def next_document_number(prefix: str, *, width: int = 5) -> str:
    """Produce the next number for ``prefix``, e.g. ``QR-2026-00042``."""
    year = datetime.now(UTC).year
    scope = f"{prefix}-{year}"
    sequence = await next_sequence(scope)
    return f"{prefix}-{year}-{sequence:0{width}d}"
