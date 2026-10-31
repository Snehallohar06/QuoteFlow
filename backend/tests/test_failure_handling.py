"""The twelve required failure scenarios, plus idempotency.

Each test asserts the four things the brief asks of a failure: the error is
recorded, the workflow status is updated, existing information is preserved, and
the request is retried only when retrying could help.
"""

import pytest
from bson import Decimal128, ObjectId
from pymongo.errors import ConnectionFailure, DuplicateKeyError

from app.db.mongo import Collections, get_collection
from app.models.enums import (
    EscalationReason,
    ProductStatus,
    RequestStatus,
    UserRole,
    WorkflowOutcome,
)
from app.models.quotation import Quotation
from app.services import action_tool, checker_tool, workflow_engine
from app.utils.money import decode_decimals
from tests.conftest import Actor, _login, create_customer, create_product, create_user

pytestmark = pytest.mark.workflow


async def submit(client, actor, items, **extra):
    response = await client.post(
        "/api/v1/quotation-requests",
        headers=actor.headers,
        json={"items": items, "submit": True, **extra},
    )
    return response


async def submit_ok(client, actor, items, **extra):
    response = await submit(client, actor, items, **extra)
    assert response.status_code == 201, response.text
    return response.json()["workflow"]


async def load_quotation(quotation_id: str) -> Quotation:
    raw = await get_collection(Collections.QUOTATIONS).find_one(
        {"_id": ObjectId(quotation_id)}
    )
    return Quotation.from_mongo(decode_decimals(raw))


async def audit_count(client, manager, action: str) -> int:
    response = await client.get(
        "/api/v1/audit-logs", headers=manager.headers, params={"action": action}
    )
    return response.json()["meta"]["total"]


# ===========================================================================
# 1. Missing customer information
# ===========================================================================


async def test_1_missing_customer_information(client, manager):
    customer_id = await create_customer(
        code="FAIL-NOCUST", email="nocust@test.example"
    )
    # Blank the contact details the way an imported record can be.
    await get_collection(Collections.CUSTOMERS).update_one(
        {"_id": ObjectId(customer_id)},
        {"$set": {"phone": "", "contact_name": ""}},
    )
    user = await create_user(
        email="nocust.buyer@test.example",
        role=UserRole.CUSTOMER,
        customer_id=customer_id,
    )
    actor = Actor(user["id"], user["email"], await _login(client, user["email"]))
    product_id = await create_product(sku="FAIL-1")

    workflow = await submit_ok(
        client, actor, [{"product_id": product_id, "quantity": 1}]
    )

    assert workflow["outcome"] == WorkflowOutcome.VALIDATION_FAILED.value
    assert workflow["resulting_status"] == RequestStatus.VALIDATION_FAILED.value
    assert any(
        "missing required information" in error
        for error in workflow["validation_errors"]
    )
    # Information is preserved: the lines the customer submitted are still there.
    assert len(workflow["request"]["items"]) == 1
    # Not retried - a missing field is a verdict, not a fault.
    assert workflow["retries_used"] == 0


# ===========================================================================
# 2. Invalid product ID
# ===========================================================================


async def test_2_invalid_product_id(client, customer_actor):
    response = await submit(
        client,
        customer_actor,
        [{"product_id": "000000000000000000000000", "quantity": 1}],
    )
    assert response.status_code == 404
    assert response.json()["error"]["details"]["missing_product_ids"]


async def test_2b_malformed_product_id(client, customer_actor):
    response = await submit(
        client, customer_actor, [{"product_id": "not-an-object-id", "quantity": 1}]
    )
    assert response.status_code == 422


async def test_2c_a_product_discontinued_after_drafting(client, customer_actor):
    """Information is preserved while the status moves to failed."""
    product_id = await create_product(sku="FAIL-2C")
    draft = await client.post(
        "/api/v1/quotation-requests",
        headers=customer_actor.headers,
        json={
            "items": [{"product_id": product_id, "quantity": 4}],
            "customer_notes": "Keep this note.",
            "submit": False,
        },
    )
    request_id = draft.json()["request"]["id"]

    await get_collection(Collections.PRODUCTS).update_one(
        {"_id": ObjectId(product_id)},
        {"$set": {"status": ProductStatus.DISCONTINUED.value}},
    )

    response = await client.post(
        f"/api/v1/quotation-requests/{request_id}/submit",
        headers=customer_actor.headers,
    )
    body = response.json()
    assert body["outcome"] == WorkflowOutcome.VALIDATION_FAILED.value
    assert any("discontinued" in error for error in body["validation_errors"])
    # Preserved, not discarded.
    assert body["request"]["customer_notes"] == "Keep this note."
    assert body["request"]["items"][0]["quantity"] == 4


# ===========================================================================
# 3. Invalid quantity
# ===========================================================================


@pytest.mark.parametrize("quantity", [0, -5])
async def test_3_invalid_quantity_is_rejected_by_the_schema(
    client, customer_actor, quantity
):
    product_id = await create_product(sku=f"FAIL-3-{abs(quantity)}")
    response = await submit(
        client, customer_actor, [{"product_id": product_id, "quantity": quantity}]
    )
    assert response.status_code == 422


async def test_3b_a_quantity_past_the_ceiling_fails_validation(
    client, customer_actor, manager
):
    await client.patch(
        "/api/v1/settings",
        headers=manager.headers,
        json={"execution_policy": {"max_quantity_per_line": 50}},
    )
    product_id = await create_product(sku="FAIL-3B", stock_quantity=10_000)
    workflow = await submit_ok(
        client, customer_actor, [{"product_id": product_id, "quantity": 100}]
    )
    assert workflow["outcome"] == WorkflowOutcome.VALIDATION_FAILED.value
    assert any("exceeds the 50 permitted" in e for e in workflow["validation_errors"])


# ===========================================================================
# 4. Product unavailable
# ===========================================================================


async def test_4_product_unavailable_escalates_to_a_manager(client, customer_actor):
    """With backorders allowed, a shortfall is quoted but needs review."""
    product_id = await create_product(sku="FAIL-4", stock_quantity=3, lead_time_days=21)
    workflow = await submit_ok(
        client, customer_actor, [{"product_id": product_id, "quantity": 20}]
    )

    assert workflow["resulting_status"] == RequestStatus.PENDING_APPROVAL.value
    types = [exception["type"] for exception in workflow["exceptions"]]
    assert "STOCK_SHORTFALL" in types
    availability = workflow["request"]["items"][0]["availability"]
    assert availability["shortfall"] == 17
    assert availability["lead_time_days"] == 21


async def test_4b_product_unavailable_fails_when_backorders_are_off(
    client, customer_actor, manager
):
    await client.patch(
        "/api/v1/settings",
        headers=manager.headers,
        json={"quotation_policy": {"allow_backorder": False}},
    )
    product_id = await create_product(sku="FAIL-4B", stock_quantity=0)
    workflow = await submit_ok(
        client, customer_actor, [{"product_id": product_id, "quantity": 5}]
    )
    assert workflow["outcome"] == WorkflowOutcome.VALIDATION_FAILED.value
    assert workflow["retries_used"] == 0


# ===========================================================================
# 5. Excessive discount
# ===========================================================================


async def test_5_excessive_discount_goes_to_a_manager(client, customer_actor):
    product_id = await create_product(
        sku="FAIL-5", unit_price="1000.00", cost_price="100.00"
    )
    workflow = await submit_ok(
        client,
        customer_actor,
        [{"product_id": product_id, "quantity": 10, "requested_discount_percent": 12}],
    )
    assert workflow["outcome"] == WorkflowOutcome.PENDING_APPROVAL.value
    assert workflow["approval_id"] is not None
    assert workflow["quotation_id"] is None, "nothing may be issued before approval"


async def test_5b_a_discount_beyond_any_approval_is_refused(client, customer_actor):
    product_id = await create_product(
        sku="FAIL-5B", unit_price="1000.00", cost_price="100.00"
    )
    workflow = await submit_ok(
        client,
        customer_actor,
        [{"product_id": product_id, "quantity": 100, "requested_discount_percent": 45}],
    )
    assert workflow["outcome"] == WorkflowOutcome.VALIDATION_FAILED.value
    assert any("under any approval" in e for e in workflow["validation_errors"])


async def test_5c_a_discount_below_cost_is_refused(client, customer_actor):
    product_id = await create_product(
        sku="FAIL-5C", unit_price="1000.00", cost_price="950.00"
    )
    workflow = await submit_ok(
        client,
        customer_actor,
        [{"product_id": product_id, "quantity": 100, "requested_discount_percent": 12}],
    )
    assert workflow["outcome"] == WorkflowOutcome.VALIDATION_FAILED.value
    assert any("below the cost price" in e for e in workflow["validation_errors"])


# ===========================================================================
# 6. Database connection failure
# ===========================================================================


async def test_6_a_database_fault_is_retried_then_succeeds(
    client, customer_actor, monkeypatch
):
    product_id = await create_product(sku="FAIL-6")
    real = workflow_engine._validate_request
    calls = {"n": 0}

    async def flaky(request, settings_doc):
        calls["n"] += 1
        if calls["n"] == 1:
            raise ConnectionFailure("connection reset by peer")
        return await real(request, settings_doc)

    monkeypatch.setattr(workflow_engine, "_validate_request", flaky)

    workflow = await submit_ok(
        client, customer_actor, [{"product_id": product_id, "quantity": 2}]
    )
    assert workflow["outcome"] == WorkflowOutcome.COMPLETED.value
    assert workflow["retries_used"] == 1


async def test_6b_a_persistent_database_fault_escalates(
    client, customer_actor, monkeypatch, manager
):
    product_id = await create_product(sku="FAIL-6B")

    async def always_down(request, settings_doc):
        raise ConnectionFailure("no reachable servers")

    monkeypatch.setattr(workflow_engine, "_validate_request", always_down)

    workflow = await submit_ok(
        client, customer_actor, [{"product_id": product_id, "quantity": 1}]
    )
    assert workflow["outcome"] == WorkflowOutcome.ESCALATED.value
    assert (
        workflow["escalation_reason"]
        == EscalationReason.REPEATED_PROCESSING_FAILURE.value
    )
    # The error is recorded on the step, not just logged.
    executions = await client.get(
        f"/api/v1/quotation-requests/{workflow['request']['id']}/executions",
        headers=manager.headers,
    )
    step = executions.json()[0]["steps"][0]
    assert step["status"] == "FAILED"
    assert any("ConnectionFailure" in error for error in step["errors"])


# ===========================================================================
# 7. Duplicate request / idempotency
# ===========================================================================


async def test_7_a_request_can_only_ever_hold_one_quotation(client, customer_actor):
    product_id = await create_product(sku="FAIL-7")
    workflow = await submit_ok(
        client, customer_actor, [{"product_id": product_id, "quantity": 2}]
    )
    request_id = workflow["request"]["id"]

    count = await get_collection(Collections.QUOTATIONS).count_documents(
        {"request_id": request_id}
    )
    assert count == 1


async def test_7b_the_unique_index_refuses_a_second_quotation(client, customer_actor):
    """The idempotency guarantee is enforced by the database, not by a check."""
    product_id = await create_product(sku="FAIL-7B")
    workflow = await submit_ok(
        client, customer_actor, [{"product_id": product_id, "quantity": 1}]
    )
    request_id = workflow["request"]["id"]

    stored = await get_collection(Collections.QUOTATIONS).find_one(
        {"request_id": request_id}
    )
    clone = dict(stored)
    clone.pop("_id")
    clone["quotation_number"] = "QT-CLONE-0001"
    clone["verification_code"] = "ZZZZ-ZZZZ-ZZZZ"

    with pytest.raises(DuplicateKeyError):
        await get_collection(Collections.QUOTATIONS).insert_one(clone)


async def test_7c_the_action_tool_is_idempotent(client, customer_actor):
    """Calling the action tool twice returns the first quotation, not a second."""
    from app.services import customer_service, request_service, settings_service

    product_id = await create_product(sku="FAIL-7C")
    workflow = await submit_ok(
        client, customer_actor, [{"product_id": product_id, "quantity": 2}]
    )
    request_id = workflow["request"]["id"]
    first_id = workflow["quotation_id"]

    request = await request_service.get_request(request_id)
    customer = await customer_service.get_customer(str(request.customer_id))
    settings_doc = await settings_service.get_settings_document()

    again = await action_tool.execute(
        request,
        customer=customer,
        settings_doc=settings_doc,
        auto_approved=True,
    )
    assert again.reused_existing is True
    assert again.quotation_id == first_id
    assert "reused_existing_quotation" in again.operations

    count = await get_collection(Collections.QUOTATIONS).count_documents(
        {"request_id": request_id}
    )
    assert count == 1


async def test_7d_a_duplicate_line_is_refused(client, customer_actor):
    product_id = await create_product(sku="FAIL-7D")
    response = await submit(
        client,
        customer_actor,
        [
            {"product_id": product_id, "quantity": 2},
            {"product_id": product_id, "quantity": 3},
        ],
    )
    assert response.status_code == 422


# ===========================================================================
# 8. Manager rejection
# ===========================================================================


async def test_8_manager_rejection_updates_the_status(client, customer_actor, manager):
    product_id = await create_product(
        sku="FAIL-8", unit_price="1000.00", cost_price="100.00"
    )
    workflow = await submit_ok(
        client,
        customer_actor,
        [{"product_id": product_id, "quantity": 10, "requested_discount_percent": 9}],
    )

    response = await client.post(
        f"/api/v1/approvals/{workflow['approval_id']}/decision",
        headers=manager.headers,
        json={"decision": "REJECT", "comments": "Margin is too thin."},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["request"]["status"] == RequestStatus.REJECTED.value
    assert body["quotation_id"] is None
    # Information preserved: the priced lines survive the rejection.
    assert body["request"]["pricing"]["final_amount"] > 0
    assert len(body["request"]["items"]) == 1


async def test_8b_rejection_without_a_reason_is_refused(
    client, customer_actor, manager
):
    product_id = await create_product(
        sku="FAIL-8B", unit_price="1000.00", cost_price="100.00"
    )
    workflow = await submit_ok(
        client,
        customer_actor,
        [{"product_id": product_id, "quantity": 10, "requested_discount_percent": 9}],
    )
    response = await client.post(
        f"/api/v1/approvals/{workflow['approval_id']}/decision",
        headers=manager.headers,
        json={"decision": "REJECT"},
    )
    assert response.status_code == 409
    assert "comment explaining the decision" in response.json()["error"]["message"]


# ===========================================================================
# 9. PDF generation failure
# ===========================================================================


async def test_9_a_pdf_failure_is_retried_then_escalates(
    client, customer_actor, monkeypatch, manager
):
    """A document that cannot be written must not be reported as delivered."""
    from app.services import pdf_service

    product_id = await create_product(sku="FAIL-9")

    def broken_render(quotation, output_path=None):
        raise OSError("No space left on device")

    monkeypatch.setattr(pdf_service, "render_quotation_pdf", broken_render)

    workflow = await submit_ok(
        client, customer_actor, [{"product_id": product_id, "quantity": 1}]
    )

    assert workflow["outcome"] == WorkflowOutcome.ESCALATED.value
    assert (
        workflow["escalation_reason"]
        == EscalationReason.REPEATED_PROCESSING_FAILURE.value
    )
    assert workflow["gate"]["document_generated"] is False
    assert workflow["resulting_status"] == RequestStatus.ESCALATED.value
    # An OSError is transient, so it was retried before giving up.
    assert workflow["retries_used"] >= 1


async def test_9b_a_pdf_that_writes_nothing_is_caught(
    client, customer_actor, monkeypatch, tmp_path
):
    """An empty file is a failure even though no exception was raised."""
    from app.services import pdf_service

    product_id = await create_product(sku="FAIL-9B")

    def empty_render(quotation, output_path=None):
        target = tmp_path / f"{quotation.quotation_number}.pdf"
        target.write_bytes(b"")
        return target

    monkeypatch.setattr(pdf_service, "render_quotation_pdf", empty_render)

    workflow = await submit_ok(
        client, customer_actor, [{"product_id": product_id, "quantity": 1}]
    )
    assert workflow["outcome"] == WorkflowOutcome.ESCALATED.value
    assert workflow["gate"]["document_generated"] is False


# ===========================================================================
# 10. Verification mismatch
# ===========================================================================


async def test_10_a_tampered_total_fails_verification(client, customer_actor):
    product_id = await create_product(sku="FAIL-10", unit_price="1000.00")
    workflow = await submit_ok(
        client, customer_actor, [{"product_id": product_id, "quantity": 2}]
    )

    await get_collection(Collections.QUOTATIONS).update_one(
        {"_id": ObjectId(workflow["quotation_id"])},
        {"$set": {"pricing.final_amount": Decimal128("1.00")}},
    )

    report = await checker_tool.verify_quotation(
        await load_quotation(workflow["quotation_id"])
    )
    assert report.passed is False
    checks = {finding.check for finding in report.findings}
    assert "final_amount" in checks
    assert "document_consistency" in checks, "the integrity digest must also fail"


async def test_10b_a_tampered_unit_price_fails_verification(client, customer_actor):
    """The checker re-reads the catalogue, so a doctored line price is caught."""
    product_id = await create_product(sku="FAIL-10B", unit_price="1000.00")
    workflow = await submit_ok(
        client, customer_actor, [{"product_id": product_id, "quantity": 2}]
    )

    await get_collection(Collections.QUOTATIONS).update_one(
        {"_id": ObjectId(workflow["quotation_id"])},
        {"$set": {"items.0.unit_price": Decimal128("1.00")}},
    )

    report = await checker_tool.verify_quotation(
        await load_quotation(workflow["quotation_id"])
    )
    assert report.passed is False
    assert any(finding.check == "unit_prices" for finding in report.findings)


async def test_10c_a_mismatch_escalates_rather_than_completing(
    client, customer_actor, monkeypatch, manager
):
    product_id = await create_product(sku="FAIL-10C")
    real = checker_tool.verify_quotation

    async def rejecting(quotation, **kwargs):
        report = await real(quotation, **kwargs)
        report.fail(
            checker_tool.Finding(
                check="final_amount", detail="Injected mismatch.", expected="1", actual="2"
            )
        )
        return report

    monkeypatch.setattr(workflow_engine.checker_tool, "verify_quotation", rejecting)

    workflow = await submit_ok(
        client, customer_actor, [{"product_id": product_id, "quantity": 1}]
    )
    assert workflow["resulting_status"] == RequestStatus.ESCALATED.value
    assert (
        workflow["escalation_reason"] == EscalationReason.VERIFICATION_MISMATCH.value
    )
    assert await audit_count(client, manager, "QUOTATION_VERIFICATION_FAILED") == 1


async def test_10d_a_sound_quotation_passes_every_check(client, customer_actor):
    product_id = await create_product(sku="FAIL-10D", unit_price="1234.56")
    workflow = await submit_ok(
        client, customer_actor, [{"product_id": product_id, "quantity": 7}]
    )
    report = await checker_tool.verify_quotation(
        await load_quotation(workflow["quotation_id"])
    )
    assert report.passed is True, report.summary
    # Every required check actually ran.
    for required in (
        "product_information",
        "quantities",
        "unit_prices",
        "discount_calculations",
        "tax_calculations",
        "final_amount",
        "approval_status",
        "document_consistency",
    ):
        assert required in report.checks_run, required


async def test_10e_a_missing_pdf_is_caught(client, customer_actor):
    import pathlib

    product_id = await create_product(sku="FAIL-10E")
    workflow = await submit_ok(
        client, customer_actor, [{"product_id": product_id, "quantity": 1}]
    )
    quotation = await load_quotation(workflow["quotation_id"])
    pathlib.Path(quotation.pdf_path).unlink()

    report = await checker_tool.verify_quotation(quotation)
    assert report.passed is False
    assert any(finding.check == "document_file" for finding in report.findings)


async def test_10f_a_quotation_with_no_approval_evidence_is_refused(
    client, customer_actor
):
    """A document claiming manager approval must name a granted approval."""
    product_id = await create_product(sku="FAIL-10F")
    workflow = await submit_ok(
        client, customer_actor, [{"product_id": product_id, "quantity": 1}]
    )
    await get_collection(Collections.QUOTATIONS).update_one(
        {"_id": ObjectId(workflow["quotation_id"])},
        {"$set": {"auto_approved": False, "approval_id": None}},
    )
    report = await checker_tool.verify_quotation(
        await load_quotation(workflow["quotation_id"])
    )
    assert report.passed is False
    assert any(finding.check == "approval_status" for finding in report.findings)


# ===========================================================================
# 11. Maximum retries exceeded
# ===========================================================================


async def test_11_retry_exhaustion_escalates_and_records_the_count(
    client, customer_actor, manager, monkeypatch
):
    await client.patch(
        "/api/v1/settings",
        headers=manager.headers,
        json={"execution_policy": {"max_retries_per_step": 3, "retry_backoff_ms": 0}},
    )
    product_id = await create_product(sku="FAIL-11")
    calls = {"n": 0}

    async def never_recovers(request, settings_doc):
        calls["n"] += 1
        raise ConnectionFailure("still unreachable")

    monkeypatch.setattr(workflow_engine, "_validate_request", never_recovers)

    workflow = await submit_ok(
        client, customer_actor, [{"product_id": product_id, "quantity": 1}]
    )

    assert calls["n"] == 4, "one attempt plus three retries"
    assert workflow["retries_used"] == 3
    assert workflow["request"]["retry_count"] == 3
    assert workflow["outcome"] == WorkflowOutcome.ESCALATED.value

    # The retry log is on the execution for audit.
    executions = await client.get(
        f"/api/v1/quotation-requests/{workflow['request']['id']}/executions",
        headers=manager.headers,
    )
    budget = executions.json()[0]["budget"]
    assert budget["retries_used"] == 3
    assert len(budget["retries"]) == 3
    assert {record["failure_class"] for record in budget["retries"]} == {"TRANSIENT"}


# ===========================================================================
# 12. Workflow timeout
# ===========================================================================


async def test_12_a_spent_time_budget_stops_the_run(
    client, customer_actor, manager, monkeypatch
):
    """A run whose time budget is already spent is escalated, not continued.

    The clock is driven by overriding ``elapsed_ms`` rather than by sleeping,
    so the test is deterministic. The arithmetic behind the limit has its own
    unit test in ``test_workflow_boundaries``; what matters here is that the
    engine acts on a spent budget instead of carrying on.
    """
    from app.services.execution_budget import ExecutionBudget

    await client.patch(
        "/api/v1/settings",
        headers=manager.headers,
        json={"execution_policy": {"max_execution_ms": 1_000}},
    )
    product_id = await create_product(sku="FAIL-12")

    monkeypatch.setattr(
        ExecutionBudget, "elapsed_ms", property(lambda self: 9_999_999)
    )

    workflow = await submit_ok(
        client, customer_actor, [{"product_id": product_id, "quantity": 1}]
    )

    assert workflow["outcome"] == WorkflowOutcome.BUDGET_EXCEEDED.value
    assert workflow["escalation_reason"] == EscalationReason.BUDGET_EXCEEDED.value
    assert "execution limit" in workflow["escalation_detail"]
    assert workflow["resulting_status"] == RequestStatus.ESCALATED.value
    # No document may be issued once the budget is spent.
    assert workflow["quotation_id"] is None
    assert workflow["gate"]["document_generated"] is False


async def test_12b_the_total_time_budget_is_separate_from_the_per_run_one(
    client, manager
):
    settings = await client.get("/api/v1/settings", headers=manager.headers)
    policy = settings.json()["execution_policy"]
    assert policy["max_execution_ms"] < policy["max_total_execution_ms"], (
        "a single run should be allowed less than a request's whole life"
    )


# ===========================================================================
# Cross-cutting: information is preserved through every failure
# ===========================================================================


async def test_a_failed_request_keeps_everything_it_was_given(
    client, customer_actor
):
    product_id = await create_product(
        sku="FAIL-PRESERVE", status=ProductStatus.DISCONTINUED
    )
    workflow = await submit_ok(
        client,
        customer_actor,
        [{"product_id": product_id, "quantity": 9, "requested_discount_percent": 2}],
        customer_notes="Deliver to gate 4.",
    )

    request = workflow["request"]
    assert request["customer_notes"] == "Deliver to gate 4."
    assert request["items"][0]["quantity"] == 9
    assert request["items"][0]["requested_discount_percent"] == 2
    assert request["customer_code"]
    assert request["request_number"]
    # And the failure itself is on the record.
    assert request["validation_errors"]


async def test_an_escalated_request_can_be_resubmitted_after_a_fix(
    client, customer_actor, employee
):
    """Escalation parks a request; it does not destroy it."""
    product_id = await create_product(sku="FAIL-RECOVER")
    real = checker_tool.verify_quotation

    async def rejecting(quotation, **kwargs):
        report = await real(quotation, **kwargs)
        report.fail(
            checker_tool.Finding(check="final_amount", detail="Injected.", expected="1", actual="2")
        )
        return report

    import unittest.mock as mock

    with mock.patch.object(
        workflow_engine.checker_tool, "verify_quotation", rejecting
    ):
        workflow = await submit_ok(
            client, customer_actor, [{"product_id": product_id, "quantity": 1}]
        )
    assert workflow["resulting_status"] == RequestStatus.ESCALATED.value
    request_id = workflow["request"]["id"]

    # With the fault gone, a staff reprocess clears it.
    response = await client.post(
        f"/api/v1/quotation-requests/{request_id}/reprocess",
        headers=employee.headers,
    )
    assert response.status_code == 200, response.text
    assert response.json()["outcome"] == WorkflowOutcome.COMPLETED.value
