"""Analytics aggregations for the manager dashboard.

All figures come from MongoDB aggregation pipelines rather than from documents
loaded into Python, so the dashboard stays responsive as volumes grow.

Note on the async driver: ``AsyncCollection.aggregate()`` is itself awaitable and
returns the cursor, so each pipeline runs in two steps - see :func:`_run`.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from functools import wraps
from typing import Any

from app.db.mongo import Collections, get_collection
from app.models.common import jsonable, utc_now
from app.models.enums import (
    ApprovalStatus,
    QuotationStatus,
    RequestStatus,
    StepStatus,
    WorkflowOutcome,
)
from app.utils.money import ZERO, money, rate, to_decimal

#: Statuses counted as "open pipeline" on the dashboard.
_OPEN_STATUSES = [
    RequestStatus.SUBMITTED.value,
    RequestStatus.UNDER_VALIDATION.value,
    RequestStatus.PRICED.value,
    RequestStatus.PENDING_APPROVAL.value,
]

#: Statuses that count as a favourable outcome. A request that passed the
#: success gate ends as COMPLETED; APPROVED is the brief moment between the
#: approval and the verified document, so both belong here.
_APPROVED_STATUSES = [
    RequestStatus.APPROVED.value,
    RequestStatus.COMPLETED.value,
]

#: Requests parked for a human. Counted separately so they are not mistaken
#: for either a success or a rejection.
_ESCALATED_STATUSES = [RequestStatus.ESCALATED.value]


def _window(days: int) -> datetime:
    return utc_now() - timedelta(days=days)


def _json_ready(func):
    """Return Decimals as JSON numbers.

    These endpoints hand back schema-less dicts, so there is no Pydantic model
    to carry the money serialiser. Converting here keeps analytics figures
    numeric and consistent with the rest of the API, instead of arriving as
    strings that a charting library would silently mis-plot.
    """

    @wraps(func)
    async def wrapper(*args, **kwargs):
        return jsonable(await func(*args, **kwargs))

    return wrapper


async def _run(
    collection, pipeline: list[dict], length: int | None = None
) -> list[dict]:
    """Execute an aggregation pipeline and materialise the rows."""
    cursor = await collection.aggregate(pipeline)
    return await cursor.to_list(length=length)


def _count_if(field: str, value: str) -> dict:
    """``$sum`` of 1 for each document where ``field`` equals ``value``."""
    return {"$sum": {"$cond": [{"$eq": [field, value]}, 1, 0]}}


@_json_ready
async def overview(*, days: int = 30) -> dict[str, Any]:
    """Headline KPIs for the period, plus live queue depths."""
    since = _window(days)
    now = utc_now()
    requests = get_collection(Collections.QUOTATION_REQUESTS)
    quotations = get_collection(Collections.QUOTATIONS)
    approvals = get_collection(Collections.APPROVALS)

    status_rows = await _run(
        requests,
        [
            {"$match": {"created_at": {"$gte": since}}},
            {"$group": {"_id": "$status", "count": {"$sum": 1}}},
        ],
    )
    by_status = {row["_id"]: row["count"] for row in status_rows}
    total_requests = sum(by_status.values())

    quotation_rows = await _run(
        quotations,
        [
            {"$match": {"issued_at": {"$gte": since}}},
            {
                "$group": {
                    "_id": None,
                    "count": {"$sum": 1},
                    "value": {"$sum": "$pricing.final_amount"},
                    "discount": {"$sum": "$pricing.total_discount"},
                    "auto": {
                        "$sum": {"$cond": [{"$eq": ["$auto_approved", True]}, 1, 0]}
                    },
                }
            },
        ],
        length=1,
    )
    stats = quotation_rows[0] if quotation_rows else {}

    quoted_value = money(to_decimal(stats.get("value")))
    discount_given = money(to_decimal(stats.get("discount")))
    quotation_count = stats.get("count", 0)
    auto_count = stats.get("auto", 0)

    approved = sum(by_status.get(status, 0) for status in _APPROVED_STATUSES)
    completed = by_status.get(RequestStatus.COMPLETED.value, 0)
    rejected = by_status.get(RequestStatus.REJECTED.value, 0)
    escalated = sum(by_status.get(status, 0) for status in _ESCALATED_STATUSES)
    decided = approved + rejected
    open_requests = sum(by_status.get(status, 0) for status in _OPEN_STATUSES)

    pending_approvals = await approvals.count_documents(
        {"status": ApprovalStatus.PENDING.value}
    )
    overdue_approvals = await approvals.count_documents(
        {"status": ApprovalStatus.PENDING.value, "sla_due_at": {"$lt": now}}
    )
    live_quotations = await quotations.count_documents(
        {"status": QuotationStatus.ISSUED.value, "valid_until": {"$gte": now}}
    )

    # Gross value before discount: the denominator for the discount rate.
    gross_value = quoted_value + discount_given

    return {
        "period_days": days,
        "since": since,
        "total_requests": total_requests,
        "requests_by_status": by_status,
        "open_requests": open_requests,
        "approved_requests": approved,
        "completed_requests": completed,
        "rejected_requests": rejected,
        "escalated_requests": escalated,
        "approval_rate_percent": rate(approved / decided * 100) if decided else ZERO,
        "quotations_issued": quotation_count,
        "quoted_value": quoted_value,
        "average_quotation_value": (
            money(quoted_value / quotation_count) if quotation_count else ZERO
        ),
        "total_discount_given": discount_given,
        "discount_rate_percent": (
            rate(discount_given / gross_value * 100) if gross_value > ZERO else ZERO
        ),
        "auto_approved_quotations": auto_count,
        "automation_rate_percent": (
            rate(auto_count / quotation_count * 100) if quotation_count else ZERO
        ),
        "pending_approvals": pending_approvals,
        "overdue_approvals": overdue_approvals,
        "live_quotations": live_quotations,
    }


@_json_ready
async def request_trend(*, days: int = 30) -> list[dict[str, Any]]:
    """Daily request counts split by outcome, for the dashboard line chart."""
    rows = await _run(
        get_collection(Collections.QUOTATION_REQUESTS),
        [
            {"$match": {"created_at": {"$gte": _window(days)}}},
            {
                "$group": {
                    "_id": {
                        "$dateToString": {"format": "%Y-%m-%d", "date": "$created_at"}
                    },
                    "total": {"$sum": 1},
                    "approved": {
                        "$sum": {
                            "$cond": [
                                {"$in": ["$status", _APPROVED_STATUSES]}, 1, 0
                            ]
                        }
                    },
                    "rejected": _count_if("$status", RequestStatus.REJECTED.value),
                    "escalated": _count_if("$status", RequestStatus.ESCALATED.value),
                    "pending": _count_if(
                        "$status", RequestStatus.PENDING_APPROVAL.value
                    ),
                    "failed": _count_if(
                        "$status", RequestStatus.VALIDATION_FAILED.value
                    ),
                }
            },
            {"$sort": {"_id": 1}},
        ],
    )
    return [
        {
            "date": row["_id"],
            "total": row["total"],
            "approved": row["approved"],
            "rejected": row["rejected"],
            "escalated": row.get("escalated", 0),
            "pending": row["pending"],
            "failed": row["failed"],
        }
        for row in rows
    ]


@_json_ready
async def revenue_trend(*, days: int = 90) -> list[dict[str, Any]]:
    """Monthly quoted value and discount, for the bar chart."""
    rows = await _run(
        get_collection(Collections.QUOTATIONS),
        [
            {"$match": {"issued_at": {"$gte": _window(days)}}},
            {
                "$group": {
                    "_id": {"$dateToString": {"format": "%Y-%m", "date": "$issued_at"}},
                    "quotations": {"$sum": 1},
                    "quoted_value": {"$sum": "$pricing.final_amount"},
                    "discount": {"$sum": "$pricing.total_discount"},
                }
            },
            {"$sort": {"_id": 1}},
        ],
    )
    return [
        {
            "month": row["_id"],
            "quotations": row["quotations"],
            "quoted_value": money(to_decimal(row["quoted_value"])),
            "discount": money(to_decimal(row["discount"])),
        }
        for row in rows
    ]


@_json_ready
async def top_products(*, days: int = 30, limit: int = 10) -> list[dict[str, Any]]:
    """Most-quoted products by value."""
    rows = await _run(
        get_collection(Collections.QUOTATIONS),
        [
            {"$match": {"issued_at": {"$gte": _window(days)}}},
            {"$unwind": "$items"},
            {
                "$group": {
                    "_id": "$items.sku",
                    "name": {"$first": "$items.name"},
                    "quantity": {"$sum": "$items.quantity"},
                    "value": {"$sum": "$items.line_total"},
                    "quotations": {"$sum": 1},
                }
            },
            {"$sort": {"value": -1}},
            {"$limit": limit},
        ],
        length=limit,
    )
    return [
        {
            "sku": row["_id"],
            "name": row["name"],
            "quantity": row["quantity"],
            "value": money(to_decimal(row["value"])),
            "quotations": row["quotations"],
        }
        for row in rows
    ]


@_json_ready
async def top_customers(*, days: int = 30, limit: int = 10) -> list[dict[str, Any]]:
    """Highest-value customers by quoted amount."""
    rows = await _run(
        get_collection(Collections.QUOTATIONS),
        [
            {"$match": {"issued_at": {"$gte": _window(days)}}},
            {
                "$group": {
                    "_id": "$customer_id",
                    "customer_name": {"$first": "$buyer.name"},
                    "quotations": {"$sum": 1},
                    "value": {"$sum": "$pricing.final_amount"},
                    "discount": {"$sum": "$pricing.total_discount"},
                }
            },
            {"$sort": {"value": -1}},
            {"$limit": limit},
        ],
        length=limit,
    )
    return [
        {
            "customer_id": row["_id"],
            "customer_name": row["customer_name"],
            "quotations": row["quotations"],
            "value": money(to_decimal(row["value"])),
            "discount": money(to_decimal(row["discount"])),
        }
        for row in rows
    ]


@_json_ready
async def exception_breakdown(*, days: int = 30) -> list[dict[str, Any]]:
    """Which rules are sending work to the manager, and how often."""
    rows = await _run(
        get_collection(Collections.QUOTATION_REQUESTS),
        [
            {
                "$match": {
                    "created_at": {"$gte": _window(days)},
                    "exceptions": {"$ne": []},
                }
            },
            {"$unwind": "$exceptions"},
            {"$group": {"_id": "$exceptions.type", "count": {"$sum": 1}}},
            {"$sort": {"count": -1}},
        ],
    )
    total = sum(row["count"] for row in rows)
    return [
        {
            "type": row["_id"],
            "count": row["count"],
            "share_percent": rate(row["count"] / total * 100) if total else ZERO,
        }
        for row in rows
    ]


@_json_ready
async def approval_performance(*, days: int = 30) -> dict[str, Any]:
    """Turnaround time and SLA compliance for resolved approvals."""
    rows = await _run(
        get_collection(Collections.APPROVALS),
        [
            {
                "$match": {
                    "created_at": {"$gte": _window(days)},
                    "decided_at": {"$ne": None},
                }
            },
            {
                "$project": {
                    "status": 1,
                    "turnaround_ms": {"$subtract": ["$decided_at", "$created_at"]},
                    "within_sla": {
                        "$cond": [{"$lte": ["$decided_at", "$sla_due_at"]}, 1, 0]
                    },
                }
            },
            {
                "$group": {
                    "_id": None,
                    "decided": {"$sum": 1},
                    "avg_turnaround_ms": {"$avg": "$turnaround_ms"},
                    "max_turnaround_ms": {"$max": "$turnaround_ms"},
                    "within_sla": {"$sum": "$within_sla"},
                    "approved": _count_if("$status", ApprovalStatus.APPROVED.value),
                    "rejected": _count_if("$status", ApprovalStatus.REJECTED.value),
                }
            },
        ],
        length=1,
    )

    if not rows:
        return {
            "decided": 0,
            "approved": 0,
            "rejected": 0,
            "average_turnaround_hours": ZERO,
            "longest_turnaround_hours": ZERO,
            "within_sla": 0,
            "sla_compliance_percent": ZERO,
        }

    row = rows[0]
    decided = row["decided"]
    return {
        "decided": decided,
        "approved": row["approved"],
        "rejected": row["rejected"],
        "average_turnaround_hours": rate(
            to_decimal(row["avg_turnaround_ms"] or 0) / 3_600_000
        ),
        "longest_turnaround_hours": rate(
            to_decimal(row["max_turnaround_ms"] or 0) / 3_600_000
        ),
        "within_sla": row["within_sla"],
        "sla_compliance_percent": (
            rate(row["within_sla"] / decided * 100) if decided else ZERO
        ),
    }


@_json_ready
async def workflow_performance(*, days: int = 30) -> dict[str, Any]:
    """How the automation itself is performing: outcomes and step timings."""
    since = _window(days)
    collection = get_collection(Collections.WORKFLOW_EXECUTIONS)

    outcome_rows = await _run(
        collection,
        [
            {"$match": {"started_at": {"$gte": since}}},
            {
                "$group": {
                    "_id": "$outcome",
                    "count": {"$sum": 1},
                    "avg_duration_ms": {"$avg": "$duration_ms"},
                }
            },
        ],
    )

    step_rows = await _run(
        collection,
        [
            {"$match": {"started_at": {"$gte": since}}},
            {"$unwind": "$steps"},
            {
                "$group": {
                    "_id": "$steps.step",
                    "executions": {"$sum": 1},
                    "avg_duration_ms": {"$avg": "$steps.duration_ms"},
                    "failures": _count_if("$steps.status", StepStatus.FAILED.value),
                }
            },
            {"$sort": {"_id": 1}},
        ],
    )

    total = sum(row["count"] for row in outcome_rows)
    by_outcome = {row["_id"]: row["count"] for row in outcome_rows}
    auto = by_outcome.get(WorkflowOutcome.AUTO_APPROVED.value, 0)

    # Weighted mean of the per-outcome averages.
    average_duration_ms = (
        int(
            sum((row["avg_duration_ms"] or 0) * row["count"] for row in outcome_rows)
            / total
        )
        if total
        else 0
    )

    return {
        "total_executions": total,
        "by_outcome": by_outcome,
        "straight_through_percent": rate(auto / total * 100) if total else ZERO,
        "average_duration_ms": average_duration_ms,
        "steps": [
            {
                "step": row["_id"],
                "executions": row["executions"],
                "average_duration_ms": round(row["avg_duration_ms"] or 0, 2),
                "failures": row["failures"],
            }
            for row in step_rows
        ],
    }


@_json_ready
async def dashboard(*, days: int = 30) -> dict[str, Any]:
    """One call that fills the whole manager dashboard."""
    return {
        "overview": await overview(days=days),
        "request_trend": await request_trend(days=days),
        "revenue_trend": await revenue_trend(days=max(days, 90)),
        "top_products": await top_products(days=days),
        "top_customers": await top_customers(days=days),
        "exception_breakdown": await exception_breakdown(days=days),
        "approval_performance": await approval_performance(days=days),
        "workflow_performance": await workflow_performance(days=days),
    }
