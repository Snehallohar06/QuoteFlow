"""QuoteFlow application entry point."""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.v1.router import api_router
from app.core.config import settings
from app.core.exceptions import register_exception_handlers
from app.db.indexes import ensure_indexes
from app.db.mongo import close_mongo_connection, connect_to_mongo, ping

logging.basicConfig(
    level=logging.DEBUG if settings.debug else logging.INFO,
    format="%(asctime)s %(levelname)-8s %(name)s: %(message)s",
)
logger = logging.getLogger("quoteflow")

DESCRIPTION = """
**QuoteFlow** automates a company's sales quotation process end to end.

A customer submits a quotation request; the backend validates it, verifies stock,
calculates prices with `Decimal` arithmetic, applies the configured discount
policy, routes anything outside policy to a sales manager, and issues a verified
PDF quotation.

Every decision is made by explicit business rules held in `company_settings` and
recorded step by step in `workflow_executions`, so each outcome is reproducible
and explainable.

### Roles
| Role | Can do |
| --- | --- |
| `CUSTOMER` | Register, browse the catalogue, submit requests, track status, download quotations |
| `SALES_EMPLOYEE` | Manage customers and products, monitor the queue, reprocess failed requests |
| `SALES_MANAGER` | Everything above, plus approvals, analytics and the rule book |

### Authentication
Sign in at `POST /api/v1/auth/login` and send the returned token as
`Authorization: Bearer <access_token>`.
"""


@asynccontextmanager
async def lifespan(_: FastAPI):
    """Open the database, apply indexes and seed the rule book on startup."""
    database = await connect_to_mongo()
    await ensure_indexes(database)

    # Imported here so the module graph is fully loaded before first use.
    from app.services import quotation_service, settings_service

    await settings_service.initialise_settings()
    expired = await quotation_service.expire_due_quotations()
    if expired:
        logger.info("Marked %d quotation(s) as expired on startup", expired)

    logger.info("%s %s is ready", settings.app_name, settings.app_version)
    try:
        yield
    finally:
        await close_mongo_connection()


def create_app() -> FastAPI:
    app = FastAPI(
        title=f"{settings.app_name} API",
        version=settings.app_version,
        description=DESCRIPTION,
        lifespan=lifespan,
        docs_url="/docs",
        redoc_url="/redoc",
        openapi_url="/openapi.json",
        contact={"name": "QuoteFlow", "email": "sales@northwind-supplies.example"},
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    register_exception_handlers(app)
    app.include_router(api_router, prefix=settings.api_prefix)

    @app.get("/", tags=["Service"], summary="Service banner")
    async def root() -> dict:
        return {
            "name": settings.app_name,
            "version": settings.app_version,
            "description": "Automated Quotation Request and Approval Management System",
            "docs": "/docs",
            "api": settings.api_prefix,
        }

    @app.get("/health", tags=["Service"], summary="Liveness and database check")
    async def health() -> dict:
        database = await ping()
        return {
            "status": "ok" if database["connected"] else "degraded",
            "version": settings.app_version,
            "environment": settings.app_env,
            "database": database,
        }

    return app


app = create_app()
