"""Product catalogue management."""

from __future__ import annotations

from typing import Any

from pymongo import ReturnDocument
from pymongo.errors import DuplicateKeyError

from app.core.exceptions import BusinessRuleError, ConflictError, NotFoundError
from app.db.mongo import Collections, get_collection
from app.models.common import build_page, object_id, utc_now
from app.models.enums import AuditAction, CustomerTier, ProductStatus
from app.models.product import Product
from app.schemas.product import (
    CatalogueProductResponse,
    ProductCreateRequest,
    ProductResponse,
    ProductUpdateRequest,
)
from app.services import audit_service, settings_service
from app.services.discount_engine import resolve_ceiling
from app.utils.money import decode_decimals, encode_decimals


def to_response(product: Product) -> ProductResponse:
    data = product.model_dump()
    data["available_quantity"] = product.available_quantity
    return ProductResponse.model_validate(data)


async def get_product(product_id: str) -> Product:
    raw = await get_collection(Collections.PRODUCTS).find_one(
        {"_id": object_id(product_id)}
    )
    if raw is None:
        raise NotFoundError("Product not found.")
    return Product.from_mongo(decode_decimals(raw))


async def get_products_by_ids(product_ids: list[str]) -> dict[str, Product]:
    """Batch fetch keyed by id string - avoids an N+1 read when pricing a request."""
    if not product_ids:
        return {}
    unique = {str(pid) for pid in product_ids}
    cursor = get_collection(Collections.PRODUCTS).find(
        {"_id": {"$in": [object_id(pid) for pid in unique]}}
    )
    documents = await cursor.to_list(length=len(unique))
    products = [Product.from_mongo(decode_decimals(doc)) for doc in documents]
    return {str(product.id): product for product in products}


def _build_query(
    search: str | None,
    category: str | None,
    status: str | None,
    in_stock_only: bool,
) -> dict[str, Any]:
    query: dict[str, Any] = {}
    if status:
        query["status"] = status
    if category:
        query["category"] = category
    if search:
        pattern = {"$regex": search.strip(), "$options": "i"}
        query["$or"] = [
            {"name": pattern},
            {"sku": pattern},
            {"description": pattern},
            {"category": pattern},
        ]
    if in_stock_only:
        query["stock_quantity"] = {"$gt": 0}
    return query


async def list_products(
    *,
    page: int = 1,
    page_size: int = 20,
    search: str | None = None,
    category: str | None = None,
    status: str | None = None,
    in_stock_only: bool = False,
):
    query = _build_query(search, category, status, in_stock_only)
    collection = get_collection(Collections.PRODUCTS)
    total = await collection.count_documents(query)
    cursor = (
        collection.find(query)
        .sort("name", 1)
        .skip((page - 1) * page_size)
        .limit(page_size)
    )
    documents = await cursor.to_list(length=page_size)
    items = [to_response(Product.from_mongo(decode_decimals(doc))) for doc in documents]
    return build_page(items, total, page, page_size)


async def list_catalogue(
    *,
    customer_tier: str = CustomerTier.STANDARD.value,
    page: int = 1,
    page_size: int = 20,
    search: str | None = None,
    category: str | None = None,
    in_stock_only: bool = False,
):
    """Customer-facing catalogue.

    Cost price is excluded, and each row carries the discount the viewer could
    ask for at a quantity of one - so the UI can set expectations before a
    request is submitted rather than after it is rejected.
    """
    query = _build_query(search, category, ProductStatus.ACTIVE.value, in_stock_only)
    settings_doc = await settings_service.get_settings_document()
    policy = settings_doc.discount_policy

    collection = get_collection(Collections.PRODUCTS)
    total = await collection.count_documents(query)
    cursor = (
        collection.find(query)
        .sort("name", 1)
        .skip((page - 1) * page_size)
        .limit(page_size)
    )
    documents = await cursor.to_list(length=page_size)

    items: list[CatalogueProductResponse] = []
    for doc in documents:
        product = Product.from_mongo(decode_decimals(doc))
        ceiling, _, _, _ = resolve_ceiling(
            quantity=1,
            customer_tier=customer_tier,
            policy=policy,
            product_max_percent=product.max_discount_percent,
        )
        data = product.model_dump()
        data["available_quantity"] = product.available_quantity
        data["indicative_max_discount_percent"] = ceiling
        data["low_stock"] = (
            product.reorder_level > 0
            and product.available_quantity <= product.reorder_level
        )
        items.append(CatalogueProductResponse.model_validate(data))

    return build_page(items, total, page, page_size)


async def list_categories() -> list[dict[str, Any]]:
    """Category facets for the catalogue filter."""
    cursor = await get_collection(Collections.PRODUCTS).aggregate(
        [
            {"$match": {"status": ProductStatus.ACTIVE.value}},
            {"$group": {"_id": "$category", "count": {"$sum": 1}}},
            {"$sort": {"_id": 1}},
        ]
    )
    rows = await cursor.to_list(length=None)
    return [{"category": row["_id"], "product_count": row["count"]} for row in rows]


async def create_product(
    payload: ProductCreateRequest,
    *,
    actor: dict[str, Any],
    request_context: dict[str, Any] | None = None,
) -> ProductResponse:
    if payload.reserved_quantity > payload.stock_quantity:
        raise BusinessRuleError(
            "The reserved quantity cannot exceed the quantity in stock."
        )

    product = Product.model_validate(payload.model_dump())
    product.sku = product.sku.strip().upper()
    try:
        result = await get_collection(Collections.PRODUCTS).insert_one(
            encode_decimals(product.model_dump(exclude={"id"}))
        )
    except DuplicateKeyError as exc:
        raise ConflictError(f"A product with SKU {product.sku} already exists.") from exc

    product.id = str(result.inserted_id)
    await audit_service.record(
        action=AuditAction.PRODUCT_CREATED,
        entity_type="product",
        entity_id=product.id,
        summary=f"Product {product.sku} ({product.name}) added to the catalogue.",
        actor=actor,
        **(request_context or {}),
    )
    return to_response(product)


async def update_product(
    product_id: str,
    payload: ProductUpdateRequest,
    *,
    actor: dict[str, Any],
    request_context: dict[str, Any] | None = None,
) -> ProductResponse:
    existing = await get_product(product_id)
    updates = payload.model_dump(exclude_unset=True, exclude_none=True)
    if not updates:
        return to_response(existing)

    stock = updates.get("stock_quantity", existing.stock_quantity)
    reserved = updates.get("reserved_quantity", existing.reserved_quantity)
    if reserved > stock:
        raise BusinessRuleError(
            "The reserved quantity cannot exceed the quantity in stock."
        )

    updates["updated_at"] = utc_now()
    raw = await get_collection(Collections.PRODUCTS).find_one_and_update(
        {"_id": object_id(product_id)},
        {"$set": encode_decimals(updates)},
        return_document=ReturnDocument.AFTER,
    )
    updated = Product.from_mongo(decode_decimals(raw))

    await audit_service.record(
        action=AuditAction.PRODUCT_UPDATED,
        entity_type="product",
        entity_id=product_id,
        summary=f"Product {existing.sku} updated.",
        actor=actor,
        changes=audit_service.diff(
            existing.model_dump(mode="json"),
            updated.model_dump(mode="json"),
            list(payload.model_dump(exclude_unset=True, exclude_none=True)),
        ),
        **(request_context or {}),
    )
    return to_response(updated)


async def discontinue_product(
    product_id: str,
    *,
    actor: dict[str, Any],
    request_context: dict[str, Any] | None = None,
) -> ProductResponse:
    """Soft delete.

    Products are never removed: historical quotations reference them, and an
    audit trail that points at a missing document is not an audit trail.
    """
    existing = await get_product(product_id)
    raw = await get_collection(Collections.PRODUCTS).find_one_and_update(
        {"_id": object_id(product_id)},
        {
            "$set": {
                "status": ProductStatus.DISCONTINUED.value,
                "updated_at": utc_now(),
            }
        },
        return_document=ReturnDocument.AFTER,
    )
    await audit_service.record(
        action=AuditAction.PRODUCT_DELETED,
        entity_type="product",
        entity_id=product_id,
        summary=f"Product {existing.sku} discontinued.",
        actor=actor,
        changes={"status": {"before": existing.status, "after": ProductStatus.DISCONTINUED.value}},
        **(request_context or {}),
    )
    return to_response(Product.from_mongo(decode_decimals(raw)))


async def adjust_stock(
    product_id: str,
    delta: int,
    *,
    actor: dict[str, Any],
    reason: str | None = None,
    request_context: dict[str, Any] | None = None,
) -> ProductResponse:
    """Apply a relative stock movement, refusing to go negative."""
    existing = await get_product(product_id)
    new_quantity = existing.stock_quantity + delta
    if new_quantity < 0:
        raise BusinessRuleError(
            f"Stock for {existing.sku} cannot fall below zero "
            f"(currently {existing.stock_quantity}, requested change {delta})."
        )
    if new_quantity < existing.reserved_quantity:
        raise BusinessRuleError(
            f"Stock for {existing.sku} cannot fall below the reserved quantity of "
            f"{existing.reserved_quantity}."
        )

    raw = await get_collection(Collections.PRODUCTS).find_one_and_update(
        {"_id": object_id(product_id)},
        {"$set": {"stock_quantity": new_quantity, "updated_at": utc_now()}},
        return_document=ReturnDocument.AFTER,
    )
    await audit_service.record(
        action=AuditAction.PRODUCT_UPDATED,
        entity_type="product",
        entity_id=product_id,
        summary=f"Stock for {existing.sku} adjusted by {delta:+d}.",
        actor=actor,
        changes={
            "stock_quantity": {
                "before": existing.stock_quantity,
                "after": new_quantity,
            }
        },
        metadata={"reason": reason} if reason else {},
        **(request_context or {}),
    )
    return to_response(Product.from_mongo(decode_decimals(raw)))
