"""Master-data authorisation: a sales employee proposes, a manager decides.

The boundary being tested is that a sales employee cannot add a customer or a
product on their own authority. Every test here either proves the refusal, or
proves that the approval route produces exactly the record the direct route
would have - no shortcut, no second code path.
"""

from app.db.mongo import Collections, get_collection
from app.models.enums import MasterDataRequestStatus
from tests.conftest import create_product

CUSTOMERS = "/api/v1/customers"
PRODUCTS = "/api/v1/products"
QUEUE = "/api/v1/master-data-requests"

NEW_CUSTOMER = {
    "company_name": "Proposed Industries",
    "contact_name": "Asha Nair",
    "email": "Asha@Proposed.example",
    "phone": "9876500011",
    "tier": "SILVER",
    "credit_limit": 250000,
    "notes": "Met at the trade fair.",
}

NEW_PRODUCT = {
    "sku": "prop-001",
    "name": "Proposed Widget",
    "category": "Testing",
    "unit_price": 2400,
    "cost_price": 1500,
    "stock_quantity": 40,
    "lead_time_days": 6,
}


async def submit_customer(client, actor, **overrides):
    payload = {"customer": {**NEW_CUSTOMER, **overrides}, "reason": "New account."}
    return await client.post(f"{QUEUE}/customers", headers=actor.headers, json=payload)


async def submit_product(client, actor, **overrides):
    payload = {"product": {**NEW_PRODUCT, **overrides}, "reason": "Range extension."}
    return await client.post(f"{QUEUE}/products", headers=actor.headers, json=payload)


# ---------------------------------------------------------------------------
# The boundary: an employee cannot write master data directly
# ---------------------------------------------------------------------------


class TestDirectCreationIsManagerOnly:
    async def test_an_employee_cannot_create_a_customer(self, client, employee):
        response = await client.post(
            CUSTOMERS, headers=employee.headers, json=NEW_CUSTOMER
        )
        assert response.status_code == 403
        error = response.json()["error"]
        assert error["code"] == "permission_denied"
        assert error["details"]["submit_route"] == f"{QUEUE}/customers"

    async def test_an_employee_cannot_create_a_product(self, client, employee):
        response = await client.post(PRODUCTS, headers=employee.headers, json=NEW_PRODUCT)
        assert response.status_code == 403
        assert response.json()["error"]["details"]["submit_route"] == f"{QUEUE}/products"

    async def test_the_refusal_writes_nothing(self, client, employee):
        await client.post(CUSTOMERS, headers=employee.headers, json=NEW_CUSTOMER)
        found = await get_collection(Collections.CUSTOMERS).find_one(
            {"email": "asha@proposed.example"}
        )
        assert found is None

    async def test_a_manager_can_still_create_a_customer_directly(self, client, manager):
        response = await client.post(
            CUSTOMERS, headers=manager.headers, json=NEW_CUSTOMER
        )
        assert response.status_code == 201
        assert response.json()["company_name"] == "Proposed Industries"

    async def test_a_customer_cannot_use_the_approval_queue(self, client, customer_actor):
        response = await submit_customer(client, customer_actor)
        assert response.status_code == 403

    async def test_an_employee_may_still_edit_an_existing_customer(
        self, client, employee, customer_actor
    ):
        """Only *adding* needs authorisation; day-to-day upkeep does not."""
        response = await client.patch(
            f"{CUSTOMERS}/{customer_actor.customer_id}",
            headers=employee.headers,
            json={"phone": "9000011111"},
        )
        assert response.status_code == 200
        assert response.json()["phone"] == "9000011111"


# ---------------------------------------------------------------------------
# Submission
# ---------------------------------------------------------------------------


class TestSubmission:
    async def test_an_employee_can_submit_a_customer(self, client, employee):
        response = await submit_customer(client, employee)
        assert response.status_code == 201
        body = response.json()
        assert body["status"] == MasterDataRequestStatus.PENDING.value
        assert body["entity_type"] == "CUSTOMER"
        assert body["label"] == "Proposed Industries"
        assert body["requested_by_name"] == "Test Employee"
        assert body["reason"] == "New account."
        assert body["reference"].startswith("MDR-")
        # Nothing is created yet.
        assert body["created_entity_id"] is None

    async def test_submitting_does_not_touch_the_customers_collection(
        self, client, employee
    ):
        await submit_customer(client, employee)
        found = await get_collection(Collections.CUSTOMERS).find_one(
            {"email": "asha@proposed.example"}
        )
        assert found is None

    async def test_the_submitted_values_are_preserved_verbatim(self, client, employee):
        response = await submit_customer(client, employee, credit_limit=777000)
        payload = response.json()["payload"]
        assert payload["company_name"] == "Proposed Industries"
        assert payload["credit_limit"] == 777000
        assert payload["tier"] == "SILVER"
        # The email is normalised on the way in, as the direct route does.
        assert payload["email"] == "asha@proposed.example"

    async def test_an_employee_can_submit_a_product(self, client, employee):
        response = await submit_product(client, employee)
        assert response.status_code == 201
        body = response.json()
        assert body["entity_type"] == "PRODUCT"
        assert body["label"] == "PROP-001 — Proposed Widget"
        assert body["payload"]["sku"] == "PROP-001"

    async def test_an_invalid_payload_is_refused_at_submission(self, client, employee):
        response = await submit_product(client, employee, unit_price=0)
        assert response.status_code == 422

    async def test_a_manager_may_also_submit_rather_than_create(self, client, manager):
        """Nothing stops a manager using the queue; it is a staff route."""
        response = await submit_customer(client, manager)
        assert response.status_code == 201

    async def test_a_customer_that_already_exists_is_refused_immediately(
        self, client, employee, customer_actor
    ):
        existing = await client.get(
            f"{CUSTOMERS}/{customer_actor.customer_id}", headers=employee.headers
        )
        response = await submit_customer(client, employee, email=existing.json()["email"])
        assert response.status_code == 409
        assert "already exists" in response.json()["error"]["message"]

    async def test_a_product_sku_that_already_exists_is_refused_immediately(
        self, client, employee
    ):
        await create_product(sku="TAKEN-1")
        response = await submit_product(client, employee, sku="taken-1")
        assert response.status_code == 409

    async def test_the_same_record_cannot_be_queued_twice(self, client, employee):
        first = await submit_customer(client, employee)
        assert first.status_code == 201
        second = await submit_customer(client, employee)
        assert second.status_code == 409
        assert "already waiting" in second.json()["error"]["message"]

    async def test_a_second_employee_cannot_queue_the_same_record(
        self, client, employee, manager
    ):
        """The constraint is on the record, not on the person asking."""
        await submit_customer(client, employee)
        response = await submit_customer(client, manager)
        assert response.status_code == 409


# ---------------------------------------------------------------------------
# The queue
# ---------------------------------------------------------------------------


class TestQueue:
    async def test_a_manager_sees_the_whole_queue(self, client, employee, manager):
        await submit_customer(client, employee)
        response = await client.get(QUEUE, headers=manager.headers)
        assert response.status_code == 200
        assert response.json()["meta"]["total"] == 1

    async def test_the_pending_count_drives_the_managers_badge(
        self, client, employee, manager
    ):
        assert (
            await client.get(f"{QUEUE}/pending-count", headers=manager.headers)
        ).json()["pending"] == 0
        await submit_customer(client, employee)
        await submit_product(client, employee)
        response = await client.get(f"{QUEUE}/pending-count", headers=manager.headers)
        assert response.json()["pending"] == 2

    async def test_an_employee_sees_only_their_own_requests(
        self, client, employee, manager
    ):
        await submit_customer(client, manager)
        response = await client.get(QUEUE, headers=employee.headers)
        assert response.json()["meta"]["total"] == 0

    async def test_an_employee_cannot_read_another_persons_request(
        self, client, employee, manager
    ):
        raised = await submit_customer(client, manager)
        request_id = raised.json()["id"]
        response = await client.get(f"{QUEUE}/{request_id}", headers=employee.headers)
        assert response.status_code == 404

    async def test_the_queue_can_be_filtered_by_entity_type(
        self, client, employee, manager
    ):
        await submit_customer(client, employee)
        await submit_product(client, employee)
        response = await client.get(
            QUEUE, headers=manager.headers, params={"entity_type": "PRODUCT"}
        )
        items = response.json()["items"]
        assert len(items) == 1
        assert items[0]["entity_type"] == "PRODUCT"

    async def test_the_queue_can_be_filtered_by_status(self, client, employee, manager):
        raised = await submit_customer(client, employee)
        await client.post(
            f"{QUEUE}/{raised.json()['id']}/decision",
            headers=manager.headers,
            json={"approve": True},
        )
        await submit_product(client, employee)

        pending = await client.get(
            QUEUE, headers=manager.headers, params={"status": "PENDING"}
        )
        assert pending.json()["meta"]["total"] == 1
        approved = await client.get(
            QUEUE, headers=manager.headers, params={"status": "APPROVED"}
        )
        assert approved.json()["meta"]["total"] == 1


# ---------------------------------------------------------------------------
# Approval
# ---------------------------------------------------------------------------


class TestApproval:
    async def test_approving_creates_the_customer(self, client, employee, manager):
        raised = await submit_customer(client, employee)
        response = await client.post(
            f"{QUEUE}/{raised.json()['id']}/decision",
            headers=manager.headers,
            json={"approve": True, "comments": "Known buyer."},
        )
        assert response.status_code == 200
        body = response.json()
        assert body["request"]["status"] == "APPROVED"
        assert body["customer"]["company_name"] == "Proposed Industries"
        assert body["customer"]["email"] == "asha@proposed.example"
        assert body["customer"]["tier"] == "SILVER"
        assert body["customer"]["code"].startswith("CUST-")
        assert body["product"] is None

    async def test_the_approved_customer_appears_in_the_customer_list(
        self, client, employee, manager
    ):
        raised = await submit_customer(client, employee)
        await client.post(
            f"{QUEUE}/{raised.json()['id']}/decision",
            headers=manager.headers,
            json={"approve": True},
        )
        listing = await client.get(
            CUSTOMERS, headers=employee.headers, params={"search": "Proposed"}
        )
        assert listing.json()["meta"]["total"] == 1

    async def test_approving_creates_the_product(self, client, employee, manager):
        raised = await submit_product(client, employee)
        response = await client.post(
            f"{QUEUE}/{raised.json()['id']}/decision",
            headers=manager.headers,
            json={"approve": True},
        )
        body = response.json()
        assert body["product"]["sku"] == "PROP-001"
        assert body["product"]["unit_price"] == 2400.0
        assert body["product"]["available_quantity"] == 40
        assert body["customer"] is None

    async def test_the_decision_records_who_authorised_it(
        self, client, employee, manager
    ):
        raised = await submit_customer(client, employee)
        response = await client.post(
            f"{QUEUE}/{raised.json()['id']}/decision",
            headers=manager.headers,
            json={"approve": True, "comments": "Fine."},
        )
        request = response.json()["request"]
        assert request["decided_by_name"] == "Test Manager"
        assert request["decided_by"] == manager.id
        assert request["decided_at"] is not None
        assert request["decision_comments"] == "Fine."
        # And it links to what it produced.
        assert request["created_entity_id"]
        assert request["created_entity_label"].startswith("CUST-")

    async def test_the_audit_trail_names_the_proposer_and_the_authoriser(
        self, client, employee, manager
    ):
        raised = await submit_customer(client, employee)
        await client.post(
            f"{QUEUE}/{raised.json()['id']}/decision",
            headers=manager.headers,
            json={"approve": True},
        )
        entries = await client.get(
            "/api/v1/audit-logs",
            headers=manager.headers,
            params={"entity_type": "master_data_request", "page_size": 50},
        )
        actions = {item["action"] for item in entries.json()["items"]}
        assert {"MASTER_DATA_REQUESTED", "MASTER_DATA_APPROVED"} <= actions

        approved = next(
            item
            for item in entries.json()["items"]
            if item["action"] == "MASTER_DATA_APPROVED"
        )
        assert approved["actor_email"] == manager.email
        assert approved["metadata"]["requested_by"] == "Test Employee"

    async def test_the_created_customer_is_audited_against_the_manager(
        self, client, employee, manager
    ):
        """The record is created by the manager's authority, not the employee's."""
        raised = await submit_customer(client, employee)
        await client.post(
            f"{QUEUE}/{raised.json()['id']}/decision",
            headers=manager.headers,
            json={"approve": True},
        )
        entries = await client.get(
            "/api/v1/audit-logs",
            headers=manager.headers,
            params={"action": "CUSTOMER_CREATED"},
        )
        assert entries.json()["items"][0]["actor_email"] == manager.email

    async def test_the_employee_is_told_the_outcome(self, client, employee, manager):
        raised = await submit_customer(client, employee)
        await client.post(
            f"{QUEUE}/{raised.json()['id']}/decision",
            headers=manager.headers,
            json={"approve": True},
        )
        inbox = await client.get("/api/v1/notifications", headers=employee.headers)
        titles = [item["title"] for item in inbox.json()["items"]]
        assert any("Approved" in title for title in titles)

    async def test_managers_are_told_a_request_is_waiting(
        self, client, employee, manager
    ):
        await submit_customer(client, employee)
        inbox = await client.get("/api/v1/notifications", headers=manager.headers)
        types = [item["type"] for item in inbox.json()["items"]]
        assert "MASTER_DATA_REQUESTED" in types

    async def test_approving_frees_the_slot_for_another_proposal(
        self, client, employee, manager
    ):
        """The pending-uniqueness constraint must not outlive the decision."""
        raised = await submit_product(client, employee)
        await client.post(
            f"{QUEUE}/{raised.json()['id']}/decision",
            headers=manager.headers,
            json={"approve": True},
        )
        # The product now exists, so a repeat proposal is refused for that
        # reason - not because the index still holds the old row.
        response = await submit_product(client, employee)
        assert response.status_code == 409
        assert "already exists" in response.json()["error"]["message"]


# ---------------------------------------------------------------------------
# Refusal
# ---------------------------------------------------------------------------


class TestRefusal:
    async def test_refusing_creates_nothing(self, client, employee, manager):
        raised = await submit_customer(client, employee)
        response = await client.post(
            f"{QUEUE}/{raised.json()['id']}/decision",
            headers=manager.headers,
            json={"approve": False, "comments": "Credit check outstanding."},
        )
        assert response.status_code == 200
        body = response.json()
        assert body["request"]["status"] == "REJECTED"
        assert body["customer"] is None
        assert body["request"]["created_entity_id"] is None

        found = await get_collection(Collections.CUSTOMERS).find_one(
            {"email": "asha@proposed.example"}
        )
        assert found is None

    async def test_a_refusal_requires_a_reason(self, client, employee, manager):
        raised = await submit_customer(client, employee)
        response = await client.post(
            f"{QUEUE}/{raised.json()['id']}/decision",
            headers=manager.headers,
            json={"approve": False},
        )
        assert response.status_code == 409
        assert "reason is required" in response.json()["error"]["message"]

    async def test_a_blank_reason_does_not_count(self, client, employee, manager):
        raised = await submit_customer(client, employee)
        response = await client.post(
            f"{QUEUE}/{raised.json()['id']}/decision",
            headers=manager.headers,
            json={"approve": False, "comments": "   "},
        )
        assert response.status_code == 409

    async def test_the_submitted_values_survive_a_refusal(
        self, client, employee, manager
    ):
        """A rejected proposal still shows exactly what was asked for."""
        raised = await submit_customer(client, employee)
        await client.post(
            f"{QUEUE}/{raised.json()['id']}/decision",
            headers=manager.headers,
            json={"approve": False, "comments": "Not yet."},
        )
        response = await client.get(
            f"{QUEUE}/{raised.json()['id']}", headers=employee.headers
        )
        body = response.json()
        assert body["payload"]["company_name"] == "Proposed Industries"
        assert body["reason"] == "New account."
        assert body["decision_comments"] == "Not yet."

    async def test_a_refused_record_can_be_proposed_again(
        self, client, employee, manager
    ):
        """Refusal must not permanently blacklist the record."""
        raised = await submit_customer(client, employee)
        await client.post(
            f"{QUEUE}/{raised.json()['id']}/decision",
            headers=manager.headers,
            json={"approve": False, "comments": "Fix the credit limit."},
        )
        response = await submit_customer(client, employee, credit_limit=50000)
        assert response.status_code == 201


# ---------------------------------------------------------------------------
# Who may decide, and how often
# ---------------------------------------------------------------------------


class TestDecisionAuthority:
    async def test_an_employee_cannot_approve_anything(self, client, employee):
        raised = await submit_customer(client, employee)
        response = await client.post(
            f"{QUEUE}/{raised.json()['id']}/decision",
            headers=employee.headers,
            json={"approve": True},
        )
        assert response.status_code == 403

    async def test_an_employee_cannot_approve_their_own_request(self, client, employee):
        """The point of the control: self-service is exactly what is blocked."""
        raised = await submit_customer(client, employee)
        await client.post(
            f"{QUEUE}/{raised.json()['id']}/decision",
            headers=employee.headers,
            json={"approve": True},
        )
        found = await get_collection(Collections.CUSTOMERS).find_one(
            {"email": "asha@proposed.example"}
        )
        assert found is None

    async def test_a_customer_cannot_decide(self, client, employee, customer_actor):
        raised = await submit_customer(client, employee)
        response = await client.post(
            f"{QUEUE}/{raised.json()['id']}/decision",
            headers=customer_actor.headers,
            json={"approve": True},
        )
        assert response.status_code == 403

    async def test_a_decision_cannot_be_taken_twice(self, client, employee, manager):
        raised = await submit_customer(client, employee)
        first = await client.post(
            f"{QUEUE}/{raised.json()['id']}/decision",
            headers=manager.headers,
            json={"approve": False, "comments": "No."},
        )
        assert first.status_code == 200
        second = await client.post(
            f"{QUEUE}/{raised.json()['id']}/decision",
            headers=manager.headers,
            json={"approve": True},
        )
        assert second.status_code == 409
        assert "already been decided" in second.json()["error"]["message"]

    async def test_an_approved_request_cannot_be_approved_again(
        self, client, employee, manager
    ):
        """Otherwise a second approval would create a duplicate customer."""
        raised = await submit_customer(client, employee)
        await client.post(
            f"{QUEUE}/{raised.json()['id']}/decision",
            headers=manager.headers,
            json={"approve": True},
        )
        again = await client.post(
            f"{QUEUE}/{raised.json()['id']}/decision",
            headers=manager.headers,
            json={"approve": True},
        )
        assert again.status_code == 409
        assert (
            await get_collection(Collections.CUSTOMERS).count_documents(
                {"email": "asha@proposed.example"}
            )
            == 1
        )

    async def test_an_unknown_request_is_a_404(self, client, manager):
        response = await client.post(
            f"{QUEUE}/000000000000000000000000/decision",
            headers=manager.headers,
            json={"approve": True},
        )
        assert response.status_code == 404

    async def test_a_malformed_id_is_a_422(self, client, manager):
        response = await client.get(f"{QUEUE}/not-an-id", headers=manager.headers)
        assert response.status_code == 422


# ---------------------------------------------------------------------------
# Withdrawal
# ---------------------------------------------------------------------------


class TestWithdrawal:
    async def test_the_requester_can_withdraw_their_own(self, client, employee):
        raised = await submit_customer(client, employee)
        response = await client.post(
            f"{QUEUE}/{raised.json()['id']}/withdraw", headers=employee.headers
        )
        assert response.status_code == 200
        assert response.json()["status"] == "WITHDRAWN"

    async def test_somebody_else_cannot_withdraw_it(self, client, employee, manager):
        raised = await submit_customer(client, employee)
        response = await client.post(
            f"{QUEUE}/{raised.json()['id']}/withdraw", headers=manager.headers
        )
        assert response.status_code == 403

    async def test_a_withdrawn_request_cannot_then_be_approved(
        self, client, employee, manager
    ):
        raised = await submit_customer(client, employee)
        await client.post(
            f"{QUEUE}/{raised.json()['id']}/withdraw", headers=employee.headers
        )
        response = await client.post(
            f"{QUEUE}/{raised.json()['id']}/decision",
            headers=manager.headers,
            json={"approve": True},
        )
        assert response.status_code == 409

    async def test_withdrawing_frees_the_record_to_be_proposed_again(
        self, client, employee
    ):
        raised = await submit_customer(client, employee)
        await client.post(
            f"{QUEUE}/{raised.json()['id']}/withdraw", headers=employee.headers
        )
        response = await submit_customer(client, employee)
        assert response.status_code == 201


# ---------------------------------------------------------------------------
# Protection
# ---------------------------------------------------------------------------


class TestProtection:
    async def test_every_route_requires_a_token(self, client):
        for method, path in [
            ("POST", f"{QUEUE}/customers"),
            ("POST", f"{QUEUE}/products"),
            ("GET", QUEUE),
            ("GET", f"{QUEUE}/pending-count"),
            ("GET", f"{QUEUE}/000000000000000000000000"),
            ("POST", f"{QUEUE}/000000000000000000000000/decision"),
            ("POST", f"{QUEUE}/000000000000000000000000/withdraw"),
        ]:
            response = await client.request(method, path, json={})
            assert response.status_code == 401, f"{method} {path}"
