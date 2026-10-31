"""Shared Pydantic plumbing: ObjectId handling, money fields, base models."""

from datetime import UTC, datetime
from decimal import Decimal
from typing import Annotated, Any, Generic, TypeVar

from bson import ObjectId
from bson.errors import InvalidId
from pydantic import (
    BaseModel,
    BeforeValidator,
    ConfigDict,
    PlainSerializer,
    WithJsonSchema,
)

from app.core.exceptions import ValidationError
from app.utils.money import money, rate

T = TypeVar("T")


def _validate_object_id(value: Any) -> str:
    """Accept an ObjectId or its hex string and normalise to a string."""
    if isinstance(value, ObjectId):
        return str(value)
    if isinstance(value, str):
        if ObjectId.is_valid(value):
            return value
        raise ValueError("Not a valid ObjectId.")
    raise ValueError("Not a valid ObjectId.")


#: An ObjectId exposed to API clients as a 24-character hex string.
PyObjectId = Annotated[
    str,
    BeforeValidator(_validate_object_id),
    WithJsonSchema({"type": "string", "example": "6710c0a1b2c3d4e5f6a7b8c9"}),
]


def _to_object_id(value: str | ObjectId) -> ObjectId:
    """Convert a path/query identifier into an ObjectId.

    Raises the domain validation error rather than a bare ValueError, so a
    malformed id in a URL is answered with 422 instead of surfacing as a 500.
    """
    if isinstance(value, ObjectId):
        return value
    # ObjectId(None) mints a brand-new id instead of failing, which would turn a
    # missing identifier into a silent query for a document that cannot exist.
    if value is None:
        raise ValidationError("An identifier is required.")
    try:
        return ObjectId(value)
    except (InvalidId, TypeError) as exc:
        raise ValidationError(
            f"{value!r} is not a valid identifier.",
            details={"expected": "a 24-character hexadecimal ObjectId"},
        ) from exc


#: Monetary amount. Validated/stored as Decimal, serialised as a JSON number so
#: charting libraries on the frontend receive plain numbers. All arithmetic
#: happens on the Decimal before serialisation, so no precision is lost in
#: calculations - only in display, at 2dp.
Money = Annotated[
    Decimal,
    BeforeValidator(money),
    PlainSerializer(lambda v: float(v), return_type=float, when_used="json"),
]

#: Percentage value with the same treatment as :data:`Money`.
Rate = Annotated[
    Decimal,
    BeforeValidator(rate),
    PlainSerializer(lambda v: float(v), return_type=float, when_used="json"),
]


def jsonable(value: Any) -> Any:
    """Recursively turn Decimals into floats inside a free-form structure."""
    if isinstance(value, Decimal):
        return float(value)
    if isinstance(value, dict):
        return {key: jsonable(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [jsonable(item) for item in value]
    return value


#: A schema-less dict (rule context, step output, audit diffs) whose Decimal
#: values serialise as JSON numbers. Without this they would come out as
#: strings, because an untyped ``dict`` field carries no money annotation for
#: Pydantic to act on - so the same amount would be a number in one field and a
#: string in another.
JsonDict = Annotated[
    dict,
    PlainSerializer(jsonable, return_type=dict, when_used="json"),
]


def utc_now() -> datetime:
    """Timezone-aware UTC timestamp, used for every stored date."""
    return datetime.now(UTC)


def ensure_utc(value: datetime | None) -> datetime | None:
    """MongoDB returns naive datetimes; re-attach UTC so comparisons are safe."""
    if value is None:
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


class AppModel(BaseModel):
    """Base for all API schemas.

    ``validate_default`` is on so that a field declared as ``Money`` with a
    readable literal default (``Field(default="0.00")``) is run through the
    money validator and becomes a real ``Decimal``, rather than staying a string
    that only fails later at serialisation time.
    """

    model_config = ConfigDict(
        populate_by_name=True,
        from_attributes=True,
        str_strip_whitespace=True,
        use_enum_values=True,
        validate_default=True,
    )


class DocumentModel(AppModel):
    """Base for models that mirror a MongoDB document."""

    model_config = ConfigDict(
        populate_by_name=True,
        from_attributes=True,
        str_strip_whitespace=True,
        use_enum_values=True,
        arbitrary_types_allowed=True,
        validate_default=True,
    )

    id: PyObjectId | None = None

    @classmethod
    def from_mongo(cls, document: dict[str, Any] | None):
        """Build the model from a raw MongoDB document."""
        if document is None:
            return None
        data = dict(document)
        if "_id" in data:
            data["id"] = data.pop("_id")
        return cls.model_validate(data)


class PageMeta(AppModel):
    total: int
    page: int
    page_size: int
    total_pages: int


class Page(AppModel, Generic[T]):
    """Envelope for paginated list endpoints."""

    items: list[T]
    meta: PageMeta


def build_page(items: list[T], total: int, page: int, page_size: int) -> Page[T]:
    total_pages = (total + page_size - 1) // page_size if page_size else 0
    return Page(
        items=items,
        meta=PageMeta(
            total=total,
            page=page,
            page_size=page_size,
            total_pages=total_pages,
        ),
    )


object_id = _to_object_id
