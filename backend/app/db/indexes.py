"""Index definitions, applied idempotently on application startup.

Every index exists to support a query the API actually issues; the comment on
each one names that query.
"""

from __future__ import annotations

import logging

from pymongo import ASCENDING, DESCENDING, TEXT, IndexModel
from pymongo.asynchronous.database import AsyncDatabase
from pymongo.errors import OperationFailure

from app.db.mongo import Collections
from app.models.enums import MasterDataRequestStatus

logger = logging.getLogger(__name__)

INDEX_PLAN: dict[str, list[IndexModel]] = {
    Collections.USERS: [
        # Login lookup, and a hard guarantee against duplicate accounts.
        IndexModel([("email", ASCENDING)], unique=True, name="uq_user_email"),
        IndexModel([("role", ASCENDING), ("status", ASCENDING)], name="ix_user_role"),
        IndexModel([("customer_id", ASCENDING)], sparse=True, name="ix_user_customer"),
    ],
    Collections.CUSTOMERS: [
        IndexModel([("code", ASCENDING)], unique=True, name="uq_customer_code"),
        IndexModel([("email", ASCENDING)], unique=True, name="uq_customer_email"),
        IndexModel(
            [("status", ASCENDING), ("tier", ASCENDING)], name="ix_customer_status"
        ),
        # Customer search box on the sales console.
        IndexModel(
            [("company_name", TEXT), ("contact_name", TEXT), ("code", TEXT)],
            name="tx_customer_search",
        ),
    ],
    Collections.PRODUCTS: [
        IndexModel([("sku", ASCENDING)], unique=True, name="uq_product_sku"),
        IndexModel(
            [("status", ASCENDING), ("category", ASCENDING)], name="ix_product_catalog"
        ),
        # Catalogue search box.
        IndexModel(
            [("name", TEXT), ("description", TEXT), ("sku", TEXT)],
            name="tx_product_search",
        ),
    ],
    Collections.QUOTATION_REQUESTS: [
        IndexModel([("request_number", ASCENDING)], unique=True, name="uq_request_no"),
        # "My requests" list for a customer, newest first.
        IndexModel(
            [("customer_id", ASCENDING), ("created_at", DESCENDING)],
            name="ix_request_customer",
        ),
        # Sales/manager queues filtered by status.
        IndexModel(
            [("status", ASCENDING), ("created_at", DESCENDING)],
            name="ix_request_status",
        ),
        IndexModel([("submitted_at", DESCENDING)], name="ix_request_submitted"),
    ],
    Collections.QUOTATIONS: [
        IndexModel(
            [("quotation_number", ASCENDING)], unique=True, name="uq_quotation_no"
        ),
        # Public verification endpoint.
        IndexModel(
            [("verification_code", ASCENDING)], unique=True, name="uq_verification_code"
        ),
        # Idempotency: a request may only ever have one quotation. The unique
        # index is the guarantee - two concurrent runs cannot both insert, and
        # the loser adopts the winner's document.
        IndexModel([("request_id", ASCENDING)], unique=True, name="uq_quotation_request"),
        IndexModel(
            [("customer_id", ASCENDING), ("issued_at", DESCENDING)],
            name="ix_quotation_customer",
        ),
        IndexModel(
            [("status", ASCENDING), ("valid_until", ASCENDING)],
            name="ix_quotation_validity",
        ),
    ],
    Collections.APPROVALS: [
        # Manager approval inbox.
        IndexModel(
            [("status", ASCENDING), ("created_at", DESCENDING)],
            name="ix_approval_queue",
        ),
        IndexModel([("request_id", ASCENDING)], name="ix_approval_request"),
        IndexModel([("decided_by", ASCENDING)], sparse=True, name="ix_approval_actor"),
    ],
    Collections.MASTER_DATA_REQUESTS: [
        # The manager's master-data queue, and an employee's own submissions.
        IndexModel(
            [("status", ASCENDING), ("created_at", DESCENDING)],
            name="ix_master_data_queue",
        ),
        IndexModel(
            [("requested_by", ASCENDING), ("created_at", DESCENDING)],
            name="ix_master_data_requester",
        ),
        IndexModel([("reference", ASCENDING)], unique=True, name="uq_master_data_ref"),
        # One open proposal per record. The partial filter scopes the constraint
        # to PENDING rows, so a rejected proposal does not block a corrected
        # resubmission while two colleagues still cannot queue the same customer
        # twice.
        IndexModel(
            [("entity_type", ASCENDING), ("dedupe_key", ASCENDING)],
            unique=True,
            name="uq_master_data_pending",
            partialFilterExpression={"status": MasterDataRequestStatus.PENDING.value},
        ),
    ],
    Collections.WORKFLOW_EXECUTIONS: [
        IndexModel(
            [("request_id", ASCENDING), ("started_at", DESCENDING)],
            name="ix_execution_request",
        ),
        IndexModel([("outcome", ASCENDING)], name="ix_execution_outcome"),
    ],
    Collections.AUDIT_LOGS: [
        IndexModel([("created_at", DESCENDING)], name="ix_audit_recent"),
        IndexModel(
            [("entity_type", ASCENDING), ("entity_id", ASCENDING)],
            name="ix_audit_entity",
        ),
        IndexModel([("actor_id", ASCENDING)], sparse=True, name="ix_audit_actor"),
        IndexModel([("action", ASCENDING)], name="ix_audit_action"),
    ],
    Collections.NOTIFICATIONS: [
        # Notification bell: unread first, newest first.
        IndexModel(
            [("user_id", ASCENDING), ("read", ASCENDING), ("created_at", DESCENDING)],
            name="ix_notification_inbox",
        ),
    ],
    Collections.COMPANY_SETTINGS: [
        IndexModel([("key", ASCENDING)], unique=True, name="uq_settings_key"),
    ],
}


async def ensure_indexes(database: AsyncDatabase) -> dict[str, list[str]]:
    """Create every planned index. Safe to call repeatedly."""
    created: dict[str, list[str]] = {}
    for collection_name, models in INDEX_PLAN.items():
        try:
            names = await database[collection_name].create_indexes(models)
        except OperationFailure as exc:
            # An index that already exists with different options should not stop
            # the application from booting; log it for the operator instead.
            logger.warning(
                "Index creation on %s reported: %s", collection_name, exc.details or exc
            )
            continue
        created[collection_name] = names
    logger.info("Ensured indexes on %d collections", len(created))
    return created
