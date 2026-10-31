"""Aggregates the v1 routers into one mountable router."""

from fastapi import APIRouter

from app.api.v1 import (
    analytics,
    approvals,
    audit,
    auth,
    customers,
    master_data,
    notifications,
    products,
    quotations,
    requests,
    settings,
)

api_router = APIRouter()

api_router.include_router(auth.router)
api_router.include_router(customers.router)
api_router.include_router(products.router)
api_router.include_router(requests.router)
api_router.include_router(approvals.router)
api_router.include_router(master_data.router)
api_router.include_router(quotations.router)
# Unauthenticated: anyone holding a printed quotation can check it.
api_router.include_router(quotations.public_router)
api_router.include_router(audit.router)
api_router.include_router(notifications.router)
api_router.include_router(analytics.router)
api_router.include_router(settings.router)
