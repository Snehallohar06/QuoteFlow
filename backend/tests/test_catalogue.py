"""Product catalogue, availability checks and customer management."""

from app.models.enums import CustomerStatus, CustomerTier, ProductStatus
from tests.conftest import create_product

NEW_PRODUCT = {
    "sku": "api-001",
    "name": "API Created Widget",
    "category": "Testing",
    "unit_price": 1500,
    "cost_price": 900,
    "stock_quantity": 50,
    "reorder_level": 10,
    "lead_time_days": 7,
}


# ---------------------------------------------------------------------------
# Catalogue
# ---------------------------------------------------------------------------


async def test_the_catalogue_hides_discontinued_products(client, customer_actor):
    await create_product(sku="LIVE-1", name="Live Widget")
    await create_product(
        sku="DEAD-1", name="Dead Widget", status=ProductStatus.DISCONTINUED
    )

    response = await client.get(
        "/api/v1/products/catalogue", headers=customer_actor.headers
    )
    assert response.status_code == 200
    skus = [item["sku"] for item in response.json()["items"]]
    assert "LIVE-1" in skus
    assert "DEAD-1" not in skus


async def test_the_catalogue_hides_cost_price_from_customers(client, customer_actor):
    await create_product(sku="COST-1", unit_price="1000.00", cost_price="640.00")
    response = await client.get(
        "/api/v1/products/catalogue", headers=customer_actor.headers
    )
    item = response.json()["items"][0]
    assert "cost_price" not in item
    assert "640" not in response.text


async def test_staff_do_see_cost_price(client, employee):
    await create_product(sku="COST-2", unit_price="1000.00", cost_price="640.00")
    response = await client.get("/api/v1/products", headers=employee.headers)
    assert response.json()["items"][0]["cost_price"] == 640.0


async def test_the_catalogue_shows_the_discount_a_customer_may_request(
    client, customer_actor
):
    await create_product(sku="ENT-1")
    response = await client.get(
        "/api/v1/products/catalogue", headers=customer_actor.headers
    )
    # Standard tier, quantity of one: the 1-5 band allows 2%.
    assert response.json()["items"][0]["indicative_max_discount_percent"] == 2.0


async def test_a_gold_customer_sees_their_tier_bonus(client):
    from app.models.enums import UserRole
    from tests.conftest import Actor, _login, create_customer, create_user

    customer_id = await create_customer(
        code="CUST-GOLD", email="gold@test.example", tier=CustomerTier.GOLD
    )
    user = await create_user(
        email="gold.buyer@test.example",
        role=UserRole.CUSTOMER,
        customer_id=customer_id,
    )
    actor = Actor(user["id"], user["email"], await _login(client, user["email"]))

    await create_product(sku="GOLD-1")
    response = await client.get("/api/v1/products/catalogue", headers=actor.headers)
    # 2% band + 2% GOLD bonus.
    assert response.json()["items"][0]["indicative_max_discount_percent"] == 4.0


async def test_a_product_cap_lowers_the_figure_shown(client, customer_actor):
    await create_product(sku="CAP-1", max_discount_percent="1")
    response = await client.get(
        "/api/v1/products/catalogue", headers=customer_actor.headers
    )
    assert response.json()["items"][0]["indicative_max_discount_percent"] == 1.0


async def test_low_stock_is_flagged(client, customer_actor):
    await create_product(sku="LOW-1", stock_quantity=3, reorder_level=10)
    await create_product(sku="FULL-1", stock_quantity=300, reorder_level=10)

    response = await client.get(
        "/api/v1/products/catalogue", headers=customer_actor.headers
    )
    flags = {item["sku"]: item["low_stock"] for item in response.json()["items"]}
    assert flags["LOW-1"] is True
    assert flags["FULL-1"] is False


async def test_the_catalogue_can_be_searched_and_filtered(client, customer_actor):
    await create_product(sku="PUMP-A", name="Centrifugal Pump", category="Pumps")
    await create_product(sku="VALVE-A", name="Gate Valve", category="Valves")

    search = await client.get(
        "/api/v1/products/catalogue",
        headers=customer_actor.headers,
        params={"search": "centrifugal"},
    )
    assert [item["sku"] for item in search.json()["items"]] == ["PUMP-A"]

    filtered = await client.get(
        "/api/v1/products/catalogue",
        headers=customer_actor.headers,
        params={"category": "Valves"},
    )
    assert [item["sku"] for item in filtered.json()["items"]] == ["VALVE-A"]

    categories = await client.get(
        "/api/v1/products/categories", headers=customer_actor.headers
    )
    assert {row["category"] for row in categories.json()} == {"Pumps", "Valves"}


async def test_the_catalogue_paginates(client, customer_actor):
    for index in range(7):
        await create_product(sku=f"PAGE-{index}", name=f"Paged Widget {index}")

    response = await client.get(
        "/api/v1/products/catalogue",
        headers=customer_actor.headers,
        params={"page": 2, "page_size": 3},
    )
    body = response.json()
    assert body["meta"] == {
        "total": 7,
        "page": 2,
        "page_size": 3,
        "total_pages": 3,
    }
    assert len(body["items"]) == 3


# ---------------------------------------------------------------------------
# Availability pre-check
# ---------------------------------------------------------------------------


async def test_the_availability_check_reports_each_line(client, customer_actor):
    plenty = await create_product(sku="AVL-FULL", stock_quantity=100)
    partial = await create_product(
        sku="AVL-PART", stock_quantity=4, lead_time_days=14
    )
    none_left = await create_product(sku="AVL-NONE", stock_quantity=0)

    response = await client.post(
        "/api/v1/products/check-availability",
        headers=customer_actor.headers,
        json={
            "items": [
                {"product_id": plenty, "quantity": 10},
                {"product_id": partial, "quantity": 10},
                {"product_id": none_left, "quantity": 10},
            ]
        },
    )
    assert response.status_code == 200
    body = response.json()
    assert body["all_available"] is False

    lines = {line["sku"]: line for line in body["lines"]}
    assert lines["AVL-FULL"]["status"] == "IN_STOCK"
    assert lines["AVL-FULL"]["shortfall"] == 0
    assert lines["AVL-PART"]["status"] == "PARTIAL"
    assert lines["AVL-PART"]["shortfall"] == 6
    assert lines["AVL-PART"]["lead_time_days"] == 14
    assert "backordered" in lines["AVL-PART"]["message"]
    assert lines["AVL-NONE"]["status"] == "OUT_OF_STOCK"
    assert lines["AVL-NONE"]["shortfall"] == 10


async def test_everything_in_stock_reports_all_available(client, customer_actor):
    product_id = await create_product(sku="AVL-OK", stock_quantity=100)
    response = await client.post(
        "/api/v1/products/check-availability",
        headers=customer_actor.headers,
        json={"items": [{"product_id": product_id, "quantity": 5}]},
    )
    assert response.json()["all_available"] is True


async def test_the_availability_check_404s_on_an_unknown_product(
    client, customer_actor
):
    response = await client.post(
        "/api/v1/products/check-availability",
        headers=customer_actor.headers,
        json={"items": [{"product_id": "000000000000000000000000", "quantity": 1}]},
    )
    assert response.status_code == 404
    assert response.json()["error"]["details"]["missing_product_ids"]


# ---------------------------------------------------------------------------
# Product management
# ---------------------------------------------------------------------------


async def test_a_manager_can_create_a_product_and_the_sku_is_normalised(
    client, manager
):
    response = await client.post(
        "/api/v1/products", headers=manager.headers, json=NEW_PRODUCT
    )
    assert response.status_code == 201
    body = response.json()
    assert body["sku"] == "API-001"
    assert body["available_quantity"] == 50


async def test_an_employee_cannot_create_a_product_directly(client, employee):
    """They are pointed at the approval queue rather than simply refused."""
    response = await client.post(
        "/api/v1/products", headers=employee.headers, json=NEW_PRODUCT
    )
    assert response.status_code == 403
    error = response.json()["error"]
    assert "sales manager" in error["message"]
    assert error["details"]["submit_route"] == "/api/v1/master-data-requests/products"


async def test_a_duplicate_sku_is_a_conflict(client, manager):
    await client.post("/api/v1/products", headers=manager.headers, json=NEW_PRODUCT)
    response = await client.post(
        "/api/v1/products", headers=manager.headers, json=NEW_PRODUCT
    )
    assert response.status_code == 409


async def test_a_customer_cannot_create_a_product(client, customer_actor):
    response = await client.post(
        "/api/v1/products", headers=customer_actor.headers, json=NEW_PRODUCT
    )
    assert response.status_code == 403


async def test_a_zero_unit_price_is_rejected(client, manager):
    response = await client.post(
        "/api/v1/products",
        headers=manager.headers,
        json={**NEW_PRODUCT, "unit_price": 0},
    )
    assert response.status_code == 422


async def test_reserved_stock_cannot_exceed_stock(client, manager):
    response = await client.post(
        "/api/v1/products",
        headers=manager.headers,
        json={**NEW_PRODUCT, "stock_quantity": 5, "reserved_quantity": 9},
    )
    assert response.status_code == 409
    assert "reserved quantity" in response.json()["error"]["message"]


async def test_a_stock_movement_is_applied(client, employee):
    product_id = await create_product(sku="MOVE-1", stock_quantity=20)

    up = await client.post(
        f"/api/v1/products/{product_id}/stock",
        headers=employee.headers,
        json={"delta": 15, "reason": "Goods received"},
    )
    assert up.json()["stock_quantity"] == 35

    down = await client.post(
        f"/api/v1/products/{product_id}/stock",
        headers=employee.headers,
        json={"delta": -5},
    )
    assert down.json()["stock_quantity"] == 30


async def test_stock_cannot_be_driven_negative(client, employee):
    product_id = await create_product(sku="MOVE-2", stock_quantity=3)
    response = await client.post(
        f"/api/v1/products/{product_id}/stock",
        headers=employee.headers,
        json={"delta": -10},
    )
    assert response.status_code == 409
    assert "below zero" in response.json()["error"]["message"]


async def test_stock_cannot_fall_below_the_reserved_quantity(client, employee):
    product_id = await create_product(
        sku="MOVE-3", stock_quantity=10, reserved_quantity=8
    )
    response = await client.post(
        f"/api/v1/products/{product_id}/stock",
        headers=employee.headers,
        json={"delta": -5},
    )
    assert response.status_code == 409
    assert "reserved quantity" in response.json()["error"]["message"]


async def test_deleting_a_product_only_discontinues_it(client, manager):
    product_id = await create_product(sku="SOFT-1")

    response = await client.delete(
        f"/api/v1/products/{product_id}", headers=manager.headers
    )
    assert response.status_code == 200
    assert response.json()["status"] == ProductStatus.DISCONTINUED.value

    # Still retrievable, because historical quotations reference it.
    still_there = await client.get(
        f"/api/v1/products/{product_id}", headers=manager.headers
    )
    assert still_there.status_code == 200


async def test_an_employee_cannot_discontinue_a_product(client, employee):
    product_id = await create_product(sku="SOFT-2")
    response = await client.delete(
        f"/api/v1/products/{product_id}", headers=employee.headers
    )
    assert response.status_code == 403


async def test_an_unknown_product_is_a_404(client, employee):
    response = await client.get(
        "/api/v1/products/000000000000000000000000", headers=employee.headers
    )
    assert response.status_code == 404


# ---------------------------------------------------------------------------
# Customer management
# ---------------------------------------------------------------------------


NEW_CUSTOMER = {
    "company_name": "Created By API",
    "contact_name": "API Contact",
    "email": "api.customer@test.example",
    "phone": "+91 90000 22222",
    "tier": CustomerTier.SILVER.value,
    "credit_limit": 250000,
}


async def test_a_manager_can_create_a_customer_with_a_generated_code(client, manager):
    response = await client.post(
        "/api/v1/customers", headers=manager.headers, json=NEW_CUSTOMER
    )
    assert response.status_code == 201
    body = response.json()
    assert body["code"].startswith("CUST-")
    assert body["tier"] == CustomerTier.SILVER.value
    assert body["credit_limit"] == 250000.0
    assert body["available_credit"] == 250000.0


async def test_a_duplicate_customer_email_is_a_conflict(client, manager):
    await client.post("/api/v1/customers", headers=manager.headers, json=NEW_CUSTOMER)
    response = await client.post(
        "/api/v1/customers", headers=manager.headers, json=NEW_CUSTOMER
    )
    assert response.status_code == 409


async def test_an_employee_cannot_create_a_customer_directly(client, employee):
    """Adding a customer needs a manager's approval; see the master-data queue."""
    response = await client.post(
        "/api/v1/customers", headers=employee.headers, json=NEW_CUSTOMER
    )
    assert response.status_code == 403
    details = response.json()["error"]["details"]
    assert details["submit_route"] == "/api/v1/master-data-requests/customers"


async def test_a_customer_can_be_updated(client, employee, customer_actor):
    response = await client.patch(
        f"/api/v1/customers/{customer_actor.customer_id}",
        headers=employee.headers,
        json={"tier": CustomerTier.PLATINUM.value, "credit_limit": 900000},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["tier"] == CustomerTier.PLATINUM.value
    assert body["credit_limit"] == 900000.0


async def test_only_a_manager_can_block_a_customer(
    client, employee, manager, customer_actor
):
    denied = await client.post(
        f"/api/v1/customers/{customer_actor.customer_id}/status",
        headers=employee.headers,
        params={"new_status": CustomerStatus.BLOCKED.value},
    )
    assert denied.status_code == 403

    allowed = await client.post(
        f"/api/v1/customers/{customer_actor.customer_id}/status",
        headers=manager.headers,
        params={"new_status": CustomerStatus.BLOCKED.value},
    )
    assert allowed.status_code == 200
    assert allowed.json()["status"] == CustomerStatus.BLOCKED.value


async def test_the_customer_summary_reports_activity(
    client, employee, customer_actor
):
    product_id = await create_product(sku="SUMMARY-1", unit_price="1000.00")
    await client.post(
        "/api/v1/quotation-requests",
        headers=customer_actor.headers,
        json={"items": [{"product_id": product_id, "quantity": 2}], "submit": True},
    )

    response = await client.get(
        f"/api/v1/customers/{customer_actor.customer_id}/summary",
        headers=employee.headers,
    )
    assert response.status_code == 200
    body = response.json()
    assert body["total_requests"] == 1
    assert body["requests_by_status"]["COMPLETED"] == 1
    assert body["total_quotations"] == 1
    assert body["quoted_value"] == 2360.0
    assert body["last_request_at"] is not None


async def test_an_issued_quotation_consumes_credit(client, employee, customer_actor):
    await client.patch(
        f"/api/v1/customers/{customer_actor.customer_id}",
        headers=employee.headers,
        json={"credit_limit": 100000},
    )
    product_id = await create_product(sku="CREDIT-1", unit_price="1000.00")
    await client.post(
        "/api/v1/quotation-requests",
        headers=customer_actor.headers,
        json={"items": [{"product_id": product_id, "quantity": 2}], "submit": True},
    )

    response = await client.get(
        f"/api/v1/customers/{customer_actor.customer_id}", headers=employee.headers
    )
    body = response.json()
    assert body["outstanding_amount"] == 2360.0
    assert body["available_credit"] == 97640.0


async def test_customers_can_be_searched(client, employee, manager):
    await client.post(
        "/api/v1/customers",
        headers=manager.headers,
        json={**NEW_CUSTOMER, "company_name": "Findable Fabricators"},
    )
    response = await client.get(
        "/api/v1/customers", headers=employee.headers, params={"search": "findable"}
    )
    assert response.json()["meta"]["total"] == 1
