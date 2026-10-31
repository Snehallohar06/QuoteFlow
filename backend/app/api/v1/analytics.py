"""Analytics endpoints for the sales dashboard."""

from fastapi import APIRouter, Query

from app.core.deps import ManagerUser, StaffUser
from app.services import analytics_service

router = APIRouter(prefix="/analytics", tags=["Analytics"])

_DAYS = Query(30, ge=1, le=365, description="Size of the reporting window in days")


@router.get("/dashboard", summary="Everything the dashboard needs, in one call")
async def dashboard(_: ManagerUser, days: int = _DAYS) -> dict:
    return await analytics_service.dashboard(days=days)


@router.get("/overview", summary="Headline KPIs")
async def overview(_: StaffUser, days: int = _DAYS) -> dict:
    return await analytics_service.overview(days=days)


@router.get("/requests/trend", summary="Daily request counts by outcome")
async def request_trend(_: StaffUser, days: int = _DAYS) -> list[dict]:
    return await analytics_service.request_trend(days=days)


@router.get("/revenue/trend", summary="Monthly quoted value and discount")
async def revenue_trend(
    _: ManagerUser, days: int = Query(90, ge=30, le=730)
) -> list[dict]:
    return await analytics_service.revenue_trend(days=days)


@router.get("/products/top", summary="Most-quoted products by value")
async def top_products(
    _: StaffUser, days: int = _DAYS, limit: int = Query(10, ge=1, le=50)
) -> list[dict]:
    return await analytics_service.top_products(days=days, limit=limit)


@router.get("/customers/top", summary="Highest-value customers")
async def top_customers(
    _: ManagerUser, days: int = _DAYS, limit: int = Query(10, ge=1, le=50)
) -> list[dict]:
    return await analytics_service.top_customers(days=days, limit=limit)


@router.get("/exceptions", summary="Which rules are driving manual review")
async def exception_breakdown(_: ManagerUser, days: int = _DAYS) -> list[dict]:
    return await analytics_service.exception_breakdown(days=days)


@router.get("/approvals/performance", summary="Approval turnaround and SLA compliance")
async def approval_performance(_: ManagerUser, days: int = _DAYS) -> dict:
    return await analytics_service.approval_performance(days=days)


@router.get("/workflow/performance", summary="Automation rate and per-step timings")
async def workflow_performance(_: ManagerUser, days: int = _DAYS) -> dict:
    return await analytics_service.workflow_performance(days=days)
