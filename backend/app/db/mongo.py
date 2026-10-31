"""MongoDB connection management.

Uses PyMongo's native async client (``AsyncMongoClient``, PyMongo 4.13+), which
replaces the now end-of-life Motor driver. A single client is created on
application startup and shared across requests - the driver maintains its own
connection pool, so creating clients per request would be wasteful.
"""

from __future__ import annotations

import logging
from typing import Any

from pymongo import AsyncMongoClient
from pymongo.asynchronous.collection import AsyncCollection
from pymongo.asynchronous.database import AsyncDatabase
from pymongo.errors import PyMongoError

from app.core.config import settings

logger = logging.getLogger(__name__)


class Collections:
    """Canonical collection names, referenced instead of raw strings."""

    USERS = "users"
    CUSTOMERS = "customers"
    PRODUCTS = "products"
    QUOTATION_REQUESTS = "quotation_requests"
    QUOTATIONS = "quotations"
    APPROVALS = "approvals"
    MASTER_DATA_REQUESTS = "master_data_requests"
    WORKFLOW_EXECUTIONS = "workflow_executions"
    AUDIT_LOGS = "audit_logs"
    NOTIFICATIONS = "notifications"
    COMPANY_SETTINGS = "company_settings"
    COUNTERS = "counters"

    @classmethod
    def all(cls) -> list[str]:
        return [
            value
            for key, value in vars(cls).items()
            if key.isupper() and isinstance(value, str)
        ]


class Database:
    """Holds the process-wide client/database handles."""

    client: AsyncMongoClient | None = None
    database: AsyncDatabase | None = None


db_state = Database()


async def connect_to_mongo(
    uri: str | None = None, db_name: str | None = None
) -> AsyncDatabase:
    """Open the connection and verify it with a ping."""
    uri = uri or settings.mongodb_uri
    db_name = db_name or settings.mongodb_db_name

    client: AsyncMongoClient = AsyncMongoClient(
        uri,
        uuidRepresentation="standard",
        serverSelectionTimeoutMS=5000,
        tz_aware=True,
    )
    try:
        await client.admin.command("ping")
    except PyMongoError as exc:
        await client.close()
        raise RuntimeError(
            f"Could not reach MongoDB at {uri!r}. Is the server running?"
        ) from exc

    db_state.client = client
    db_state.database = client[db_name]
    logger.info("Connected to MongoDB database %r", db_name)
    return db_state.database


async def close_mongo_connection() -> None:
    if db_state.client is not None:
        await db_state.client.close()
        db_state.client = None
        db_state.database = None
        logger.info("Closed the MongoDB connection")


def get_database() -> AsyncDatabase:
    """Return the active database, failing loudly if startup did not run."""
    if db_state.database is None:
        raise RuntimeError(
            "The database is not initialised. connect_to_mongo() must run first."
        )
    return db_state.database


def get_collection(name: str) -> AsyncCollection:
    return get_database()[name]


async def ping() -> dict[str, Any]:
    """Health-check helper used by the /health endpoint."""
    try:
        await get_database().command("ping")
    except (PyMongoError, RuntimeError) as exc:
        return {"connected": False, "error": str(exc)}
    return {"connected": True, "database": settings.mongodb_db_name}
