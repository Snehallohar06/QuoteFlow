"""End-to-end workflow tests: every branch of the pipeline."""

from decimal import Decimal

import pytest

from app.db.mongo import Collections, get_collection
from app.models.enums import (
    ApprovalStatus,
    AvailabilityStatus,
    CustomerStatus,
    ExceptionType,
    ProductStatus,
    RequestStatus,
    StepStatus,
    UserRole,
    WorkflowOutcome,
    WorkflowStep,
)
from tests.conftest import (
    Actor,
    _login,
    create_customer,
    create_product,
    create_user,
)

pytestmark = pytest.mark.workflow


async def submit(client, actor, items, **extra):
    payload = {"items": items, "submit": True, **extra}
    response = await client.post(
        "/api/v1/quotation-requests", headers=actor.headers, json=payload
    )
    assert response.status_code == 201, response.text
    body = response.json()
    assert body["submitted"] is True
    return body["workflow"]


# ---------------------------------------------------------------------------
# Happy path
# ---------------------------------------------------------------------------


async def test_in_policy_request_is_auto_approved_and_quoted(client, customer_actor):
    product_id = await create_product(unit_price="1000.00", stock_quantity=100)
    workflow = await submit(
        client, customer_actor, [{"product_id": product_id, "quantity": 3}]
    )

    assert workflow["outcome"] == WorkflowOutcome.COMPLETED.value
    assert workflow["resulting_status"] == RequestStatus.COMPLETED.value
    assert workflow["requires_approval"] is False
    assert workflow["exceptions"] == []
    assert workflow["quotation_id"] is not None
    assert workflow["approval_id"] is None
    # The success gate must be fully satisfied for COMPLETED.
    assert all(workflow["gate"].values()), workflow["gate"]

    pricing = workflow["request"]["pricing"]
    assert pricing["subtotal"] == 3000.0
    assert pricing["total_discount"] == 0.0
    assert pricing["taxable_amount"] == 3000.0
    assert pricing["total_tax"] == 540.0  # 18% default
    assert pricing["final_amount"] == 3540.0
    assert pricing["line_count"] == 1
    assert pricing["total_quantity"] == 3


async def test_discount_within_the_tier_is_auto_approved(client, customer_actor):
    product_id = await create_product(unit_price="1000.00", stock_quantity=100)
    # 10 units -> 5% ceiling; asking for 5% exactly.
    workflow = await submit(
        client,
        customer_actor,
        [{"product_id": product_id, "quantity": 10, "requested_discount_percent": 5}],
    )

    assert workflow["outcome"] == WorkflowOutcome.COMPLETED.value
    line = workflow["request"]["items"][0]
    assert line["applied_discount_percent"] == 5.0
    assert line["max_allowed_discount_percent"] == 5.0
    assert line["discount_exception"] is False
    assert line["line_discount_amount"] == 500.0
    assert line["line_total"] == 11210.0  # 9500 + 18%


async def test_a_draft_is_not_processed_until_submitted(client, customer_actor):
    product_id = await create_product()
    response = await client.post(
        "/api/v1/quotation-requests",
        headers=customer_actor.headers,
        json={
            "items": [{"product_id": product_id, "quantity": 2}],
            "submit": False,
        },
    )
    assert response.status_code == 201
    body = response.json()
    assert body["submitted"] is False
    assert body["request"]["status"] == RequestStatus.DRAFT.value
    # A draft carries no figures: nothing has been validated yet.
    assert body["request"]["pricing"] is None

    submitted = await client.post(
        f"/api/v1/quotation-requests/{body['request']['id']}/submit",
        headers=customer_actor.headers,
    )
    assert submitted.status_code == 200
    assert submitted.json()["resulting_status"] == RequestStatus.COMPLETED.value


# ---------------------------------------------------------------------------
# Approval routing
# ---------------------------------------------------------------------------


async def test_discount_above_the_tier_goes_to_a_manager(client, customer_actor):
    product_id = await create_product(unit_price="1000.00", cost_price="100.00")
    workflow = await submit(
        client,
        customer_actor,
        [{"product_id": product_id, "quantity": 10, "requested_discount_percent": 9}],
    )

    assert workflow["outcome"] == WorkflowOutcome.PENDING_APPROVAL.value
    assert workflow["resulting_status"] == RequestStatus.PENDING_APPROVAL.value
    assert workflow["requires_approval"] is True
    assert workflow["quotation_id"] is None
    assert workflow["approval_id"] is not None

    exceptions = workflow["exceptions"]
    assert len(exceptions) == 1
    assert exceptions[0]["type"] == ExceptionType.DISCOUNT_LIMIT_EXCEEDED.value
    assert exceptions[0]["context"]["max_allowed_percent"] == 5.0
    assert exceptions[0]["context"]["requested_percent"] == 9.0

    # The exception line is still priced at the requested discount, so the
    # manager sees exactly what was asked for.
    line = workflow["request"]["items"][0]
    assert line["applied_discount_percent"] == 9.0
    assert line["discount_exception"] is True


async def test_an_approval_task_is_created_with_the_sla_and_snapshot(
    client, customer_actor
):
    product_id = await create_product(unit_price="1000.00", cost_price="100.00")
    workflow = await submit(
        client,
        customer_actor,
        [{"product_id": product_id, "quantity": 10, "requested_discount_percent": 9}],
    )

    approval = await get_collection(Collections.APPROVALS).find_one(
        {"request_id": workflow["request"]["id"]}
    )
    assert approval is not None
    assert approval["status"] == ApprovalStatus.PENDING.value
    assert approval["sla_due_at"] is not None
    assert approval["pricing_snapshot"]["final_amount"].to_decimal() == Decimal(
        "10738.00"
    )
    assert approval["requested_discount_percent"].to_decimal() == Decimal("9.00")


async def test_order_value_threshold_forces_review(client, customer_actor, manager):
    await client.patch(
        "/api/v1/settings",
        headers=manager.headers,
        json={"approval_policy": {"order_value_threshold": 10000}},
    )
    product_id = await create_product(unit_price="5000.00", stock_quantity=100)

    workflow = await submit(
        client, customer_actor, [{"product_id": product_id, "quantity": 3}]
    )
    assert workflow["requires_approval"] is True
    types = [exception["type"] for exception in workflow["exceptions"]]
    assert ExceptionType.ORDER_VALUE_THRESHOLD.value in types


async def test_threshold_of_zero_disables_the_value_check(
    client, customer_actor, manager
):
    await client.patch(
        "/api/v1/settings",
        headers=manager.headers,
        json={"approval_policy": {"order_value_threshold": 0}},
    )
    product_id = await create_product(unit_price="900000.00", stock_quantity=100)
    workflow = await submit(
        client, customer_actor, [{"product_id": product_id, "quantity": 2}]
    )
    assert workflow["outcome"] == WorkflowOutcome.COMPLETED.value


async def test_credit_limit_breach_forces_review(client):
    customer_id = await create_customer(
        code="CUST-CREDIT", email="credit@test.example", credit_limit="5000.00"
    )
    user = await create_user(
        email="credit.buyer@test.example",
        role=UserRole.CUSTOMER,
        customer_id=customer_id,
    )
    actor = Actor(user["id"], user["email"], await _login(client, user["email"]))

    product_id = await create_product(unit_price="4000.00", stock_quantity=100)
    workflow = await submit(
        client, actor, [{"product_id": product_id, "quantity": 2}]
    )

    types = [exception["type"] for exception in workflow["exceptions"]]
    assert ExceptionType.CREDIT_LIMIT_EXCEEDED.value in types
    breach = next(
        exception
        for exception in workflow["exceptions"]
        if exception["type"] == ExceptionType.CREDIT_LIMIT_EXCEEDED.value
    )
    assert breach["context"]["credit_limit"] == 5000.0
    assert breach["context"]["projected_exposure"] == 9440.0


async def test_stock_shortfall_forces_review_but_still_quotes(client, customer_actor):
    product_id = await create_product(
        sku="SHORT-1", stock_quantity=4, reserved_quantity=0, lead_time_days=21
    )
    workflow = await submit(
        client, customer_actor, [{"product_id": product_id, "quantity": 10}]
    )

    types = [exception["type"] for exception in workflow["exceptions"]]
    assert ExceptionType.STOCK_SHORTFALL.value in types

    availability = workflow["request"]["items"][0]["availability"]
    assert availability["status"] == AvailabilityStatus.PARTIAL.value
    assert availability["available_quantity"] == 4
    assert availability["shortfall"] == 6
    assert availability["lead_time_days"] == 21


async def test_reserved_stock_is_not_available_to_quote(client, customer_actor):
    product_id = await create_product(
        sku="RESERVED-1", stock_quantity=10, reserved_quantity=8
    )
    workflow = await submit(
        client, customer_actor, [{"product_id": product_id, "quantity": 5}]
    )
    availability = workflow["request"]["items"][0]["availability"]
    assert availability["available_quantity"] == 2
    assert availability["shortfall"] == 3


async def test_backorder_can_be_forbidden_by_policy(client, customer_actor, manager):
    await client.patch(
        "/api/v1/settings",
        headers=manager.headers,
        json={"quotation_policy": {"allow_backorder": False}},
    )
    product_id = await create_product(sku="NOBACK-1", stock_quantity=2)

    workflow = await submit(
        client, customer_actor, [{"product_id": product_id, "quantity": 10}]
    )
    assert workflow["outcome"] == WorkflowOutcome.VALIDATION_FAILED.value
    assert any(
        "backorders are not permitted" in error
        for error in workflow["validation_errors"]
    )


async def test_several_exceptions_are_all_reported(client, customer_actor, manager):
    await client.patch(
        "/api/v1/settings",
        headers=manager.headers,
        json={"approval_policy": {"order_value_threshold": 1000}},
    )
    product_id = await create_product(
        sku="MULTI-1", unit_price="1000.00", cost_price="100.00", stock_quantity=3
    )
    workflow = await submit(
        client,
        customer_actor,
        [{"product_id": product_id, "quantity": 10, "requested_discount_percent": 9}],
    )

    types = {exception["type"] for exception in workflow["exceptions"]}
    assert types == {
        ExceptionType.DISCOUNT_LIMIT_EXCEEDED.value,
        ExceptionType.ORDER_VALUE_THRESHOLD.value,
        ExceptionType.STOCK_SHORTFALL.value,
    }


# ---------------------------------------------------------------------------
# Validation failures
# ---------------------------------------------------------------------------


async def test_a_discontinued_product_fails_validation(client, customer_actor):
    product_id = await create_product(
        sku="GONE-1", status=ProductStatus.DISCONTINUED
    )
    workflow = await submit(
        client, customer_actor, [{"product_id": product_id, "quantity": 1}]
    )

    assert workflow["outcome"] == WorkflowOutcome.VALIDATION_FAILED.value
    assert workflow["resulting_status"] == RequestStatus.VALIDATION_FAILED.value
    assert any("discontinued" in error for error in workflow["validation_errors"])
    assert workflow["quotation_id"] is None


async def test_a_blocked_customer_fails_validation(client):
    customer_id = await create_customer(
        code="CUST-BLOCKED",
        email="blocked@test.example",
        status=CustomerStatus.BLOCKED.value,
    )
    user = await create_user(
        email="blocked.buyer@test.example",
        role=UserRole.CUSTOMER,
        customer_id=customer_id,
    )
    actor = Actor(user["id"], user["email"], await _login(client, user["email"]))
    product_id = await create_product()

    # Blocking is caught up front, before a request is even created.
    response = await client.post(
        "/api/v1/quotation-requests",
        headers=actor.headers,
        json={"items": [{"product_id": product_id, "quantity": 1}], "submit": True},
    )
    assert response.status_code == 409
    assert "blocked" in response.json()["error"]["message"]


async def test_a_customer_put_on_hold_mid_flight_fails_validation(
    client, customer_actor
):
    product_id = await create_product()
    draft = await client.post(
        "/api/v1/quotation-requests",
        headers=customer_actor.headers,
        json={"items": [{"product_id": product_id, "quantity": 1}], "submit": False},
    )
    request_id = draft.json()["request"]["id"]

    await get_collection(Collections.CUSTOMERS).update_one(
        {"code": "CUST-TEST-1"}, {"$set": {"status": CustomerStatus.ON_HOLD.value}}
    )

    response = await client.post(
        f"/api/v1/quotation-requests/{request_id}/submit",
        headers=customer_actor.headers,
    )
    assert response.status_code == 200
    assert response.json()["outcome"] == WorkflowOutcome.VALIDATION_FAILED.value
    assert any("on hold" in error for error in response.json()["validation_errors"])


async def test_a_discount_beyond_the_absolute_maximum_fails_validation(
    client, customer_actor
):
    product_id = await create_product(unit_price="1000.00", cost_price="100.00")
    workflow = await submit(
        client,
        customer_actor,
        [{"product_id": product_id, "quantity": 100, "requested_discount_percent": 45}],
    )
    assert workflow["outcome"] == WorkflowOutcome.VALIDATION_FAILED.value
    assert any(
        "under any approval" in error for error in workflow["validation_errors"]
    )


async def test_a_discount_below_cost_fails_validation(client, customer_actor):
    product_id = await create_product(unit_price="1000.00", cost_price="950.00")
    workflow = await submit(
        client,
        customer_actor,
        [{"product_id": product_id, "quantity": 100, "requested_discount_percent": 12}],
    )
    assert workflow["outcome"] == WorkflowOutcome.VALIDATION_FAILED.value
    assert any("below the cost price" in error for error in workflow["validation_errors"])


async def test_an_unknown_product_is_rejected_at_creation(client, customer_actor):
    response = await client.post(
        "/api/v1/quotation-requests",
        headers=customer_actor.headers,
        json={
            "items": [{"product_id": "000000000000000000000000", "quantity": 1}],
            "submit": True,
        },
    )
    assert response.status_code == 404


async def test_a_duplicate_product_line_is_rejected_by_the_schema(
    client, customer_actor
):
    product_id = await create_product()
    response = await client.post(
        "/api/v1/quotation-requests",
        headers=customer_actor.headers,
        json={
            "items": [
                {"product_id": product_id, "quantity": 2},
                {"product_id": product_id, "quantity": 3},
            ],
            "submit": True,
        },
    )
    assert response.status_code == 422


async def test_zero_quantity_is_rejected_by_the_schema(client, customer_actor):
    product_id = await create_product()
    response = await client.post(
        "/api/v1/quotation-requests",
        headers=customer_actor.headers,
        json={"items": [{"product_id": product_id, "quantity": 0}], "submit": True},
    )
    assert response.status_code == 422


async def test_an_empty_item_list_is_rejected_by_the_schema(client, customer_actor):
    response = await client.post(
        "/api/v1/quotation-requests",
        headers=customer_actor.headers,
        json={"items": [], "submit": True},
    )
    assert response.status_code == 422


# ---------------------------------------------------------------------------
# Execution trace
# ---------------------------------------------------------------------------


async def test_the_execution_records_every_step_in_order(client, customer_actor):
    product_id = await create_product()
    workflow = await submit(
        client, customer_actor, [{"product_id": product_id, "quantity": 5}]
    )

    response = await client.get(
        f"/api/v1/quotation-requests/{workflow['request']['id']}/executions",
        headers=customer_actor.headers,
    )
    assert response.status_code == 200
    executions = response.json()
    assert len(executions) == 1

    execution = executions[0]
    assert execution["engine_version"] == "2.0.0"
    assert execution["outcome"] == WorkflowOutcome.COMPLETED.value
    assert [step["step"] for step in execution["steps"]] == [
        WorkflowStep.VALIDATE_REQUEST.value,
        WorkflowStep.CHECK_AVAILABILITY.value,
        WorkflowStep.CALCULATE_PRICING.value,
        WorkflowStep.EVALUATE_DISCOUNT_RULES.value,
        WorkflowStep.DETERMINE_APPROVAL_ROUTE.value,
        WorkflowStep.GENERATE_DOCUMENT.value,
        WorkflowStep.VERIFY_DOCUMENT.value,
        WorkflowStep.FINALISE.value,
    ]
    assert all(step["status"] == StepStatus.SUCCESS.value for step in execution["steps"])
    assert all(step["duration_ms"] >= 0 for step in execution["steps"])
    assert execution["duration_ms"] >= 0


async def test_steps_after_a_failure_are_recorded_as_skipped(client, customer_actor):
    product_id = await create_product(sku="SKIP-1", status=ProductStatus.DISCONTINUED)
    workflow = await submit(
        client, customer_actor, [{"product_id": product_id, "quantity": 1}]
    )

    response = await client.get(
        f"/api/v1/quotation-requests/{workflow['request']['id']}/executions",
        headers=customer_actor.headers,
    )
    steps = {step["step"]: step["status"] for step in response.json()[0]["steps"]}

    assert steps[WorkflowStep.VALIDATE_REQUEST.value] == StepStatus.FAILED.value
    assert steps[WorkflowStep.CHECK_AVAILABILITY.value] == StepStatus.SKIPPED.value
    assert steps[WorkflowStep.CALCULATE_PRICING.value] == StepStatus.SKIPPED.value
    assert steps[WorkflowStep.FINALISE.value] == StepStatus.SUCCESS.value


async def test_the_pricing_step_records_the_figures_it_produced(client, customer_actor):
    product_id = await create_product(unit_price="1000.00")
    workflow = await submit(
        client, customer_actor, [{"product_id": product_id, "quantity": 4}]
    )

    response = await client.get(
        f"/api/v1/quotation-requests/{workflow['request']['id']}/executions",
        headers=customer_actor.headers,
    )
    pricing_step = next(
        step
        for step in response.json()[0]["steps"]
        if step["step"] == WorkflowStep.CALCULATE_PRICING.value
    )
    assert pricing_step["output"]["subtotal"] == 4000.0
    assert pricing_step["output"]["final_amount"] == 4720.0


async def test_the_discount_step_records_the_rule_trace(client, customer_actor):
    product_id = await create_product(unit_price="1000.00", cost_price="100.00")
    workflow = await submit(
        client,
        customer_actor,
        [{"product_id": product_id, "quantity": 30, "requested_discount_percent": 8}],
    )

    response = await client.get(
        f"/api/v1/quotation-requests/{workflow['request']['id']}/executions",
        headers=customer_actor.headers,
    )
    rules_step = next(
        step
        for step in response.json()[0]["steps"]
        if step["step"] == WorkflowStep.EVALUATE_DISCOUNT_RULES.value
    )
    trace = rules_step["output"]["rules"][0]
    assert trace["quantity"] == 30
    assert trace["base_tier_percent"] == 10.0
    assert trace["max_allowed_percent"] == 10.0
    assert trace["verdict"] == "ALLOWED"


async def test_identical_submissions_produce_identical_decisions(
    client, customer_actor
):
    """The pipeline is deterministic: no inference, no randomness."""
    product_id = await create_product(unit_price="1234.56", cost_price="100.00")
    items = [
        {"product_id": product_id, "quantity": 17, "requested_discount_percent": 4.5}
    ]

    first = await submit(client, customer_actor, items)
    second = await submit(client, customer_actor, items)

    assert first["outcome"] == second["outcome"]
    assert first["request"]["pricing"] == second["request"]["pricing"]
    assert [exception["type"] for exception in first["exceptions"]] == [
        exception["type"] for exception in second["exceptions"]
    ]


# ---------------------------------------------------------------------------
# Status history and re-submission
# ---------------------------------------------------------------------------


async def test_status_history_records_the_whole_journey(client, customer_actor):
    product_id = await create_product()
    workflow = await submit(
        client, customer_actor, [{"product_id": product_id, "quantity": 2}]
    )
    history = [entry["to_status"] for entry in workflow["request"]["status_history"]]

    assert history == [
        RequestStatus.DRAFT.value,
        RequestStatus.SUBMITTED.value,
        RequestStatus.PRICED.value,
        RequestStatus.APPROVED.value,
        RequestStatus.COMPLETED.value,
    ]


async def test_a_failed_request_can_be_fixed_and_resubmitted(client, customer_actor):
    bad_product = await create_product(
        sku="BAD-1", status=ProductStatus.DISCONTINUED
    )
    good_product = await create_product(sku="GOOD-1")

    workflow = await submit(
        client, customer_actor, [{"product_id": bad_product, "quantity": 1}]
    )
    request_id = workflow["request"]["id"]
    assert workflow["resulting_status"] == RequestStatus.VALIDATION_FAILED.value

    patched = await client.patch(
        f"/api/v1/quotation-requests/{request_id}",
        headers=customer_actor.headers,
        json={"items": [{"product_id": good_product, "quantity": 2}]},
    )
    assert patched.status_code == 200

    resubmitted = await client.post(
        f"/api/v1/quotation-requests/{request_id}/submit",
        headers=customer_actor.headers,
    )
    assert resubmitted.status_code == 200
    body = resubmitted.json()
    assert body["resulting_status"] == RequestStatus.COMPLETED.value
    # A resubmission after a failure counts as a new revision.
    assert body["request"]["revision"] == 1


async def test_an_approved_request_cannot_be_edited_or_resubmitted(
    client, customer_actor
):
    product_id = await create_product()
    workflow = await submit(
        client, customer_actor, [{"product_id": product_id, "quantity": 1}]
    )
    request_id = workflow["request"]["id"]

    patched = await client.patch(
        f"/api/v1/quotation-requests/{request_id}",
        headers=customer_actor.headers,
        json={"items": [{"product_id": product_id, "quantity": 9}]},
    )
    assert patched.status_code == 409
    assert patched.json()["error"]["code"] == "workflow_error"

    resubmitted = await client.post(
        f"/api/v1/quotation-requests/{request_id}/submit",
        headers=customer_actor.headers,
    )
    assert resubmitted.status_code == 409


async def test_editing_a_draft_clears_any_earlier_pricing(client, customer_actor):
    bad_product = await create_product(sku="CLR-BAD", status=ProductStatus.DISCONTINUED)
    good_product = await create_product(sku="CLR-GOOD")

    workflow = await submit(
        client, customer_actor, [{"product_id": bad_product, "quantity": 1}]
    )
    request_id = workflow["request"]["id"]

    patched = await client.patch(
        f"/api/v1/quotation-requests/{request_id}",
        headers=customer_actor.headers,
        json={"items": [{"product_id": good_product, "quantity": 1}]},
    )
    body = patched.json()
    assert body["pricing"] is None
    assert body["validation_errors"] == []
    assert body["requires_approval"] is False


async def test_a_request_can_be_cancelled(client, customer_actor):
    product_id = await create_product(unit_price="1000.00", cost_price="100.00")
    workflow = await submit(
        client,
        customer_actor,
        [{"product_id": product_id, "quantity": 10, "requested_discount_percent": 9}],
    )
    request_id = workflow["request"]["id"]

    response = await client.post(
        f"/api/v1/quotation-requests/{request_id}/cancel",
        headers=customer_actor.headers,
        json={"reason": "Project postponed"},
    )
    assert response.status_code == 200
    assert response.json()["status"] == RequestStatus.CANCELLED.value

    # The pending approval leaves the manager's queue.
    approval = await get_collection(Collections.APPROVALS).find_one(
        {"request_id": request_id}
    )
    assert approval["status"] != ApprovalStatus.PENDING.value


async def test_an_approved_request_cannot_be_cancelled(client, customer_actor):
    product_id = await create_product()
    workflow = await submit(
        client, customer_actor, [{"product_id": product_id, "quantity": 1}]
    )
    response = await client.post(
        f"/api/v1/quotation-requests/{workflow['request']['id']}/cancel",
        headers=customer_actor.headers,
        json={},
    )
    assert response.status_code == 409


# ---------------------------------------------------------------------------
# Pricing freshness and access control
# ---------------------------------------------------------------------------


async def test_pricing_uses_the_catalogue_price_at_submission_time(
    client, customer_actor, employee
):
    product_id = await create_product(unit_price="1000.00")
    draft = await client.post(
        "/api/v1/quotation-requests",
        headers=customer_actor.headers,
        json={"items": [{"product_id": product_id, "quantity": 2}], "submit": False},
    )
    request_id = draft.json()["request"]["id"]

    await client.patch(
        f"/api/v1/products/{product_id}",
        headers=employee.headers,
        json={"unit_price": 1500},
    )

    submitted = await client.post(
        f"/api/v1/quotation-requests/{request_id}/submit",
        headers=customer_actor.headers,
    )
    assert submitted.json()["request"]["pricing"]["subtotal"] == 3000.0


async def test_a_customer_cannot_read_another_customers_request(
    client, customer_actor
):
    other_customer = await create_customer(
        code="CUST-OTHER", email="other@test.example"
    )
    other_user = await create_user(
        email="other.buyer@test.example",
        role=UserRole.CUSTOMER,
        customer_id=other_customer,
    )
    other = Actor(
        other_user["id"], other_user["email"], await _login(client, other_user["email"])
    )

    product_id = await create_product()
    workflow = await submit(
        client, customer_actor, [{"product_id": product_id, "quantity": 1}]
    )

    response = await client.get(
        f"/api/v1/quotation-requests/{workflow['request']['id']}",
        headers=other.headers,
    )
    assert response.status_code == 403

    listed = await client.get("/api/v1/quotation-requests", headers=other.headers)
    assert listed.json()["meta"]["total"] == 0


async def test_staff_can_read_any_request(client, customer_actor, employee):
    product_id = await create_product()
    workflow = await submit(
        client, customer_actor, [{"product_id": product_id, "quantity": 1}]
    )
    response = await client.get(
        f"/api/v1/quotation-requests/{workflow['request']['id']}",
        headers=employee.headers,
    )
    assert response.status_code == 200


async def test_staff_must_name_a_customer_when_raising_a_request(client, employee):
    product_id = await create_product()
    response = await client.post(
        "/api/v1/quotation-requests",
        headers=employee.headers,
        json={"items": [{"product_id": product_id, "quantity": 1}], "submit": True},
    )
    assert response.status_code == 409
    assert "customer must be selected" in response.json()["error"]["message"]


async def test_staff_can_raise_a_request_on_behalf_of_a_customer(client, employee):
    customer_id = await create_customer(code="CUST-BEHALF", email="behalf@test.example")
    product_id = await create_product()

    response = await client.post(
        "/api/v1/quotation-requests",
        headers=employee.headers,
        json={
            "customer_id": customer_id,
            "items": [{"product_id": product_id, "quantity": 2}],
            "submit": True,
        },
    )
    assert response.status_code == 201
    workflow = response.json()["workflow"]
    assert workflow["request"]["customer_code"] == "CUST-BEHALF"
    assert workflow["request"]["created_by_role"] == "SALES_EMPLOYEE"


async def test_a_customer_cannot_submit_for_someone_else(client, customer_actor):
    """A customer_id in the payload is ignored for a customer account."""
    other_customer = await create_customer(
        code="CUST-IGNORED", email="ignored@test.example"
    )
    product_id = await create_product()

    workflow = await submit(
        client,
        customer_actor,
        [{"product_id": product_id, "quantity": 1}],
        customer_id=other_customer,
    )
    assert workflow["request"]["customer_code"] == "CUST-TEST-1"


async def test_a_product_tax_override_is_applied(client, customer_actor):
    product_id = await create_product(unit_price="1000.00", tax_rate="5")
    workflow = await submit(
        client, customer_actor, [{"product_id": product_id, "quantity": 2}]
    )
    pricing = workflow["request"]["pricing"]
    assert pricing["total_tax"] == 100.0  # 5%, not the 18% default
    assert pricing["final_amount"] == 2100.0


async def test_a_product_discount_cap_is_applied(client, customer_actor):
    product_id = await create_product(
        unit_price="1000.00", cost_price="100.00", max_discount_percent="3"
    )
    workflow = await submit(
        client,
        customer_actor,
        [{"product_id": product_id, "quantity": 30, "requested_discount_percent": 6}],
    )
    line = workflow["request"]["items"][0]
    assert line["max_allowed_discount_percent"] == 3.0
    assert workflow["requires_approval"] is True


# ---------------------------------------------------------------------------
# Reprocessing (staff re-run)
# ---------------------------------------------------------------------------


async def test_reprocess_clears_a_request_once_the_cause_is_fixed(
    client, customer_actor, employee
):
    """Re-running after a data correction should let the request through."""
    product_id = await create_product(
        sku="RERUN-OK", status=ProductStatus.DISCONTINUED
    )
    workflow = await submit(
        client, customer_actor, [{"product_id": product_id, "quantity": 2}]
    )
    assert workflow["outcome"] == WorkflowOutcome.VALIDATION_FAILED.value

    # Reactivate the product, then re-run.
    await client.patch(
        f"/api/v1/products/{product_id}",
        headers=employee.headers,
        json={"status": ProductStatus.ACTIVE.value},
    )
    response = await client.post(
        f"/api/v1/quotation-requests/{workflow['request']['id']}/reprocess",
        headers=employee.headers,
    )
    assert response.status_code == 200, response.text
    assert response.json()["outcome"] == WorkflowOutcome.COMPLETED.value


async def test_reprocess_records_a_repeat_failure_instead_of_erroring(
    client, customer_actor, employee
):
    """A re-run that still fails must land on VALIDATION_FAILED, not 409.

    Regression test: the engine used to enter UNDER_VALIDATION only for the
    SUBMISSION trigger, so a reprocess stayed on SUBMITTED and the state machine
    then refused the SUBMITTED -> VALIDATION_FAILED transition.
    """
    product_id = await create_product(
        sku="RERUN-FAIL", status=ProductStatus.DISCONTINUED
    )
    workflow = await submit(
        client, customer_actor, [{"product_id": product_id, "quantity": 2}]
    )
    assert workflow["outcome"] == WorkflowOutcome.VALIDATION_FAILED.value

    # Nothing fixed, so the same failure should be recorded again.
    response = await client.post(
        f"/api/v1/quotation-requests/{workflow['request']['id']}/reprocess",
        headers=employee.headers,
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["outcome"] == WorkflowOutcome.VALIDATION_FAILED.value
    assert body["resulting_status"] == RequestStatus.VALIDATION_FAILED.value
    assert any("discontinued" in error for error in body["validation_errors"])


async def test_reprocess_leaves_a_second_execution_trace(
    client, customer_actor, employee
):
    product_id = await create_product(sku="RERUN-TRACE")
    workflow = await submit(
        client, customer_actor, [{"product_id": product_id, "quantity": 2}]
    )
    # An approved request cannot be reprocessed, so use a failed one.
    bad = await create_product(sku="RERUN-TRACE-BAD", status=ProductStatus.DISCONTINUED)
    failed = await submit(client, customer_actor, [{"product_id": bad, "quantity": 1}])

    await client.post(
        f"/api/v1/quotation-requests/{failed['request']['id']}/reprocess",
        headers=employee.headers,
    )
    response = await client.get(
        f"/api/v1/quotation-requests/{failed['request']['id']}/executions",
        headers=employee.headers,
    )
    executions = response.json()
    assert len(executions) == 2
    assert {execution["trigger"] for execution in executions} == {
        "SUBMISSION",
        "REPROCESS",
    }
    del workflow


async def test_a_customer_cannot_reprocess(client, customer_actor):
    product_id = await create_product(
        sku="RERUN-DENIED", status=ProductStatus.DISCONTINUED
    )
    workflow = await submit(
        client, customer_actor, [{"product_id": product_id, "quantity": 1}]
    )
    response = await client.post(
        f"/api/v1/quotation-requests/{workflow['request']['id']}/reprocess",
        headers=customer_actor.headers,
    )
    assert response.status_code == 403


async def test_an_approved_request_cannot_be_reprocessed(client, customer_actor, employee):
    product_id = await create_product(sku="RERUN-APPROVED")
    workflow = await submit(
        client, customer_actor, [{"product_id": product_id, "quantity": 2}]
    )
    assert workflow["resulting_status"] == RequestStatus.COMPLETED.value

    response = await client.post(
        f"/api/v1/quotation-requests/{workflow['request']['id']}/reprocess",
        headers=employee.headers,
    )
    assert response.status_code == 409


async def test_a_pending_approval_cannot_be_reprocessed(client, customer_actor, employee):
    product_id = await create_product(
        sku="RERUN-PENDING", unit_price="1000.00", cost_price="100.00"
    )
    workflow = await submit(
        client,
        customer_actor,
        [{"product_id": product_id, "quantity": 10, "requested_discount_percent": 9}],
    )
    assert workflow["resulting_status"] == RequestStatus.PENDING_APPROVAL.value

    response = await client.post(
        f"/api/v1/quotation-requests/{workflow['request']['id']}/reprocess",
        headers=employee.headers,
    )
    assert response.status_code == 409
    assert "awaiting a manager decision" in response.json()["error"]["message"]
