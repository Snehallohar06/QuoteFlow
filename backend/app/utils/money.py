"""Decimal-based money helpers.

Every monetary value in QuoteFlow is a :class:`decimal.Decimal`, quantised to two
decimal places with ``ROUND_HALF_UP`` (the convention used for invoicing in most
jurisdictions). Floats are never used for arithmetic; MongoDB persistence goes
through :class:`bson.Decimal128`, which is a lossless decimal type.
"""

from decimal import ROUND_HALF_UP, Decimal
from typing import Any

from bson import Decimal128

MONEY_QUANT = Decimal("0.01")
RATE_QUANT = Decimal("0.01")
ZERO = Decimal("0.00")
HUNDRED = Decimal("100")


def to_decimal(value: Any) -> Decimal:
    """Coerce ints, strings, floats and Decimal128 into a Decimal."""
    if isinstance(value, Decimal):
        return value
    if isinstance(value, Decimal128):
        return value.to_decimal()
    if isinstance(value, float):
        # Route through str() so 0.1 does not pick up binary float noise.
        return Decimal(str(value))
    if value is None:
        return ZERO
    return Decimal(str(value))


def money(value: Any) -> Decimal:
    """Quantise a value to a 2dp monetary amount."""
    return to_decimal(value).quantize(MONEY_QUANT, rounding=ROUND_HALF_UP)


def rate(value: Any) -> Decimal:
    """Quantise a percentage / rate to 2dp."""
    return to_decimal(value).quantize(RATE_QUANT, rounding=ROUND_HALF_UP)


def percent_of(amount: Any, percentage: Any) -> Decimal:
    """Return ``percentage``% of ``amount`` as a 2dp monetary amount."""
    return money(to_decimal(amount) * to_decimal(percentage) / HUNDRED)


def to_bson(value: Any) -> Decimal128:
    """Convert a monetary Decimal into the BSON type used for storage."""
    return Decimal128(money(value))


def encode_decimals(payload: Any) -> Any:
    """Recursively convert Decimal values into Decimal128 for MongoDB writes.

    Service code can therefore build documents out of plain Decimals and convert
    once, at the persistence boundary.
    """
    if isinstance(payload, Decimal):
        return Decimal128(payload)
    if isinstance(payload, dict):
        return {key: encode_decimals(val) for key, val in payload.items()}
    if isinstance(payload, (list, tuple)):
        return [encode_decimals(item) for item in payload]
    return payload


def decode_decimals(payload: Any) -> Any:
    """Inverse of :func:`encode_decimals`, applied when reading documents."""
    if isinstance(payload, Decimal128):
        return payload.to_decimal()
    if isinstance(payload, dict):
        return {key: decode_decimals(val) for key, val in payload.items()}
    if isinstance(payload, list):
        return [decode_decimals(item) for item in payload]
    return payload
