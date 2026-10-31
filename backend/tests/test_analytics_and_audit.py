"""Analytics aggregations, the audit trail and the configurable rule book."""

from app.models.enums import ApprovalDecision, AuditAction
from tests.conftest import create_product


async def _auto_approved(client, actor, *, sku, quantity=4, unit_price="1000.00"):
    product_id = await create_product(
        sku=sku, unit_price=unit_price, cost_price="100.00", stock_quantity=1000
    )
    response = await client.post(
        "/api/v1/quotation-requests",
        headers=actor.headers,
        json={"items": [{"product_id": product_id, "quantity": quantity}], "submit": True},
    )
    assert response.status_code == 201, response.text
    return response.json()["workflow"]


async def _needs_approval(client, actor, *, sku, discount=9):
    product_id = await create_product(
        sku=sku, unit_price="1000.00", cost_price="100.00", stock_quantity=1000
    )
    response = await client.post(
        "/api/v1/quotation-requests",
        headers=actor.headers,
        json={
            "items": [
                {
                    "product_id": product_id,
                    "quantity": 10,
                    "requested_discount_percent": discount,
                }
            ],
            "submit": True,
        },
    )
    assert response.status_code == 201, response.text
    return response.json()["workflow"]


# ---------------------------------------------------------------------------
# Analytics
# ---------------------------------------------------------------------------


async def test_the_overview_counts_requests_and_value(
    client, customer_actor, manager
):
    await _auto_approved(client, customer_actor, sku="AN-1", quantity=4)
    await _auto_approved(client, customer_actor, sku="AN-2", quantity=6)
    await _needs_approval(client, customer_actor, sku="AN-3")

    response = await client.get("/api/v1/analytics/overview", headers=manager.headers)
    assert response.status_code == 200
    body = response.json()

    assert body["total_requests"] == 3
    # Both completed requests count as approved outcomes.
    assert body["approved_requests"] == 2
    assert body["completed_requests"] == 2
    assert body["requests_by_status"]["PENDING_APPROVAL"] == 1
    assert body["open_requests"] == 1
    assert body["pending_approvals"] == 1
    assert body["quotations_issued"] == 2
    assert body["live_quotations"] == 2
    # 4 x 1000 + 18% plus 6 x 1000 less 5% band... only the two auto-approved.
    assert body["quoted_value"] == 4720.0 + 7080.0
    assert body["automation_rate_percent"] == 100.0
    assert body["approval_rate_percent"] == 100.0


async def test_the_overview_is_safe_on_an_empty_database(client, manager):
    response = await client.get("/api/v1/analytics/overview", headers=manager.headers)
    assert response.status_code == 200
    body = response.json()
    assert body["total_requests"] == 0
    assert body["quoted_value"] == 0.0
    assert body["average_quotation_value"] == 0.0
    assert body["approval_rate_percent"] == 0.0
    assert body["automation_rate_percent"] == 0.0
    assert body["discount_rate_percent"] == 0.0


async def test_the_discount_rate_is_measured_against_gross_value(
    client, customer_actor, manager
):
    product_id = await create_product(
        sku="DR-1", unit_price="1000.00", cost_price="100.00"
    )
    await client.post(
        "/api/v1/quotation-requests",
        headers=customer_actor.headers,
        json={
            "items": [
                {
                    "product_id": product_id,
                    "quantity": 10,
                    "requested_discount_percent": 5,
                }
            ],
            "submit": True,
        },
    )
    response = await client.get("/api/v1/analytics/overview", headers=manager.headers)
    body = response.json()
    assert body["total_discount_given"] == 500.0
    # Gross = 11210 net + 500 discount; 500 / 11710 = 4.27%
    assert body["discount_rate_percent"] == 4.27


async def test_the_request_trend_is_bucketed_by_day(client, customer_actor, manager):
    await _auto_approved(client, customer_actor, sku="TR-1")
    await _needs_approval(client, customer_actor, sku="TR-2")

    response = await client.get(
        "/api/v1/analytics/requests/trend", headers=manager.headers
    )
    assert response.status_code == 200
    rows = response.json()
    assert len(rows) == 1
    assert rows[0]["total"] == 2
    assert rows[0]["approved"] == 1
    assert rows[0]["pending"] == 1
    assert rows[0]["escalated"] == 0
    assert len(rows[0]["date"]) == 10  # YYYY-MM-DD


async def test_top_products_ranks_by_value(client, customer_actor, manager):
    await _auto_approved(
        client, customer_actor, sku="TOP-SMALL", quantity=1, unit_price="100.00"
    )
    await _auto_approved(
        client, customer_actor, sku="TOP-BIG", quantity=4, unit_price="9000.00"
    )

    response = await client.get(
        "/api/v1/analytics/products/top", headers=manager.headers
    )
    rows = response.json()
    assert rows[0]["sku"] == "TOP-BIG"
    assert rows[0]["quantity"] == 4
    assert rows[0]["value"] > rows[1]["value"]


async def test_top_customers_reports_quoted_value(client, customer_actor, manager):
    await _auto_approved(client, customer_actor, sku="TC-1")
    response = await client.get(
        "/api/v1/analytics/customers/top", headers=manager.headers
    )
    rows = response.json()
    assert rows[0]["customer_name"] == "Test Industries"
    assert rows[0]["quotations"] == 1


async def test_the_exception_breakdown_shows_what_drives_manual_review(
    client, customer_actor, manager
):
    await _needs_approval(client, customer_actor, sku="EX-1")
    await _needs_approval(client, customer_actor, sku="EX-2")

    response = await client.get("/api/v1/analytics/exceptions", headers=manager.headers)
    rows = response.json()
    assert rows[0]["type"] == "DISCOUNT_LIMIT_EXCEEDED"
    assert rows[0]["count"] == 2
    assert rows[0]["share_percent"] == 100.0


async def test_workflow_performance_reports_the_automation_rate(
    client, customer_actor, manager
):
    await _auto_approved(client, customer_actor, sku="WP-1")
    await _auto_approved(client, customer_actor, sku="WP-2")
    await _needs_approval(client, customer_actor, sku="WP-3")

    response = await client.get(
        "/api/v1/analytics/workflow/performance", headers=manager.headers
    )
    body = response.json()
    assert body["total_executions"] == 3
    assert body["by_outcome"]["COMPLETED"] == 2
    assert body["by_outcome"]["PENDING_APPROVAL"] == 1
    # One row per pipeline step.
    assert len(body["steps"]) == 8
    assert all(step["executions"] == 3 for step in body["steps"])


async def test_approval_performance_measures_turnaround(
    client, customer_actor, manager
):
    workflow = await _needs_approval(client, customer_actor, sku="AP-1")
    await client.post(
        f"/api/v1/approvals/{workflow['approval_id']}/decision",
        headers=manager.headers,
        json={"decision": ApprovalDecision.APPROVE.value},
    )

    response = await client.get(
        "/api/v1/analytics/approvals/performance", headers=manager.headers
    )
    body = response.json()
    assert body["decided"] == 1
    assert body["approved"] == 1
    assert body["within_sla"] == 1
    assert body["sla_compliance_percent"] == 100.0


async def test_approval_performance_is_safe_with_nothing_decided(client, manager):
    response = await client.get(
        "/api/v1/analytics/approvals/performance", headers=manager.headers
    )
    body = response.json()
    assert body["decided"] == 0
    assert body["sla_compliance_percent"] == 0.0


async def test_the_dashboard_returns_every_section(client, customer_actor, manager):
    await _auto_approved(client, customer_actor, sku="DB-1")

    response = await client.get("/api/v1/analytics/dashboard", headers=manager.headers)
    assert response.status_code == 200
    body = response.json()
    assert set(body) == {
        "overview",
        "request_trend",
        "revenue_trend",
        "top_products",
        "top_customers",
        "exception_breakdown",
        "approval_performance",
        "workflow_performance",
    }
    assert body["overview"]["quotations_issued"] == 1
    assert body["revenue_trend"][0]["quotations"] == 1


# ---------------------------------------------------------------------------
# Audit trail
# ---------------------------------------------------------------------------


async def test_the_workflow_writes_an_audit_trail(client, customer_actor, manager):
    workflow = await _auto_approved(client, customer_actor, sku="AU-1")
    request_id = workflow["request"]["id"]

    response = await client.get(
        f"/api/v1/audit-logs/quotation_request/{request_id}", headers=manager.headers
    )
    assert response.status_code == 200
    actions = [entry["action"] for entry in response.json()]
    assert AuditAction.REQUEST_CREATED.value in actions
    assert AuditAction.REQUEST_SUBMITTED.value in actions
    assert AuditAction.WORKFLOW_EXECUTED.value in actions


async def test_audit_entries_name_the_actor(client, customer_actor, manager):
    await _auto_approved(client, customer_actor, sku="AU-2")

    response = await client.get(
        "/api/v1/audit-logs",
        headers=manager.headers,
        params={"action": AuditAction.REQUEST_SUBMITTED.value},
    )
    entry = response.json()["items"][0]
    assert entry["actor_email"] == customer_actor.email
    assert entry["actor_role"] == "CUSTOMER"
    assert entry["entity_type"] == "quotation_request"
    assert entry["summary"]


async def test_an_approval_decision_is_audited(client, customer_actor, manager):
    workflow = await _needs_approval(client, customer_actor, sku="AU-3")
    await client.post(
        f"/api/v1/approvals/{workflow['approval_id']}/decision",
        headers=manager.headers,
        json={"decision": ApprovalDecision.APPROVE.value, "comments": "Fine"},
    )

    response = await client.get(
        "/api/v1/audit-logs",
        headers=manager.headers,
        params={"action": AuditAction.APPROVAL_DECIDED.value},
    )
    entry = response.json()["items"][0]
    assert entry["actor_email"] == manager.email
    assert entry["metadata"]["decision"] == "APPROVE"
    assert entry["metadata"]["quotation_id"]


async def test_a_product_update_records_a_field_level_diff(client, employee, manager):
    product_id = await create_product(sku="AU-DIFF", unit_price="1000.00")
    await client.patch(
        f"/api/v1/products/{product_id}",
        headers=employee.headers,
        json={"unit_price": 1250},
    )

    response = await client.get(
        f"/api/v1/audit-logs/product/{product_id}", headers=manager.headers
    )
    entry = next(
        item
        for item in response.json()
        if item["action"] == AuditAction.PRODUCT_UPDATED.value
    )
    assert entry["changes"]["unit_price"]["before"] == 1000.0
    assert entry["changes"]["unit_price"]["after"] == 1250.0


async def test_a_download_is_audited(client, customer_actor, manager):
    workflow = await _auto_approved(client, customer_actor, sku="AU-DL")
    await client.get(
        f"/api/v1/quotations/{workflow['quotation_id']}/pdf",
        headers=customer_actor.headers,
    )

    response = await client.get(
        "/api/v1/audit-logs",
        headers=manager.headers,
        params={"action": AuditAction.QUOTATION_DOWNLOADED.value},
    )
    assert response.json()["meta"]["total"] == 1


async def test_a_public_verification_is_audited(client, customer_actor, manager):
    from bson import ObjectId

    from app.db.mongo import Collections, get_collection

    workflow = await _auto_approved(client, customer_actor, sku="AU-VER")
    stored = await get_collection(Collections.QUOTATIONS).find_one(
        {"_id": ObjectId(workflow["quotation_id"])}
    )
    await client.get(f"/api/v1/verify/{stored['verification_code']}")

    response = await client.get(
        "/api/v1/audit-logs",
        headers=manager.headers,
        params={"action": AuditAction.QUOTATION_VERIFIED.value},
    )
    entry = response.json()["items"][0]
    assert entry["actor_role"] == "PUBLIC"
    assert entry["metadata"]["integrity_ok"] is True


async def test_the_audit_trail_has_no_write_endpoints(app):
    """The trail is append-only: nothing in the API can alter it."""
    audit_routes = [
        (route.path, sorted(route.methods))
        for route in app.routes
        if "audit-logs" in getattr(route, "path", "")
    ]
    assert audit_routes
    for path, methods in audit_routes:
        assert methods == ["GET"], f"{path} exposes {methods}"


# ---------------------------------------------------------------------------
# Configurable rule book
# ---------------------------------------------------------------------------


async def test_retuning_the_tier_table_changes_the_outcome(
    client, customer_actor, manager
):
    """The same request is auto-approved or escalated purely by configuration."""
    product_id = await create_product(
        sku="CFG-1", unit_price="1000.00", cost_price="100.00", stock_quantity=1000
    )
    items = [
        {"product_id": product_id, "quantity": 10, "requested_discount_percent": 9}
    ]

    before = await client.post(
        "/api/v1/quotation-requests",
        headers=customer_actor.headers,
        json={"items": items, "submit": True},
    )
    assert before.json()["workflow"]["requires_approval"] is True

    patched = await client.patch(
        "/api/v1/settings",
        headers=manager.headers,
        json={
            "discount_policy": {
                "tiers": [
                    {
                        "min_quantity": 1,
                        "max_quantity": None,
                        "max_discount_percent": 20,
                        "label": "all quantities",
                    }
                ]
            }
        },
    )
    assert patched.status_code == 200
    assert len(patched.json()["discount_policy"]["tiers"]) == 1

    after = await client.post(
        "/api/v1/quotation-requests",
        headers=customer_actor.headers,
        json={"items": items, "submit": True},
    )
    assert after.json()["workflow"]["requires_approval"] is False


async def test_a_nested_patch_does_not_wipe_its_siblings(client, manager):
    before = await client.get("/api/v1/settings", headers=manager.headers)
    original_name = before.json()["tax_policy"]["name"]

    response = await client.patch(
        "/api/v1/settings",
        headers=manager.headers,
        json={"tax_policy": {"rate_percent": 12}},
    )
    body = response.json()
    assert body["tax_policy"]["rate_percent"] == 12.0
    assert body["tax_policy"]["name"] == original_name


async def test_an_invalid_tier_table_is_rejected(client, manager):
    response = await client.patch(
        "/api/v1/settings",
        headers=manager.headers,
        json={"discount_policy": {"tiers": []}},
    )
    assert response.status_code == 422

    # The stored rule book is untouched.
    settings = await client.get("/api/v1/settings", headers=manager.headers)
    assert len(settings.json()["discount_policy"]["tiers"]) == 4


async def test_a_tax_change_applies_to_the_next_request(
    client, customer_actor, manager
):
    await client.patch(
        "/api/v1/settings",
        headers=manager.headers,
        json={"tax_policy": {"rate_percent": 10}},
    )
    product_id = await create_product(sku="CFG-TAX", unit_price="1000.00")

    response = await client.post(
        "/api/v1/quotation-requests",
        headers=customer_actor.headers,
        json={"items": [{"product_id": product_id, "quantity": 2}], "submit": True},
    )
    pricing = response.json()["workflow"]["request"]["pricing"]
    assert pricing["total_tax"] == 200.0
    assert pricing["final_amount"] == 2200.0


async def test_the_discount_policy_endpoint_summarises_the_limits(
    client, customer_actor
):
    response = await client.get(
        "/api/v1/settings/discount-policy", headers=customer_actor.headers
    )
    assert response.status_code == 200
    body = response.json()
    assert len(body["tiers"]) == 4
    assert body["tiers"][0]["max_discount_percent"] == 2.0
    assert body["absolute_max_discount_percent"] == 40.0
    assert body["tax_policy"]["rate_percent"] == 18.0


async def test_a_settings_change_is_audited(client, manager):
    await client.patch(
        "/api/v1/settings",
        headers=manager.headers,
        json={"approval_policy": {"order_value_threshold": 777000}},
    )
    response = await client.get(
        "/api/v1/audit-logs",
        headers=manager.headers,
        params={"action": AuditAction.SETTINGS_UPDATED.value},
    )
    assert response.json()["meta"]["total"] == 1


# ---------------------------------------------------------------------------
# Service endpoints
# ---------------------------------------------------------------------------


async def test_the_health_endpoint_reports_the_database(client):
    response = await client.get("/health")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert body["database"]["connected"] is True


async def test_the_service_banner_is_public(client):
    response = await client.get("/")
    assert response.status_code == 200
    assert response.json()["name"] == "QuoteFlow"


async def test_the_openapi_schema_is_served(client):
    response = await client.get("/openapi.json")
    assert response.status_code == 200
    assert response.json()["info"]["title"] == "QuoteFlow API"
