"""Manager approval decisions and their consequences."""

import pytest
from bson import ObjectId

from app.db.mongo import Collections, get_collection
from app.models.enums import (
    ApprovalDecision,
    ApprovalStatus,
    ProductStatus,
    RequestStatus,
)
from tests.conftest import create_product

pytestmark = pytest.mark.workflow


async def raise_approval(client, customer_actor, *, discount=9, quantity=10, **product):
    """Submit a request that breaches the discount ceiling and needs review."""
    defaults = {"unit_price": "1000.00", "cost_price": "100.00", "stock_quantity": 500}
    product_id = await create_product(**{**defaults, **product})

    response = await client.post(
        "/api/v1/quotation-requests",
        headers=customer_actor.headers,
        json={
            "items": [
                {
                    "product_id": product_id,
                    "quantity": quantity,
                    "requested_discount_percent": discount,
                }
            ],
            "submit": True,
        },
    )
    assert response.status_code == 201, response.text
    workflow = response.json()["workflow"]
    assert workflow["approval_id"], workflow
    return workflow


# ---------------------------------------------------------------------------
# Queue
# ---------------------------------------------------------------------------


async def test_the_task_appears_in_the_queue(client, customer_actor, manager):
    workflow = await raise_approval(client, customer_actor)

    response = await client.get(
        "/api/v1/approvals", headers=manager.headers, params={"status": "PENDING"}
    )
    assert response.status_code == 200
    body = response.json()
    assert body["meta"]["total"] == 1
    assert body["items"][0]["request_number"] == workflow["request"]["request_number"]
    assert body["items"][0]["requested_discount_percent"] == 9.0

    count = await client.get("/api/v1/approvals/pending-count", headers=manager.headers)
    assert count.json()["pending"] == 1


async def test_the_decision_screen_bundles_the_full_context(
    client, customer_actor, manager
):
    workflow = await raise_approval(client, customer_actor)

    response = await client.get(
        f"/api/v1/approvals/{workflow['approval_id']}", headers=manager.headers
    )
    assert response.status_code == 200
    body = response.json()
    assert body["approval"]["status"] == ApprovalStatus.PENDING.value
    assert body["request"]["request_number"] == workflow["request"]["request_number"]
    assert body["customer"]["code"] == "CUST-TEST-1"
    assert body["latest_execution"]["outcome"] == "PENDING_APPROVAL"


async def test_an_employee_may_watch_but_not_decide(client, customer_actor, employee):
    workflow = await raise_approval(client, customer_actor)

    assert (
        await client.get("/api/v1/approvals", headers=employee.headers)
    ).status_code == 200

    response = await client.post(
        f"/api/v1/approvals/{workflow['approval_id']}/decision",
        headers=employee.headers,
        json={"decision": ApprovalDecision.APPROVE.value},
    )
    assert response.status_code == 403


async def test_a_customer_cannot_see_the_queue(client, customer_actor):
    response = await client.get("/api/v1/approvals", headers=customer_actor.headers)
    assert response.status_code == 403


# ---------------------------------------------------------------------------
# Approve
# ---------------------------------------------------------------------------


async def test_approval_issues_the_quotation(client, customer_actor, manager):
    workflow = await raise_approval(client, customer_actor)

    response = await client.post(
        f"/api/v1/approvals/{workflow['approval_id']}/decision",
        headers=manager.headers,
        json={"decision": ApprovalDecision.APPROVE.value, "comments": "Strategic account"},
    )
    assert response.status_code == 200, response.text
    body = response.json()

    assert body["approval"]["status"] == ApprovalStatus.APPROVED.value
    assert body["approval"]["decided_by_name"] == "Test Manager"
    assert body["approval"]["decided_at"] is not None
    # Approving runs the document and verification steps, so the request lands
    # on COMPLETED rather than stopping at APPROVED.
    assert body["request"]["status"] == RequestStatus.COMPLETED.value
    assert body["quotation_id"] is not None
    assert body["execution_id"] is not None

    quotation = await client.get(
        f"/api/v1/quotations/{body['quotation_id']}", headers=manager.headers
    )
    assert quotation.status_code == 200
    detail = quotation.json()
    # Manager-approved, so it is not marked as straight-through.
    assert detail["auto_approved"] is False
    assert detail["approved_by_name"] == "Test Manager"
    # The discount the customer asked for was granted as requested.
    assert detail["items"][0]["applied_discount_percent"] == 9.0
    assert detail["pricing"]["final_amount"] == 10738.0


async def test_approval_with_an_override_reprices_the_quotation(
    client, customer_actor, manager
):
    workflow = await raise_approval(client, customer_actor, discount=9)

    response = await client.post(
        f"/api/v1/approvals/{workflow['approval_id']}/decision",
        headers=manager.headers,
        json={
            "decision": ApprovalDecision.APPROVE.value,
            "override_discount_percent": 6,
            "comments": "6% is the most I can authorise",
        },
    )
    assert response.status_code == 200
    body = response.json()
    assert body["approval"]["override_discount_percent"] == 6.0

    line = body["request"]["items"][0]
    assert line["applied_discount_percent"] == 6.0
    assert line["requested_discount_percent"] == 9.0
    # 10000 - 6% = 9400, +18% tax = 11092
    assert body["request"]["pricing"]["final_amount"] == 11092.0


async def test_an_override_within_policy_clears_the_exception(
    client, customer_actor, manager
):
    workflow = await raise_approval(client, customer_actor, discount=9)

    response = await client.post(
        f"/api/v1/approvals/{workflow['approval_id']}/decision",
        headers=manager.headers,
        json={
            "decision": ApprovalDecision.APPROVE.value,
            "override_discount_percent": 4,
        },
    )
    body = response.json()
    assert body["request"]["exceptions"] == []
    assert body["request"]["items"][0]["discount_exception"] is False


async def test_an_override_beyond_policy_is_refused(client, customer_actor, manager):
    workflow = await raise_approval(client, customer_actor)

    response = await client.post(
        f"/api/v1/approvals/{workflow['approval_id']}/decision",
        headers=manager.headers,
        json={
            "decision": ApprovalDecision.APPROVE.value,
            "override_discount_percent": 55,
        },
    )
    assert response.status_code == 409
    assert "maximum that company policy permits" in response.json()["error"]["message"]

    # The task is untouched and still actionable.
    approval = await get_collection(Collections.APPROVALS).find_one(
        {"request_number": workflow["request"]["request_number"]}
    )
    assert approval["status"] == ApprovalStatus.PENDING.value


async def test_an_override_cannot_accompany_a_rejection(
    client, customer_actor, manager
):
    workflow = await raise_approval(client, customer_actor)
    response = await client.post(
        f"/api/v1/approvals/{workflow['approval_id']}/decision",
        headers=manager.headers,
        json={
            "decision": ApprovalDecision.REJECT.value,
            "comments": "No",
            "override_discount_percent": 3,
        },
    )
    assert response.status_code == 409


async def test_approval_is_recorded_as_its_own_execution(
    client, customer_actor, manager
):
    """The approval re-runs the pipeline, leaving a second trace."""
    workflow = await raise_approval(client, customer_actor)
    await client.post(
        f"/api/v1/approvals/{workflow['approval_id']}/decision",
        headers=manager.headers,
        json={"decision": ApprovalDecision.APPROVE.value},
    )

    response = await client.get(
        f"/api/v1/quotation-requests/{workflow['request']['id']}/executions",
        headers=manager.headers,
    )
    executions = response.json()
    assert len(executions) == 2
    triggers = {execution["trigger"] for execution in executions}
    assert triggers == {"SUBMISSION", "APPROVAL"}


# ---------------------------------------------------------------------------
# Reject and request modification
# ---------------------------------------------------------------------------


async def test_rejection_closes_the_request(client, customer_actor, manager):
    workflow = await raise_approval(client, customer_actor)

    response = await client.post(
        f"/api/v1/approvals/{workflow['approval_id']}/decision",
        headers=manager.headers,
        json={
            "decision": ApprovalDecision.REJECT.value,
            "comments": "Margin is too thin on this one.",
        },
    )
    assert response.status_code == 200
    body = response.json()
    assert body["approval"]["status"] == ApprovalStatus.REJECTED.value
    assert body["request"]["status"] == RequestStatus.REJECTED.value
    assert body["quotation_id"] is None

    quotations = await client.get("/api/v1/quotations", headers=manager.headers)
    assert quotations.json()["meta"]["total"] == 0


async def test_rejection_requires_a_comment(client, customer_actor, manager):
    workflow = await raise_approval(client, customer_actor)
    response = await client.post(
        f"/api/v1/approvals/{workflow['approval_id']}/decision",
        headers=manager.headers,
        json={"decision": ApprovalDecision.REJECT.value},
    )
    assert response.status_code == 409
    assert "comment explaining the decision" in response.json()["error"]["message"]


async def test_blank_comment_does_not_satisfy_the_requirement(
    client, customer_actor, manager
):
    workflow = await raise_approval(client, customer_actor)
    response = await client.post(
        f"/api/v1/approvals/{workflow['approval_id']}/decision",
        headers=manager.headers,
        json={"decision": ApprovalDecision.REJECT.value, "comments": "   "},
    )
    assert response.status_code == 409


async def test_requesting_modification_returns_the_request_to_the_customer(
    client, customer_actor, manager
):
    workflow = await raise_approval(client, customer_actor)

    response = await client.post(
        f"/api/v1/approvals/{workflow['approval_id']}/decision",
        headers=manager.headers,
        json={
            "decision": ApprovalDecision.REQUEST_MODIFICATION.value,
            "comments": "Please reduce the discount to 5% or raise the quantity.",
        },
    )
    assert response.status_code == 200
    assert response.json()["request"]["status"] == (
        RequestStatus.MODIFICATION_REQUESTED.value
    )

    # The customer can now edit and resubmit.
    request_id = workflow["request"]["id"]
    new_product = await create_product(sku="MOD-FIX")
    patched = await client.patch(
        f"/api/v1/quotation-requests/{request_id}",
        headers=customer_actor.headers,
        json={"items": [{"product_id": new_product, "quantity": 4}]},
    )
    assert patched.status_code == 200

    resubmitted = await client.post(
        f"/api/v1/quotation-requests/{request_id}/submit",
        headers=customer_actor.headers,
    )
    assert resubmitted.status_code == 200
    body = resubmitted.json()
    assert body["resulting_status"] == RequestStatus.COMPLETED.value
    assert body["request"]["revision"] == 1


async def test_resubmission_supersedes_the_old_approval_task(
    client, customer_actor, manager
):
    workflow = await raise_approval(client, customer_actor)
    request_id = workflow["request"]["id"]

    await client.post(
        f"/api/v1/approvals/{workflow['approval_id']}/decision",
        headers=manager.headers,
        json={
            "decision": ApprovalDecision.REQUEST_MODIFICATION.value,
            "comments": "Reduce the discount.",
        },
    )
    # Resubmit unchanged: it breaches the ceiling again and raises a new task.
    await client.post(
        f"/api/v1/quotation-requests/{request_id}/submit",
        headers=customer_actor.headers,
    )

    pending = await client.get(
        "/api/v1/approvals", headers=manager.headers, params={"status": "PENDING"}
    )
    assert pending.json()["meta"]["total"] == 1


# ---------------------------------------------------------------------------
# Concurrency and staleness
# ---------------------------------------------------------------------------


async def test_a_resolved_approval_cannot_be_decided_twice(
    client, customer_actor, manager
):
    workflow = await raise_approval(client, customer_actor)
    first = await client.post(
        f"/api/v1/approvals/{workflow['approval_id']}/decision",
        headers=manager.headers,
        json={"decision": ApprovalDecision.APPROVE.value},
    )
    assert first.status_code == 200

    second = await client.post(
        f"/api/v1/approvals/{workflow['approval_id']}/decision",
        headers=manager.headers,
        json={"decision": ApprovalDecision.REJECT.value, "comments": "Changed my mind"},
    )
    assert second.status_code == 409
    assert "already been resolved" in second.json()["error"]["message"]


async def test_approving_a_request_gone_stale_is_refused_and_reopened(
    client, customer_actor, manager
):
    """If the product is discontinued while the task waits, approval must fail."""
    workflow = await raise_approval(client, customer_actor)
    product_id = workflow["request"]["items"][0]["product_id"]

    await get_collection(Collections.PRODUCTS).update_one(
        {"_id": ObjectId(product_id)},
        {"$set": {"status": ProductStatus.DISCONTINUED.value}},
    )

    response = await client.post(
        f"/api/v1/approvals/{workflow['approval_id']}/decision",
        headers=manager.headers,
        json={"decision": ApprovalDecision.APPROVE.value},
    )
    assert response.status_code == 409
    assert "no longer passes validation" in response.json()["error"]["message"]

    # The task is back in the queue rather than silently lost.
    approval = await get_collection(Collections.APPROVALS).find_one(
        {"request_id": workflow["request"]["id"]}
    )
    assert approval["status"] == ApprovalStatus.PENDING.value


async def test_an_unknown_approval_id_is_a_404(client, manager):
    response = await client.post(
        "/api/v1/approvals/000000000000000000000000/decision",
        headers=manager.headers,
        json={"decision": ApprovalDecision.APPROVE.value},
    )
    assert response.status_code == 404


async def test_a_malformed_approval_id_is_rejected(client, manager):
    response = await client.get("/api/v1/approvals/not-an-id", headers=manager.headers)
    assert response.status_code in (400, 422)


# ---------------------------------------------------------------------------
# Notifications
# ---------------------------------------------------------------------------


async def test_the_manager_is_notified_when_a_task_is_raised(
    client, customer_actor, manager
):
    await raise_approval(client, customer_actor)

    response = await client.get(
        "/api/v1/notifications", headers=manager.headers, params={"unread_only": True}
    )
    assert response.status_code == 200
    items = response.json()["items"]
    assert any(item["type"] == "APPROVAL_REQUIRED" for item in items)


async def test_the_customer_is_notified_of_the_decision(
    client, customer_actor, manager
):
    workflow = await raise_approval(client, customer_actor)
    await client.post(
        f"/api/v1/approvals/{workflow['approval_id']}/decision",
        headers=manager.headers,
        json={"decision": ApprovalDecision.APPROVE.value},
    )

    response = await client.get(
        "/api/v1/notifications", headers=customer_actor.headers
    )
    types = [item["type"] for item in response.json()["items"]]
    assert "QUOTATION_READY" in types


async def test_notifications_can_be_marked_read(client, customer_actor, manager):
    await raise_approval(client, customer_actor)

    before = await client.get(
        "/api/v1/notifications/unread-count", headers=manager.headers
    )
    assert before.json()["unread"] >= 1

    await client.post("/api/v1/notifications/read-all", headers=manager.headers)
    after = await client.get(
        "/api/v1/notifications/unread-count", headers=manager.headers
    )
    assert after.json()["unread"] == 0


async def test_a_user_cannot_mark_another_users_notification_read(
    client, customer_actor, manager
):
    await raise_approval(client, customer_actor)
    manager_inbox = await client.get("/api/v1/notifications", headers=manager.headers)
    notification_id = manager_inbox.json()["items"][0]["id"]

    response = await client.post(
        f"/api/v1/notifications/{notification_id}/read",
        headers=customer_actor.headers,
    )
    assert response.status_code == 404
