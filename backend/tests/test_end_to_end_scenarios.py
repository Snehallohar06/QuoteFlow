"""The end-to-end scenarios, written as the brief states them.

Each test walks one whole journey through the real API and asserts every stage
the brief names, rather than only the final status. These double as the script
for the live demonstration: the five classes below are demo scenarios 1 to 5.
"""

import pytest
from bson import ObjectId
from pymongo.errors import ConnectionFailure

from app.db.mongo import Collections, get_collection
from app.models.enums import (
    EscalationReason,
    ProductStatus,
    RequestStatus,
    StepStatus,
    UserRole,
    WorkflowOutcome,
    WorkflowStep,
)
from app.services import checker_tool, workflow_engine
from tests.conftest import Actor, _login, create_customer, create_product, create_user

pytestmark = pytest.mark.workflow


async def submit(client, actor, items, **extra):
    response = await client.post(
        "/api/v1/quotation-requests",
        headers=actor.headers,
        json={"items": items, "submit": True, **extra},
    )
    assert response.status_code == 201, response.text
    return response.json()["workflow"]


def step_of(execution: dict, step: WorkflowStep) -> dict:
    found = next(
        (row for row in execution["steps"] if row["step"] == step.value), None
    )
    assert found is not None, f"{step.value} was not recorded"
    return found


# ===========================================================================
# SCENARIO 1 / TEST 1: a successful quotation
# ===========================================================================


class TestScenario1SuccessfulQuotation:
    """A customer submits a valid request and receives a verified quotation."""

    async def test_the_whole_journey(self, client, customer_actor, manager):
        product_id = await create_product(
            sku="E2E-1", name="Gate Valve 80 mm", unit_price="4250.00", stock_quantity=500
        )

        # -- submit a valid request ---------------------------------------
        workflow = await submit(
            client,
            customer_actor,
            [{"product_id": product_id, "quantity": 25, "requested_discount_percent": 10}],
            customer_notes="Annual maintenance stock.",
        )
        request_id = workflow["request"]["id"]

        # -- a unique request id was generated ----------------------------
        assert workflow["request"]["request_number"].startswith("QR-")

        executions = await client.get(
            f"/api/v1/quotation-requests/{request_id}/executions",
            headers=customer_actor.headers,
        )
        execution = executions.json()[0]

        # -- every pipeline stage ran and succeeded -----------------------
        for step in WORKFLOW_STAGES:
            assert step_of(execution, step)["status"] == StepStatus.SUCCESS.value, (
                f"{step.value} did not succeed"
            )

        # -- product verification -----------------------------------------
        availability = step_of(execution, WorkflowStep.CHECK_AVAILABILITY)
        assert availability["output"]["shortfall_lines"] == []

        # -- price calculation, with figures that reconcile ---------------
        pricing = workflow["request"]["pricing"]
        assert pricing["subtotal"] == 106250.0           # 25 x 4250
        assert pricing["total_discount"] == 10625.0      # 10%
        assert pricing["taxable_amount"] == 95625.0
        assert pricing["total_tax"] == 17212.5           # 18%
        assert pricing["final_amount"] == 112837.5
        assert (
            pricing["taxable_amount"]
            == pricing["subtotal"] - pricing["total_discount"]
        )
        assert (
            pricing["final_amount"]
            == pricing["taxable_amount"] + pricing["total_tax"]
        )

        # -- the required approval is recorded (policy authorised it) -----
        assert workflow["gate"]["approval_recorded"] is True
        assert workflow["approval_id"] is None, "within policy, so no manager needed"

        # -- the PDF was generated ----------------------------------------
        assert workflow["gate"]["document_generated"] is True
        quotation_id = workflow["quotation_id"]
        pdf = await client.get(
            f"/api/v1/quotations/{quotation_id}/pdf", headers=customer_actor.headers
        )
        assert pdf.status_code == 200
        assert pdf.content.startswith(b"%PDF-")

        # -- independent verification passed ------------------------------
        assert workflow["gate"]["independent_verification_passed"] is True
        assert workflow["check_report"]["passed"] is True
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
            assert required in workflow["check_report"]["checks_run"]

        # -- the request is COMPLETED -------------------------------------
        assert workflow["outcome"] == WorkflowOutcome.COMPLETED.value
        assert workflow["resulting_status"] == RequestStatus.COMPLETED.value
        assert all(workflow["gate"].values())
        assert workflow["request"]["completed_at"] is not None

        # -- and the customer can verify the document independently -------
        quotation = await client.get(
            f"/api/v1/quotations/{quotation_id}", headers=customer_actor.headers
        )
        code = quotation.json()["verification_code"]
        verified = await client.get(f"/api/v1/verify/{code}")
        assert verified.json()["valid"] is True
        assert verified.json()["final_amount"] == 112837.5


WORKFLOW_STAGES = (
    WorkflowStep.VALIDATE_REQUEST,
    WorkflowStep.CHECK_AVAILABILITY,
    WorkflowStep.CALCULATE_PRICING,
    WorkflowStep.EVALUATE_DISCOUNT_RULES,
    WorkflowStep.DETERMINE_APPROVAL_ROUTE,
    WorkflowStep.GENERATE_DOCUMENT,
    WorkflowStep.VERIFY_DOCUMENT,
    WorkflowStep.FINALISE,
)


# ===========================================================================
# SCENARIO 2 / TEST 2: invalid input
# ===========================================================================


class TestScenario2InvalidInput:
    """Invalid information is detected, recorded, and stops the processing."""

    async def test_a_discontinued_product_stops_the_workflow(
        self, client, customer_actor, manager
    ):
        product_id = await create_product(
            sku="E2E-2", status=ProductStatus.DISCONTINUED
        )
        workflow = await submit(
            client,
            customer_actor,
            [{"product_id": product_id, "quantity": 5}],
            customer_notes="Keep this.",
        )

        # -- validation failure detected ----------------------------------
        assert workflow["outcome"] == WorkflowOutcome.VALIDATION_FAILED.value
        assert workflow["resulting_status"] == RequestStatus.VALIDATION_FAILED.value
        assert any("discontinued" in e for e in workflow["validation_errors"])

        # -- further processing prevented ---------------------------------
        assert workflow["request"]["pricing"] is None
        assert workflow["quotation_id"] is None
        assert workflow["gate"]["pricing_validation_passed"] is False
        assert workflow["gate"]["document_generated"] is False

        executions = await client.get(
            f"/api/v1/quotation-requests/{workflow['request']['id']}/executions",
            headers=manager.headers,
        )
        execution = executions.json()[0]
        assert (
            step_of(execution, WorkflowStep.VALIDATE_REQUEST)["status"]
            == StepStatus.FAILED.value
        )
        for later in (
            WorkflowStep.CHECK_AVAILABILITY,
            WorkflowStep.CALCULATE_PRICING,
            WorkflowStep.EVALUATE_DISCOUNT_RULES,
            WorkflowStep.DETERMINE_APPROVAL_ROUTE,
            WorkflowStep.GENERATE_DOCUMENT,
            WorkflowStep.VERIFY_DOCUMENT,
        ):
            assert step_of(execution, later)["status"] == StepStatus.SKIPPED.value

        # -- the error is recorded, and what was submitted is preserved ----
        assert step_of(execution, WorkflowStep.VALIDATE_REQUEST)["errors"]
        assert workflow["request"]["customer_notes"] == "Keep this."
        assert workflow["request"]["items"][0]["quantity"] == 5

        # -- no quotation exists at all ------------------------------------
        count = await get_collection(Collections.QUOTATIONS).count_documents(
            {"request_id": workflow["request"]["id"]}
        )
        assert count == 0

    async def test_missing_customer_information_is_detected(self, client):
        customer_id = await create_customer(
            code="E2E-NOCUST", email="e2e-nocust@test.example"
        )
        await get_collection(Collections.CUSTOMERS).update_one(
            {"_id": ObjectId(customer_id)}, {"$set": {"phone": ""}}
        )
        user = await create_user(
            email="e2e-nocust.buyer@test.example",
            role=UserRole.CUSTOMER,
            customer_id=customer_id,
        )
        actor = Actor(user["id"], user["email"], await _login(client, user["email"]))
        product_id = await create_product(sku="E2E-2B")

        workflow = await submit(
            client, actor, [{"product_id": product_id, "quantity": 1}]
        )
        assert workflow["outcome"] == WorkflowOutcome.VALIDATION_FAILED.value
        assert any("telephone number" in e for e in workflow["validation_errors"])

    async def test_a_malformed_payload_never_reaches_the_workflow(
        self, client, customer_actor
    ):
        product_id = await create_product(sku="E2E-2C")
        response = await client.post(
            "/api/v1/quotation-requests",
            headers=customer_actor.headers,
            json={"items": [{"product_id": product_id, "quantity": 0}], "submit": True},
        )
        assert response.status_code == 422
        assert (
            await get_collection(Collections.QUOTATION_REQUESTS).count_documents({})
            == 0
        ), "a rejected payload must not create a request"


# ===========================================================================
# SCENARIO 3 / TEST 3: excessive discount
# ===========================================================================


class TestScenario3ExcessiveDiscount:
    """A discount beyond policy is escalated, and cannot be finalised."""

    async def test_the_request_is_sent_to_a_manager(self, client, customer_actor):
        product_id = await create_product(
            sku="E2E-3", unit_price="48500.00", cost_price="36000.00"
        )

        # 8 units sits in the 6-20 band: 5% allowed, plus 0% for STANDARD tier.
        workflow = await submit(
            client,
            customer_actor,
            [{"product_id": product_id, "quantity": 8, "requested_discount_percent": 12}],
        )

        # -- the exception is identified -----------------------------------
        assert workflow["outcome"] == WorkflowOutcome.PENDING_APPROVAL.value
        assert workflow["resulting_status"] == RequestStatus.PENDING_APPROVAL.value
        exception = workflow["exceptions"][0]
        assert exception["type"] == "DISCOUNT_LIMIT_EXCEEDED"
        assert exception["context"]["requested_percent"] == 12.0
        assert exception["context"]["max_allowed_percent"] == 5.0

        # -- the request is sent to a manager ------------------------------
        assert workflow["approval_id"] is not None
        line = workflow["request"]["items"][0]
        assert line["discount_exception"] is True
        # The manager sees the discount that was actually asked for.
        assert line["applied_discount_percent"] == 12.0

        # -- unauthorised finalisation is prevented -----------------------
        assert workflow["quotation_id"] is None
        assert workflow["gate"]["approval_recorded"] is False
        assert workflow["gate"]["document_generated"] is False
        assert workflow["gate"]["independent_verification_passed"] is False
        count = await get_collection(Collections.QUOTATIONS).count_documents(
            {"request_id": workflow["request"]["id"]}
        )
        assert count == 0

        # -- and the document steps were not even attempted ---------------
        executions = await client.get(
            f"/api/v1/quotation-requests/{workflow['request']['id']}/executions",
            headers=customer_actor.headers,
        )
        execution = executions.json()[0]
        assert (
            step_of(execution, WorkflowStep.GENERATE_DOCUMENT)["status"]
            == StepStatus.SKIPPED.value
        )

    async def test_a_manager_approval_then_completes_it(
        self, client, customer_actor, manager
    ):
        product_id = await create_product(
            sku="E2E-3B", unit_price="1000.00", cost_price="100.00"
        )
        workflow = await submit(
            client,
            customer_actor,
            [{"product_id": product_id, "quantity": 10, "requested_discount_percent": 9}],
        )

        decision = await client.post(
            f"/api/v1/approvals/{workflow['approval_id']}/decision",
            headers=manager.headers,
            json={"decision": "APPROVE", "comments": "Strategic account."},
        )
        assert decision.status_code == 200
        body = decision.json()

        assert body["request"]["status"] == RequestStatus.COMPLETED.value
        assert body["quotation_id"] is not None

        quotation = await client.get(
            f"/api/v1/quotations/{body['quotation_id']}", headers=manager.headers
        )
        detail = quotation.json()
        assert detail["auto_approved"] is False, "a person authorised this"
        assert detail["approved_by_name"] == "Test Manager"
        assert detail["items"][0]["applied_discount_percent"] == 9.0

    async def test_an_override_reprices_the_document(
        self, client, customer_actor, manager
    ):
        product_id = await create_product(
            sku="E2E-3C", unit_price="1000.00", cost_price="100.00"
        )
        workflow = await submit(
            client,
            customer_actor,
            [{"product_id": product_id, "quantity": 10, "requested_discount_percent": 20}],
        )
        decision = await client.post(
            f"/api/v1/approvals/{workflow['approval_id']}/decision",
            headers=manager.headers,
            json={
                "decision": "APPROVE",
                "override_discount_percent": 6,
                "comments": "6% is my limit.",
            },
        )
        body = decision.json()
        assert body["request"]["items"][0]["applied_discount_percent"] == 6.0
        # 10 x 1000 = 10000, less 6% = 9400, plus 18% = 11092
        assert body["request"]["pricing"]["final_amount"] == 11092.0
        assert body["request"]["status"] == RequestStatus.COMPLETED.value


# ===========================================================================
# SCENARIO 4: manager rejection
# ===========================================================================


class TestScenario4ManagerRejection:
    """A rejection closes the request and issues nothing."""

    async def test_rejection_updates_the_status_appropriately(
        self, client, customer_actor, manager
    ):
        product_id = await create_product(
            sku="E2E-4", unit_price="1000.00", cost_price="100.00"
        )
        workflow = await submit(
            client,
            customer_actor,
            [{"product_id": product_id, "quantity": 10, "requested_discount_percent": 9}],
        )

        decision = await client.post(
            f"/api/v1/approvals/{workflow['approval_id']}/decision",
            headers=manager.headers,
            json={
                "decision": "REJECT",
                "comments": "The margin is too thin at this discount.",
            },
        )
        assert decision.status_code == 200
        body = decision.json()

        assert body["approval"]["status"] == "REJECTED"
        assert body["approval"]["decided_by_name"] == "Test Manager"
        assert body["request"]["status"] == RequestStatus.REJECTED.value
        assert body["quotation_id"] is None

        # Nothing was issued.
        count = await get_collection(Collections.QUOTATIONS).count_documents(
            {"request_id": workflow["request"]["id"]}
        )
        assert count == 0

        # The customer is told, with the manager's reason.
        inbox = await client.get(
            "/api/v1/notifications", headers=customer_actor.headers
        )
        rejection = next(
            item
            for item in inbox.json()["items"]
            if item["type"] == "REQUEST_REJECTED"
        )
        assert "margin is too thin" in rejection["message"].lower()

        # The decision is on the audit trail.
        audit = await client.get(
            "/api/v1/audit-logs",
            headers=manager.headers,
            params={"action": "APPROVAL_DECIDED"},
        )
        entry = audit.json()["items"][0]
        assert entry["metadata"]["decision"] == "REJECT"
        assert entry["actor_email"] == manager.email

        # And the request is settled: re-running does nothing.
        result = await workflow_engine.execute(
            workflow["request"]["id"], trigger="REPROCESS"
        )
        assert result.outcome is WorkflowOutcome.NO_OP

    async def test_a_modification_request_returns_it_to_the_customer(
        self, client, customer_actor, manager
    ):
        product_id = await create_product(
            sku="E2E-4B", unit_price="1000.00", cost_price="100.00"
        )
        workflow = await submit(
            client,
            customer_actor,
            [{"product_id": product_id, "quantity": 10, "requested_discount_percent": 9}],
        )
        await client.post(
            f"/api/v1/approvals/{workflow['approval_id']}/decision",
            headers=manager.headers,
            json={
                "decision": "REQUEST_MODIFICATION",
                "comments": "Reduce the discount to 5% and resubmit.",
            },
        )

        request_id = workflow["request"]["id"]
        detail = await client.get(
            f"/api/v1/quotation-requests/{request_id}",
            headers=customer_actor.headers,
        )
        assert detail.json()["status"] == RequestStatus.MODIFICATION_REQUESTED.value

        # The customer complies and resubmits.
        await client.patch(
            f"/api/v1/quotation-requests/{request_id}",
            headers=customer_actor.headers,
            json={
                "items": [
                    {
                        "product_id": product_id,
                        "quantity": 10,
                        "requested_discount_percent": 5,
                    }
                ]
            },
        )
        resubmitted = await client.post(
            f"/api/v1/quotation-requests/{request_id}/submit",
            headers=customer_actor.headers,
        )
        body = resubmitted.json()
        assert body["resulting_status"] == RequestStatus.COMPLETED.value
        assert body["request"]["revision"] == 1
        # The stale approval must not be treated as authorisation.
        quotation = await client.get(
            f"/api/v1/quotations/{body['quotation_id']}", headers=manager.headers
        )
        assert quotation.json()["auto_approved"] is True


# ===========================================================================
# SCENARIO 5: a temporary failure, handled within the retry limits
# ===========================================================================


class TestScenario5TemporaryFailure:
    """A transient fault is retried inside the configured budget."""

    async def test_a_transient_fault_recovers_within_the_limit(
        self, client, customer_actor, manager, monkeypatch
    ):
        await client.patch(
            "/api/v1/settings",
            headers=manager.headers,
            json={
                "execution_policy": {
                    "max_retries_per_step": 3,
                    "retry_backoff_ms": 0,
                }
            },
        )
        product_id = await create_product(sku="E2E-5", unit_price="1000.00")
        real = workflow_engine._validate_request
        attempts = {"n": 0}

        async def flaky(request, settings_doc):
            attempts["n"] += 1
            if attempts["n"] <= 2:
                raise ConnectionFailure("transient: primary stepping down")
            return await real(request, settings_doc)

        monkeypatch.setattr(workflow_engine, "_validate_request", flaky)

        workflow = await submit(
            client, customer_actor, [{"product_id": product_id, "quantity": 3}]
        )

        # -- it recovered, inside the limit -------------------------------
        assert attempts["n"] == 3
        assert workflow["retries_used"] == 2
        assert workflow["retries_used"] < 3, "stayed within the configured maximum"
        assert workflow["outcome"] == WorkflowOutcome.COMPLETED.value

        # -- the retries are recorded for audit ---------------------------
        executions = await client.get(
            f"/api/v1/quotation-requests/{workflow['request']['id']}/executions",
            headers=manager.headers,
        )
        execution = executions.json()[0]
        assert execution["retries_used"] == 2
        assert len(execution["budget"]["retries"]) == 2
        assert all(
            record["failure_class"] == "TRANSIENT"
            for record in execution["budget"]["retries"]
        )
        assert step_of(execution, WorkflowStep.VALIDATE_REQUEST)["retries"] == 2
        assert workflow["request"]["retry_count"] == 2

    async def test_a_fault_that_never_clears_stops_at_the_limit(
        self, client, customer_actor, manager, monkeypatch
    ):
        await client.patch(
            "/api/v1/settings",
            headers=manager.headers,
            json={
                "execution_policy": {
                    "max_retries_per_step": 3,
                    "retry_backoff_ms": 0,
                }
            },
        )
        product_id = await create_product(sku="E2E-5B")
        attempts = {"n": 0}

        async def never_recovers(request, settings_doc):
            attempts["n"] += 1
            raise ConnectionFailure("transient: still unreachable")

        monkeypatch.setattr(workflow_engine, "_validate_request", never_recovers)

        workflow = await submit(
            client, customer_actor, [{"product_id": product_id, "quantity": 1}]
        )

        # -- stopped exactly at the limit, did not loop -------------------
        assert attempts["n"] == 4, "one attempt plus three retries"
        assert workflow["retries_used"] == 3

        # -- escalated rather than failing silently or looping ------------
        assert workflow["outcome"] == WorkflowOutcome.ESCALATED.value
        assert workflow["resulting_status"] == RequestStatus.ESCALATED.value
        assert (
            workflow["escalation_reason"]
            == EscalationReason.REPEATED_PROCESSING_FAILURE.value
        )

        # -- a manager is told --------------------------------------------
        inbox = await client.get("/api/v1/notifications", headers=manager.headers)
        assert any(
            item["type"] == "WORKFLOW_ESCALATED" for item in inbox.json()["items"]
        )

    async def test_a_document_fault_escalates_without_issuing_anything(
        self, client, customer_actor, monkeypatch
    ):
        """A PDF that cannot be written must not be reported as delivered."""
        from app.services import pdf_service

        product_id = await create_product(sku="E2E-5C")

        def broken(quotation, output_path=None):
            raise OSError("No space left on device")

        monkeypatch.setattr(pdf_service, "render_quotation_pdf", broken)

        workflow = await submit(
            client, customer_actor, [{"product_id": product_id, "quantity": 1}]
        )
        assert workflow["outcome"] == WorkflowOutcome.ESCALATED.value
        assert workflow["gate"]["document_generated"] is False
        assert workflow["resulting_status"] != RequestStatus.COMPLETED.value

    async def test_a_verification_mismatch_withholds_the_document(
        self, client, customer_actor, monkeypatch
    ):
        product_id = await create_product(sku="E2E-5D")
        real = checker_tool.verify_quotation

        async def rejecting(quotation, **kwargs):
            report = await real(quotation, **kwargs)
            report.fail(
                checker_tool.Finding(
                    check="final_amount",
                    detail="Independent recalculation disagreed.",
                    expected="100.00",
                    actual="1.00",
                )
            )
            return report

        monkeypatch.setattr(
            workflow_engine.checker_tool, "verify_quotation", rejecting
        )

        workflow = await submit(
            client, customer_actor, [{"product_id": product_id, "quantity": 1}]
        )
        assert workflow["resulting_status"] == RequestStatus.ESCALATED.value
        assert (
            workflow["escalation_reason"]
            == EscalationReason.VERIFICATION_MISMATCH.value
        )
        assert workflow["request"]["completed_at"] is None
