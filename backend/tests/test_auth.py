"""Authentication, token handling and role-based access control."""

from app.db.mongo import Collections, get_collection
from app.models.enums import UserRole
from tests.conftest import TEST_PASSWORD, auth, create_user

REGISTRATION = {
    "email": "new.buyer@test.example",
    "password": "StrongPassw0rd!",
    "full_name": "New Buyer",
    "company_name": "Newco Fabrication",
    "phone": "+91 90000 11111",
    "city": "Pune",
    "state": "Maharashtra",
    "postal_code": "411001",
    "address_line1": "4 Industrial Lane",
}


async def test_registration_creates_a_user_and_a_customer_record(client):
    response = await client.post("/api/v1/auth/register", json=REGISTRATION)
    assert response.status_code == 201, response.text

    body = response.json()
    assert body["user"]["role"] == UserRole.CUSTOMER.value
    assert body["user"]["customer_id"]
    assert body["access_token"] and body["refresh_token"]

    customer = await get_collection(Collections.CUSTOMERS).find_one(
        {"email": REGISTRATION["email"]}
    )
    assert customer is not None
    assert customer["company_name"] == "Newco Fabrication"
    assert customer["code"].startswith("CUST-")


async def test_registration_rejects_a_duplicate_email(client):
    await client.post("/api/v1/auth/register", json=REGISTRATION)
    response = await client.post("/api/v1/auth/register", json=REGISTRATION)
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "conflict"


async def test_registration_enforces_a_minimum_password_length(client):
    response = await client.post(
        "/api/v1/auth/register", json={**REGISTRATION, "password": "short"}
    )
    assert response.status_code == 422


async def test_password_is_never_returned_or_stored_in_clear(client):
    response = await client.post("/api/v1/auth/register", json=REGISTRATION)
    assert "password" not in response.text
    assert REGISTRATION["password"] not in response.text

    stored = await get_collection(Collections.USERS).find_one(
        {"email": REGISTRATION["email"]}
    )
    assert stored["password_hash"] != REGISTRATION["password"]
    assert stored["password_hash"].startswith("$2")


async def test_login_succeeds_and_records_the_timestamp(client):
    user = await create_user(email="login@test.example", role=UserRole.SALES_EMPLOYEE)
    response = await client.post(
        "/api/v1/auth/login",
        json={"email": user["email"], "password": TEST_PASSWORD},
    )
    assert response.status_code == 200
    assert response.json()["token_type"] == "bearer"

    stored = await get_collection(Collections.USERS).find_one({"email": user["email"]})
    assert stored["last_login_at"] is not None


async def test_login_with_a_wrong_password_is_rejected(client):
    user = await create_user(email="wrong@test.example", role=UserRole.SALES_EMPLOYEE)
    response = await client.post(
        "/api/v1/auth/login", json={"email": user["email"], "password": "not-it"}
    )
    assert response.status_code == 401


async def test_login_with_an_unknown_email_gives_the_same_error(client):
    """The message must not reveal whether the account exists."""
    response = await client.post(
        "/api/v1/auth/login",
        json={"email": "nobody@test.example", "password": TEST_PASSWORD},
    )
    assert response.status_code == 401
    assert response.json()["error"]["message"] == (
        "The email address or password is incorrect."
    )


async def test_suspended_account_cannot_sign_in(client):
    user = await create_user(email="held@test.example", role=UserRole.SALES_EMPLOYEE)
    await get_collection(Collections.USERS).update_one(
        {"email": user["email"]}, {"$set": {"status": "SUSPENDED"}}
    )
    response = await client.post(
        "/api/v1/auth/login",
        json={"email": user["email"], "password": TEST_PASSWORD},
    )
    assert response.status_code == 401
    assert "suspended" in response.json()["error"]["message"].lower()


async def test_suspension_takes_effect_on_an_already_issued_token(client, employee):
    """The user is re-read on every request, so a suspension is immediate."""
    assert (await client.get("/api/v1/auth/me", headers=employee.headers)).status_code == 200

    await get_collection(Collections.USERS).update_one(
        {"email": employee.email}, {"$set": {"status": "SUSPENDED"}}
    )
    response = await client.get("/api/v1/auth/me", headers=employee.headers)
    assert response.status_code == 401


async def test_refresh_token_yields_a_new_access_token(client):
    user = await create_user(email="refresh@test.example", role=UserRole.SALES_MANAGER)
    login = await client.post(
        "/api/v1/auth/login",
        json={"email": user["email"], "password": TEST_PASSWORD},
    )
    refresh_token = login.json()["refresh_token"]

    response = await client.post(
        "/api/v1/auth/refresh", json={"refresh_token": refresh_token}
    )
    assert response.status_code == 200
    assert response.json()["access_token"]


async def test_an_access_token_is_not_accepted_as_a_refresh_token(client, manager):
    response = await client.post(
        "/api/v1/auth/refresh", json={"refresh_token": manager.token}
    )
    assert response.status_code == 401


async def test_a_garbage_token_is_rejected(client):
    response = await client.get("/api/v1/auth/me", headers=auth("not-a-jwt"))
    assert response.status_code == 401


async def test_missing_credentials_are_rejected(client):
    response = await client.get("/api/v1/auth/me")
    assert response.status_code == 401
    assert response.json()["error"]["code"] == "authentication_failed"


async def test_me_returns_the_linked_customer_for_a_customer_account(
    client, customer_actor
):
    response = await client.get("/api/v1/auth/me", headers=customer_actor.headers)
    assert response.status_code == 200
    body = response.json()
    assert body["user"]["role"] == UserRole.CUSTOMER.value
    assert body["customer"]["code"] == "CUST-TEST-1"


async def test_me_has_no_customer_for_staff(client, employee):
    response = await client.get("/api/v1/auth/me", headers=employee.headers)
    assert response.json()["customer"] is None


async def test_password_change_invalidates_the_old_password(client, employee):
    response = await client.post(
        "/api/v1/auth/change-password",
        headers=employee.headers,
        json={"current_password": TEST_PASSWORD, "new_password": "BrandNewPass1!"},
    )
    assert response.status_code == 204

    old = await client.post(
        "/api/v1/auth/login",
        json={"email": employee.email, "password": TEST_PASSWORD},
    )
    assert old.status_code == 401

    new = await client.post(
        "/api/v1/auth/login",
        json={"email": employee.email, "password": "BrandNewPass1!"},
    )
    assert new.status_code == 200


async def test_password_change_requires_the_current_password(client, employee):
    response = await client.post(
        "/api/v1/auth/change-password",
        headers=employee.headers,
        json={"current_password": "guessing", "new_password": "BrandNewPass1!"},
    )
    assert response.status_code == 401


# ---------------------------------------------------------------------------
# Role-based access control
# ---------------------------------------------------------------------------


async def test_manager_can_create_staff_accounts(client, manager):
    response = await client.post(
        "/api/v1/auth/staff",
        headers=manager.headers,
        json={
            "email": "newstaff@test.example",
            "password": "StaffPassw0rd!",
            "full_name": "New Staff",
            "role": UserRole.SALES_EMPLOYEE.value,
        },
    )
    assert response.status_code == 201
    assert response.json()["role"] == UserRole.SALES_EMPLOYEE.value


async def test_employee_cannot_create_staff_accounts(client, employee):
    response = await client.post(
        "/api/v1/auth/staff",
        headers=employee.headers,
        json={
            "email": "sneaky@test.example",
            "password": "StaffPassw0rd!",
            "full_name": "Sneaky",
            "role": UserRole.SALES_MANAGER.value,
        },
    )
    assert response.status_code == 403
    assert response.json()["error"]["code"] == "permission_denied"


async def test_staff_endpoint_will_not_mint_a_customer_account(client, manager):
    response = await client.post(
        "/api/v1/auth/staff",
        headers=manager.headers,
        json={
            "email": "viacustomer@test.example",
            "password": "StaffPassw0rd!",
            "full_name": "Wrong Route",
            "role": UserRole.CUSTOMER.value,
        },
    )
    assert response.status_code == 403


async def test_customer_cannot_reach_staff_only_endpoints(client, customer_actor):
    for path in (
        "/api/v1/customers",
        "/api/v1/products",
        "/api/v1/analytics/overview",
        "/api/v1/audit-logs",
    ):
        response = await client.get(path, headers=customer_actor.headers)
        assert response.status_code == 403, path


async def test_employee_cannot_reach_manager_only_endpoints(client, employee):
    for path in (
        "/api/v1/analytics/dashboard",
        "/api/v1/audit-logs",
        "/api/v1/analytics/exceptions",
    ):
        response = await client.get(path, headers=employee.headers)
        assert response.status_code == 403, path


async def test_every_role_may_read_the_rule_book(client, customer_actor, employee, manager):
    for actor in (customer_actor, employee, manager):
        response = await client.get("/api/v1/settings", headers=actor.headers)
        assert response.status_code == 200


async def test_only_a_manager_may_change_the_rule_book(client, employee, manager):
    patch = {"approval_policy": {"order_value_threshold": 123456}}

    denied = await client.patch(
        "/api/v1/settings", headers=employee.headers, json=patch
    )
    assert denied.status_code == 403

    allowed = await client.patch(
        "/api/v1/settings", headers=manager.headers, json=patch
    )
    assert allowed.status_code == 200
    assert allowed.json()["approval_policy"]["order_value_threshold"] == 123456


async def test_me_returns_the_same_customer_shape_as_the_customer_endpoints(
    client, customer_actor, employee
):
    """`/auth/me` must include available_credit.

    Regression test: it used to return the bare Customer model, whose
    available_credit is a Python property that Pydantic does not serialise, so
    the client had no figure to display.
    """
    profile = await client.get("/api/v1/auth/me", headers=customer_actor.headers)
    assert profile.status_code == 200
    customer = profile.json()["customer"]

    listed = await client.get(
        f"/api/v1/customers/{customer_actor.customer_id}", headers=employee.headers
    )
    assert listed.status_code == 200

    # Same keys, so a client can use either response interchangeably.
    assert set(customer) == set(listed.json())
    assert "available_credit" in customer
    assert customer["available_credit"] == (
        customer["credit_limit"] - customer["outstanding_amount"]
    )
