"""Quotation integrity codes.

Each issued quotation carries a short ``verification_code`` printed on the PDF
and an ``integrity_hash`` computed over its financial content. Re-deriving the
hash from the stored document and comparing it to the recorded one detects any
later edit to the amounts, so a recipient can confirm a PDF against the system
of record.

The hash is an HMAC keyed with ``VERIFICATION_SECRET``: without the key a
tampered document cannot be given a matching hash.
"""

from __future__ import annotations

import hmac
import json
import secrets
from hashlib import sha256
from typing import Any

from app.core.config import settings
from app.utils.money import money, rate

#: Unambiguous alphabet - no O/0 or I/1, so codes survive being read aloud.
_CODE_ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"
_CODE_GROUPS = 3
_CODE_GROUP_LENGTH = 4


def generate_verification_code() -> str:
    """Return a code of the form ``A3KP-7WQX-R9MT``."""
    groups = [
        "".join(secrets.choice(_CODE_ALPHABET) for _ in range(_CODE_GROUP_LENGTH))
        for _ in range(_CODE_GROUPS)
    ]
    return "-".join(groups)


def _canonical_payload(
    *,
    quotation_number: str,
    request_number: str,
    customer_id: str,
    verification_code: str,
    items: list[dict],
    pricing: dict,
) -> str:
    """Build the exact string the hash is taken over.

    Only fields that must not change after issue are included, and they are
    serialised in a fixed order with fixed precision, so the same quotation
    always hashes identically regardless of dict ordering or driver round-trips.
    """
    canonical = {
        "quotation_number": quotation_number,
        "request_number": request_number,
        "customer_id": str(customer_id),
        "verification_code": verification_code,
        "items": [
            {
                "sku": item.get("sku"),
                "quantity": int(item.get("quantity") or 0),
                "unit_price": str(money(item.get("unit_price"))),
                "discount_percent": str(rate(item.get("applied_discount_percent"))),
                "line_total": str(money(item.get("line_total"))),
            }
            for item in items
        ],
        "pricing": {
            "subtotal": str(money(pricing.get("subtotal"))),
            "total_discount": str(money(pricing.get("total_discount"))),
            "taxable_amount": str(money(pricing.get("taxable_amount"))),
            "total_tax": str(money(pricing.get("total_tax"))),
            "final_amount": str(money(pricing.get("final_amount"))),
            "currency": pricing.get("currency"),
        },
    }
    return json.dumps(canonical, sort_keys=True, separators=(",", ":"))


def compute_integrity_hash(
    *,
    quotation_number: str,
    request_number: str,
    customer_id: str,
    verification_code: str,
    items: list[dict],
    pricing: dict,
) -> str:
    payload = _canonical_payload(
        quotation_number=quotation_number,
        request_number=request_number,
        customer_id=customer_id,
        verification_code=verification_code,
        items=items,
        pricing=pricing,
    )
    return hmac.new(
        settings.verification_secret.encode("utf-8"),
        payload.encode("utf-8"),
        sha256,
    ).hexdigest()


def hash_for_document(document: dict[str, Any]) -> str:
    """Re-derive the hash from a stored quotation document."""
    return compute_integrity_hash(
        quotation_number=document["quotation_number"],
        request_number=document["request_number"],
        customer_id=document["customer_id"],
        verification_code=document["verification_code"],
        items=document.get("items") or [],
        pricing=document.get("pricing") or {},
    )


def verify_document(document: dict[str, Any]) -> bool:
    """True when the stored amounts still match the hash recorded at issue."""
    expected = document.get("integrity_hash") or ""
    return hmac.compare_digest(expected, hash_for_document(document))
