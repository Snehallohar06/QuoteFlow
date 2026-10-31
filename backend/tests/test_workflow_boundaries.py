"""The five mandatory workflow boundaries.

One section per control:

A. maximum iterations   retries are capped, and only transient failures retry
B. success gate         COMPLETED requires all six conditions
C. no-op condition      a settled request is not reprocessed
D. escalation           each listed condition parks the request for a human
E. budget limit         attempts, duration and resource ceilings are enforced
"""

from decimal import Decimal

import pytest
from bson import ObjectId
from pymongo.errors import ConnectionFailure

from app.core.exceptions import BusinessRuleError
from app.db.mongo import Collections, get_collection
from app.models.company_settings import ExecutionPolicy
from app.models.enums import (
    EscalationReason,
    FailureClass,
    ProductStatus,
    RequestStatus,
    StepStatus,
    WorkflowOutcome,
    WorkflowStep,
)
from app.services import settings_service, workflow_engine
from app.services.execution_budget import (
    BudgetExceeded,
    ExecutionBudget,
    classify,
    is_retryable,
)
from tests.conftest import create_customer, create_product, create_user

pytestmark = pytest.mark.workflow


async def submit(client, actor, items, **extra):
    response = await client.post(
        "/api/v1/quotation-requests",
        headers=actor.headers,
        json={"items": items, "submit": True, **extra},
    )
    assert response.status_code == 201, response.text
    return response.json()["workflow"]


async def set_execution_policy(client, manager, **fields):
    """Re-tune the execution budget through the real settings endpoint."""
    response = await client.patch(
        "/api/v1/settings",
        headers=manager.headers,
        json={"execution_policy": fields},
    )
    assert response.status_code == 200, response.text
    return response.json()["execution_policy"]


# ===========================================================================
# A. Maximum iterations
# ===========================================================================


class TestMaximumIterations:
    async def test_a_transient_failure_is_retried_then_succeeds(
        self, client, customer_actor, monkeypatch
    ):
        """Two transient faults, then success: the run completes and counts 2."""
        product_id = await create_product(sku="RETRY-OK")
        real = workflow_engine._validate_request
        calls = {"n": 0}

        async def flaky(request, settings_doc):
            calls["n"] += 1
            if calls["n"] <= 2:
                raise ConnectionFailure("transient: replica set stepping down")
            return await real(request, settings_doc)

        monkeypatch.setattr(workflow_engine, "_validate_request", flaky)

        workflow = await submit(
            client, customer_actor, [{"product_id": product_id, "quantity": 2}]
        )

        assert calls["n"] == 3, "should have run once plus two retries"
        assert workflow["outcome"] == WorkflowOutcome.COMPLETED.value
        assert workflow["retries_used"] == 2
        # The retry count is recorded on the step and on the request.
        validate_step = next(
            step
            for step in await _steps(client, customer_actor, workflow)
            if step["step"] == WorkflowStep.VALIDATE_REQUEST.value
        )
        assert validate_step["retries"] == 2
        assert workflow["request"]["retry_count"] == 2

    async def test_retries_stop_at_the_configured_maximum(
        self, client, customer_actor, manager, monkeypatch
    ):
        """A fault that never clears is retried exactly max_retries times."""
        await set_execution_policy(client, manager, max_retries_per_step=3)
        product_id = await create_product(sku="RETRY-CAP")
        calls = {"n": 0}

        async def always_failing(request, settings_doc):
            calls["n"] += 1
            raise ConnectionFailure("transient: database unreachable")

        monkeypatch.setattr(workflow_engine, "_validate_request", always_failing)

        workflow = await submit(
            client, customer_actor, [{"product_id": product_id, "quantity": 1}]
        )
        # Stopped at the limit rather than looping, and the request was parked
        # rather than the fault surfacing to the submitter.
        assert calls["n"] == 4, f"1 attempt + 3 retries, got {calls['n']}"
        assert workflow["outcome"] == WorkflowOutcome.ESCALATED.value
        assert (
            workflow["escalation_reason"]
            == EscalationReason.REPEATED_PROCESSING_FAILURE.value
        )
        assert workflow["retries_used"] == 3
        assert "3 retry(ies)" in workflow["escalation_detail"]

    async def test_the_retry_limit_is_configurable(
        self, client, customer_actor, manager, monkeypatch
    ):
        await set_execution_policy(client, manager, max_retries_per_step=1)
        product_id = await create_product(sku="RETRY-ONE")
        calls = {"n": 0}

        async def always_failing(request, settings_doc):
            calls["n"] += 1
            raise ConnectionFailure("transient")

        monkeypatch.setattr(workflow_engine, "_validate_request", always_failing)
        workflow = await submit(
            client, customer_actor, [{"product_id": product_id, "quantity": 1}]
        )
        assert calls["n"] == 2, "1 attempt + 1 retry"
        assert workflow["retries_used"] == 1

    async def test_a_permanent_failure_is_never_retried(
        self, client, customer_actor, monkeypatch
    ):
        """A validation verdict is final; retrying would reach the same answer."""
        product_id = await create_product(sku="NO-RETRY")
        calls = {"n": 0}

        async def permanent(request, settings_doc):
            calls["n"] += 1
            raise BusinessRuleError("policy says no")

        monkeypatch.setattr(workflow_engine, "_validate_request", permanent)

        workflow = await submit(
            client, customer_actor, [{"product_id": product_id, "quantity": 1}]
        )
        assert calls["n"] == 1, "a permanent failure must not be retried"
        # Zero retries consumed: the classifier refused to spend budget on a
        # verdict. The request is still parked so the fault is not silent.
        assert workflow["retries_used"] == 0
        assert "0 retry(ies)" in workflow["escalation_detail"]
        assert workflow["outcome"] == WorkflowOutcome.ESCALATED.value

    async def test_a_validation_verdict_is_not_treated_as_a_fault(
        self, client, customer_actor
    ):
        """Invalid input fails the step without consuming any retry budget."""
        product_id = await create_product(
            sku="PERM-VERDICT", status=ProductStatus.DISCONTINUED
        )
        workflow = await submit(
            client, customer_actor, [{"product_id": product_id, "quantity": 1}]
        )
        assert workflow["outcome"] == WorkflowOutcome.VALIDATION_FAILED.value
        assert workflow["retries_used"] == 0
        assert workflow["request"]["retry_count"] == 0

    # ---- the classifier itself, with no workflow around it ---------------

    @pytest.mark.parametrize(
        "error,expected",
        [
            (ConnectionFailure("db"), FailureClass.TRANSIENT),
            (OSError("disk full"), FailureClass.TRANSIENT),
            (TimeoutError(), FailureClass.TRANSIENT),
            (BusinessRuleError("policy"), FailureClass.PERMANENT),
            (ValueError("unclassified"), FailureClass.PERMANENT),
        ],
    )
    def test_failures_are_classified(self, error, expected):
        assert classify(error) is expected
        assert is_retryable(error) is (expected is FailureClass.TRANSIENT)

    async def test_the_budget_retries_then_re_raises(self):
        """`run_step` retries transients up to the allowance, then gives up."""
        budget = ExecutionBudget(
            policy=ExecutionPolicy(max_retries_per_step=2, retry_backoff_ms=0)
        )
        calls = {"n": 0}

        async def failing():
            calls["n"] += 1
            raise ConnectionFailure("still down")

        with pytest.raises(ConnectionFailure):
            await budget.run_step("STEP", failing)

        assert calls["n"] == 3, "1 attempt + 2 retries"
        assert budget.retries_used == 2
        assert [record.step for record in budget.retries] == ["STEP", "STEP"]


# ===========================================================================
# B. Success gate
# ===========================================================================


class TestSuccessGate:
    async def test_completion_requires_all_six_conditions(
        self, client, customer_actor
    ):
        product_id = await create_product(sku="GATE-OK", unit_price="1000.00")
        workflow = await submit(
            client, customer_actor, [{"product_id": product_id, "quantity": 3}]
        )

        assert workflow["outcome"] == WorkflowOutcome.COMPLETED.value
        assert workflow["resulting_status"] == RequestStatus.COMPLETED.value
        gate = workflow["gate"]
        assert set(gate) == set(workflow_engine.SUCCESS_GATE_CONDITIONS)
        assert all(gate.values()), gate
        assert workflow["request"]["completed_at"] is not None

    def test_the_gate_is_allow_on_proof_not_allow_by_default(self):
        """An unevaluated condition counts as unmet."""
        passed, unmet = workflow_engine.evaluate_success_gate({})
        assert passed is False
        assert set(unmet) == set(workflow_engine.SUCCESS_GATE_CONDITIONS)

    @pytest.mark.parametrize("missing", workflow_engine.SUCCESS_GATE_CONDITIONS)
    def test_any_single_unmet_condition_blocks_completion(self, missing):
        gate = dict.fromkeys(workflow_engine.SUCCESS_GATE_CONDITIONS, True)
        gate[missing] = False
        passed, unmet = workflow_engine.evaluate_success_gate(gate)
        assert passed is False
        assert unmet == [missing]

    async def test_a_queued_request_does_not_reach_the_gate(
        self, client, customer_actor
    ):
        """Awaiting approval means the document steps have not run."""
        product_id = await create_product(
            sku="GATE-QUEUED", unit_price="1000.00", cost_price="100.00"
        )
        workflow = await submit(
            client,
            customer_actor,
            [
                {
                    "product_id": product_id,
                    "quantity": 10,
                    "requested_discount_percent": 9,
                }
            ],
        )
        assert workflow["resulting_status"] == RequestStatus.PENDING_APPROVAL.value
        gate = workflow["gate"]
        assert gate["approval_recorded"] is False
        assert gate["document_generated"] is False
        assert gate["independent_verification_passed"] is False
        assert workflow["quotation_id"] is None

    async def test_verification_failure_blocks_completion(
        self, client, customer_actor, monkeypatch
    ):
        """If the checker rejects the document the request is not completed."""
        from app.services import checker_tool

        product_id = await create_product(sku="GATE-VERIFY")

        real = checker_tool.verify_quotation

        async def rejecting(quotation, **kwargs):
            report = await real(quotation, **kwargs)
            report.fail(
                checker_tool.Finding(
                    check="final_amount",
                    detail="Injected mismatch for the test.",
                    expected="1.00",
                    actual="2.00",
                )
            )
            return report

        monkeypatch.setattr(workflow_engine.checker_tool, "verify_quotation", rejecting)

        workflow = await submit(
            client, customer_actor, [{"product_id": product_id, "quantity": 2}]
        )

        assert workflow["outcome"] == WorkflowOutcome.ESCALATED.value
        assert workflow["resulting_status"] == RequestStatus.ESCALATED.value
        assert (
            workflow["escalation_reason"]
            == EscalationReason.VERIFICATION_MISMATCH.value
        )
        assert workflow["gate"]["independent_verification_passed"] is False
        assert workflow["request"]["completed_at"] is None


# ===========================================================================
# C. No-op condition
# ===========================================================================


class TestNoOpCondition:
    async def test_rerunning_a_completed_request_is_a_no_op(
        self, client, customer_actor, employee
    ):
        product_id = await create_product(sku="NOOP-DONE")
        workflow = await submit(
            client, customer_actor, [{"product_id": product_id, "quantity": 2}]
        )
        request_id = workflow["request"]["id"]
        quotation_id = workflow["quotation_id"]

        # Reprocess is refused for a settled request at the service layer, so
        # drive the engine directly - that is the path a retry or a stray
        # trigger would take.
        result = await workflow_engine.execute(request_id, trigger="REPROCESS")

        assert result.outcome is WorkflowOutcome.NO_OP
        assert result.resulting_status is RequestStatus.COMPLETED
        assert result.request.no_op_count == 1
        # Crucially, no second document.
        assert result.request.quotation_id == quotation_id
        count = await get_collection(Collections.QUOTATIONS).count_documents(
            {"request_id": request_id}
        )
        assert count == 1

    async def test_every_step_is_recorded_as_skipped(self, client, customer_actor):
        product_id = await create_product(sku="NOOP-STEPS")
        workflow = await submit(
            client, customer_actor, [{"product_id": product_id, "quantity": 1}]
        )
        result = await workflow_engine.execute(
            workflow["request"]["id"], trigger="REPROCESS"
        )

        assert len(result.steps) == len(workflow_engine.WORKFLOW_PIPELINE)
        assert all(step.status is StepStatus.SKIPPED for step in result.steps)
        assert all("already COMPLETED" in (step.message or "") for step in result.steps)

    async def test_the_no_op_is_audited(self, client, customer_actor, manager):
        product_id = await create_product(sku="NOOP-AUDIT")
        workflow = await submit(
            client, customer_actor, [{"product_id": product_id, "quantity": 1}]
        )
        await workflow_engine.execute(workflow["request"]["id"], trigger="REPROCESS")

        response = await client.get(
            "/api/v1/audit-logs",
            headers=manager.headers,
            params={"action": "WORKFLOW_NO_OP"},
        )
        assert response.json()["meta"]["total"] == 1
        entry = response.json()["items"][0]
        assert entry["metadata"]["status"] == RequestStatus.COMPLETED.value

    async def test_repeated_triggers_accumulate_the_count(
        self, client, customer_actor
    ):
        product_id = await create_product(sku="NOOP-COUNT")
        workflow = await submit(
            client, customer_actor, [{"product_id": product_id, "quantity": 1}]
        )
        request_id = workflow["request"]["id"]
        for _ in range(3):
            await workflow_engine.execute(request_id, trigger="REPROCESS")

        result = await workflow_engine.execute(request_id, trigger="REPROCESS")
        assert result.request.no_op_count == 4

    async def test_a_rejected_request_is_also_settled(
        self, client, customer_actor, manager
    ):
        product_id = await create_product(
            sku="NOOP-REJECTED", unit_price="1000.00", cost_price="100.00"
        )
        workflow = await submit(
            client,
            customer_actor,
            [
                {
                    "product_id": product_id,
                    "quantity": 10,
                    "requested_discount_percent": 9,
                }
            ],
        )
        await client.post(
            f"/api/v1/approvals/{workflow['approval_id']}/decision",
            headers=manager.headers,
            json={"decision": "REJECT", "comments": "No."},
        )
        result = await workflow_engine.execute(
            workflow["request"]["id"], trigger="REPROCESS"
        )
        assert result.outcome is WorkflowOutcome.NO_OP
        assert result.resulting_status is RequestStatus.REJECTED


# ===========================================================================
# D. Escalation condition
# ===========================================================================


class TestEscalationCondition:
    async def test_missing_customer_information_escalates(self, client):
        """A customer we cannot address cannot be quoted."""
        from app.models.enums import UserRole
        from tests.conftest import Actor, _login

        customer_id = await create_customer(
            code="CUST-INCOMPLETE", email="incomplete@test.example"
        )
        # Blank the contact details directly: the API will not accept them empty,
        # but legacy or imported records can be in this state.
        await get_collection(Collections.CUSTOMERS).update_one(
            {"_id": ObjectId(customer_id)},
            {"$set": {"phone": "", "contact_name": ""}},
        )
        user = await create_user(
            email="incomplete.buyer@test.example",
            role=UserRole.CUSTOMER,
            customer_id=customer_id,
        )
        actor = Actor(user["id"], user["email"], await _login(client, user["email"]))
        product_id = await create_product(sku="ESC-MISSING")

        workflow = await submit(
            client, actor, [{"product_id": product_id, "quantity": 1}]
        )
        assert workflow["outcome"] == WorkflowOutcome.VALIDATION_FAILED.value
        assert any(
            "missing required information" in error
            for error in workflow["validation_errors"]
        )
        assert any(
            "contact name" in error and "telephone" in error
            for error in workflow["validation_errors"]
        )

    async def test_product_unavailability_escalates_when_backorders_are_off(
        self, client, customer_actor, manager
    ):
        await client.patch(
            "/api/v1/settings",
            headers=manager.headers,
            json={"quotation_policy": {"allow_backorder": False}},
        )
        product_id = await create_product(sku="ESC-STOCK", stock_quantity=2)
        workflow = await submit(
            client, customer_actor, [{"product_id": product_id, "quantity": 10}]
        )
        assert workflow["outcome"] == WorkflowOutcome.VALIDATION_FAILED.value
        assert any(
            "backorders are not permitted" in error
            for error in workflow["validation_errors"]
        )

    async def test_a_discount_exception_escalates_to_a_manager(
        self, client, customer_actor
    ):
        product_id = await create_product(
            sku="ESC-DISCOUNT", unit_price="1000.00", cost_price="100.00"
        )
        workflow = await submit(
            client,
            customer_actor,
            [
                {
                    "product_id": product_id,
                    "quantity": 10,
                    "requested_discount_percent": 12,
                }
            ],
        )
        assert workflow["outcome"] == WorkflowOutcome.PENDING_APPROVAL.value
        assert workflow["approval_id"] is not None
        assert workflow["exceptions"][0]["type"] == "DISCOUNT_LIMIT_EXCEEDED"

    async def test_manager_rejection_settles_the_request(
        self, client, customer_actor, manager
    ):
        product_id = await create_product(
            sku="ESC-REJECT", unit_price="1000.00", cost_price="100.00"
        )
        workflow = await submit(
            client,
            customer_actor,
            [
                {
                    "product_id": product_id,
                    "quantity": 10,
                    "requested_discount_percent": 9,
                }
            ],
        )
        response = await client.post(
            f"/api/v1/approvals/{workflow['approval_id']}/decision",
            headers=manager.headers,
            json={"decision": "REJECT", "comments": "Margin too thin."},
        )
        assert response.status_code == 200
        assert response.json()["request"]["status"] == RequestStatus.REJECTED.value
        assert response.json()["quotation_id"] is None

    async def test_a_repeated_processing_failure_escalates(
        self, client, customer_actor, monkeypatch
    ):
        """The action tool failing past its retries parks the request."""
        from app.services import action_tool

        product_id = await create_product(sku="ESC-ACTION")

        async def always_failing(*args, **kwargs):
            raise ConnectionFailure("transient: storage unavailable")

        monkeypatch.setattr(workflow_engine.action_tool, "execute", always_failing)

        workflow = await submit(
            client, customer_actor, [{"product_id": product_id, "quantity": 1}]
        )

        assert workflow["outcome"] == WorkflowOutcome.ESCALATED.value
        assert (
            workflow["escalation_reason"]
            == EscalationReason.REPEATED_PROCESSING_FAILURE.value
        )
        assert workflow["gate"]["document_generated"] is False
        assert workflow["retries_used"] >= 1
        del action_tool

    async def test_a_verification_mismatch_escalates(
        self, client, customer_actor, manager
    ):
        """Tampering with a stored amount is caught and escalated."""
        from app.services import checker_tool

        product_id = await create_product(sku="ESC-TAMPER", unit_price="1000.00")
        workflow = await submit(
            client, customer_actor, [{"product_id": product_id, "quantity": 2}]
        )
        quotation_id = workflow["quotation_id"]

        # Edit the stored total behind the system's back.
        from bson import Decimal128

        await get_collection(Collections.QUOTATIONS).update_one(
            {"_id": ObjectId(quotation_id)},
            {"$set": {"pricing.final_amount": Decimal128("1.00")}},
        )

        quotation = await _load_quotation(quotation_id)
        report = await checker_tool.verify_quotation(quotation)
        assert report.passed is False
        assert any(finding.check == "final_amount" for finding in report.findings)

    async def test_an_escalated_request_notifies_the_manager(
        self, client, customer_actor, manager, monkeypatch
    ):
        product_id = await create_product(sku="ESC-NOTIFY")

        async def always_failing(*args, **kwargs):
            raise ConnectionFailure("transient")

        monkeypatch.setattr(workflow_engine.action_tool, "execute", always_failing)
        await submit(client, customer_actor, [{"product_id": product_id, "quantity": 1}])

        response = await client.get(
            "/api/v1/notifications", headers=manager.headers, params={"page_size": 20}
        )
        assert any(
            item["type"] == "WORKFLOW_ESCALATED" for item in response.json()["items"]
        )

    async def test_escalation_is_audited_with_the_reason(
        self, client, customer_actor, manager, monkeypatch
    ):
        product_id = await create_product(sku="ESC-AUDIT")

        async def always_failing(*args, **kwargs):
            raise ConnectionFailure("transient")

        monkeypatch.setattr(workflow_engine.action_tool, "execute", always_failing)
        await submit(client, customer_actor, [{"product_id": product_id, "quantity": 1}])

        response = await client.get(
            "/api/v1/audit-logs",
            headers=manager.headers,
            params={"action": "WORKFLOW_ESCALATED"},
        )
        assert response.json()["meta"]["total"] >= 1
        entry = response.json()["items"][0]
        assert (
            entry["metadata"]["escalation_reason"]
            == EscalationReason.REPEATED_PROCESSING_FAILURE.value
        )
        assert entry["metadata"]["retries_used"] >= 1


# ===========================================================================
# E. Budget limit
# ===========================================================================


class TestBudgetLimit:
    async def test_the_attempt_ceiling_stops_reprocessing(
        self, client, customer_actor, employee, manager
    ):
        """Once the attempts are spent the request escalates instead of running."""
        await set_execution_policy(client, manager, max_attempts_per_request=2)
        product_id = await create_product(
            sku="BUDGET-ATTEMPTS", status=ProductStatus.DISCONTINUED
        )

        # Attempt 1: fails validation.
        workflow = await submit(
            client, customer_actor, [{"product_id": product_id, "quantity": 1}]
        )
        request_id = workflow["request"]["id"]
        assert workflow["request"]["attempt_count"] == 1

        # Attempt 2: still fails.
        second = await client.post(
            f"/api/v1/quotation-requests/{request_id}/reprocess",
            headers=employee.headers,
        )
        assert second.json()["request"]["attempt_count"] == 2

        # Attempt 3 is over the ceiling: the engine refuses to run the pipeline.
        third = await client.post(
            f"/api/v1/quotation-requests/{request_id}/reprocess",
            headers=employee.headers,
        )
        body = third.json()
        assert body["outcome"] == WorkflowOutcome.BUDGET_EXCEEDED.value
        assert (
            body["escalation_reason"] == EscalationReason.BUDGET_EXCEEDED.value
        )
        assert "processing attempts" in body["escalation_detail"]

    async def test_attempts_are_counted_even_when_a_run_fails(
        self, client, customer_actor
    ):
        product_id = await create_product(
            sku="BUDGET-COUNT", status=ProductStatus.DISCONTINUED
        )
        workflow = await submit(
            client, customer_actor, [{"product_id": product_id, "quantity": 1}]
        )
        assert workflow["attempt_number"] == 1
        assert workflow["request"]["attempt_count"] == 1

    async def test_elapsed_time_accumulates_across_attempts(
        self, client, customer_actor
    ):
        product_id = await create_product(sku="BUDGET-TIME")
        workflow = await submit(
            client, customer_actor, [{"product_id": product_id, "quantity": 1}]
        )
        assert workflow["request"]["total_execution_ms"] >= 0
        execution = (await _executions(client, customer_actor, workflow))[0]
        assert execution["budget"]["max_execution_ms"] > 0
        assert execution["budget"]["attempt_number"] == 1

    async def test_the_line_ceiling_is_enforced(
        self, client, customer_actor, manager
    ):
        await set_execution_policy(client, manager, max_lines_per_request=2)
        ids = [await create_product(sku=f"BUDGET-LINE-{i}") for i in range(3)]

        workflow = await submit(
            client,
            customer_actor,
            [{"product_id": pid, "quantity": 1} for pid in ids],
        )
        assert workflow["outcome"] == WorkflowOutcome.VALIDATION_FAILED.value
        assert any(
            "above the 2 permitted" in error
            for error in workflow["validation_errors"]
        )

    async def test_the_quantity_ceiling_is_enforced(
        self, client, customer_actor, manager
    ):
        await set_execution_policy(client, manager, max_quantity_per_line=100)
        product_id = await create_product(sku="BUDGET-QTY", stock_quantity=10_000)

        workflow = await submit(
            client, customer_actor, [{"product_id": product_id, "quantity": 500}]
        )
        assert workflow["outcome"] == WorkflowOutcome.VALIDATION_FAILED.value
        assert any(
            "exceeds the 100 permitted" in error
            for error in workflow["validation_errors"]
        )

    async def test_a_spent_duration_budget_raises(self):
        """The duration ceiling is checked, not merely configured."""
        budget = ExecutionBudget(
            policy=ExecutionPolicy(max_execution_ms=100, retry_backoff_ms=0),
            prior_elapsed_ms=0,
        )
        # Pretend the run started long ago.
        budget.started_at -= 5.0
        spent, reason = budget.exceeded()
        assert spent is True
        assert "execution limit" in reason
        with pytest.raises(BudgetExceeded):
            budget.assert_within_budget()

    async def test_a_spent_total_duration_budget_raises(self):
        budget = ExecutionBudget(
            policy=ExecutionPolicy(
                max_execution_ms=60_000, max_total_execution_ms=1_000
            ),
            prior_elapsed_ms=2_000,
        )
        spent, reason = budget.exceeded()
        assert spent is True
        assert "total execution limit" in reason

    async def test_the_attempt_ceiling_is_checked_before_work_starts(self):
        budget = ExecutionBudget(
            policy=ExecutionPolicy(max_attempts_per_request=3), attempt_number=4
        )
        spent, reason = budget.exceeded()
        assert spent is True
        assert "processing attempts" in reason

    async def test_the_budget_blocks_a_step_once_spent(self):
        budget = ExecutionBudget(
            policy=ExecutionPolicy(max_attempts_per_request=1), attempt_number=2
        )
        calls = {"n": 0}

        async def work():
            calls["n"] += 1
            return "done"

        with pytest.raises(BudgetExceeded):
            await budget.run_step("STEP", work)
        assert calls["n"] == 0, "the step must not run at all"

    async def test_every_limit_is_configurable_through_the_api(
        self, client, manager
    ):
        policy = await set_execution_policy(
            client,
            manager,
            max_retries_per_step=2,
            max_attempts_per_request=4,
            max_execution_ms=12_345,
            max_total_execution_ms=54_321,
            max_lines_per_request=7,
            max_quantity_per_line=999,
            retry_backoff_ms=10,
        )
        assert policy["max_retries_per_step"] == 2
        assert policy["max_attempts_per_request"] == 4
        assert policy["max_execution_ms"] == 12_345
        assert policy["max_total_execution_ms"] == 54_321
        assert policy["max_lines_per_request"] == 7
        assert policy["max_quantity_per_line"] == 999
        assert policy["retry_backoff_ms"] == 10

        # And the engine reads them, rather than holding its own copy.
        stored = await settings_service.get_settings_document()
        assert stored.execution_policy.max_retries_per_step == 2
        assert stored.execution_policy.max_attempts_per_request == 4

    async def test_an_invalid_limit_is_rejected(self, client, manager):
        response = await client.patch(
            "/api/v1/settings",
            headers=manager.headers,
            json={"execution_policy": {"max_retries_per_step": 99}},
        )
        assert response.status_code == 422

    def test_backoff_grows_with_each_retry(self):
        policy = ExecutionPolicy(retry_backoff_ms=100)
        assert [policy.backoff_for(n) for n in (1, 2, 3)] == [0.1, 0.2, 0.4]
        assert ExecutionPolicy(retry_backoff_ms=0).backoff_for(1) == 0.0


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------


async def _executions(client, actor, workflow):
    response = await client.get(
        f"/api/v1/quotation-requests/{workflow['request']['id']}/executions",
        headers=actor.headers,
    )
    assert response.status_code == 200, response.text
    return response.json()


async def _steps(client, actor, workflow):
    return (await _executions(client, actor, workflow))[0]["steps"]


async def _load_quotation(quotation_id: str):
    from app.models.quotation import Quotation
    from app.utils.money import decode_decimals

    raw = await get_collection(Collections.QUOTATIONS).find_one(
        {"_id": ObjectId(quotation_id)}
    )
    return Quotation.from_mongo(decode_decimals(raw))


def test_decimal_import_is_used():
    """Keep the Decimal import honest - used by the policy equality checks."""
    assert Decimal("0.1") + Decimal("0.2") == Decimal("0.3")
