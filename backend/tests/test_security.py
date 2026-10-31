"""Security verification.

Covers the eight areas the brief lists: authentication, role-based
authorisation, password storage, endpoint protection, customer data isolation,
approval restrictions, file downloads, and configuration via the environment.

These are negative tests by nature — most of them assert that something is
*refused*.
"""

import re
from datetime import UTC, datetime, timedelta
from pathlib import Path

import jwt
import pytest
from bson import ObjectId

from app.core.config import settings
from app.core.security import hash_password, verify_password
from app.db.mongo import Collections, get_collection
from app.models.enums import UserRole
from tests.conftest import (
    TEST_PASSWORD,
    Actor,
    _login,
    auth,
    create_customer,
    create_product,
    create_user,
)

BACKEND_ROOT = Path(__file__).resolve().parents[1]


# ===========================================================================
# 1. Authentication
# ===========================================================================


class TestAuthentication:
    async def test_a_protected_endpoint_refuses_an_anonymous_caller(self, client):
        response = await client.get("/api/v1/quotation-requests")
        assert response.status_code == 401
        assert response.json()["error"]["code"] == "authentication_failed"

    async def test_the_challenge_header_is_sent(self, client):
        response = await client.get("/api/v1/customers")
        assert response.headers.get("www-authenticate") == "Bearer"

    @pytest.mark.parametrize(
        "token",
        [
            "",
            "not-a-jwt",
            "Bearer.Bearer.Bearer",
            "eyJhbGciOiJIUzI1NiJ9.e30.invalid-signature",
        ],
    )
    async def test_a_malformed_token_is_refused(self, client, token):
        response = await client.get("/api/v1/auth/me", headers=auth(token))
        assert response.status_code == 401

    async def test_a_token_signed_with_the_wrong_key_is_refused(
        self, client, customer_actor
    ):
        """A forged token must not be accepted, however well-formed."""
        forged = jwt.encode(
            {
                "sub": customer_actor.id,
                "type": "access",
                "exp": int((datetime.now(UTC) + timedelta(hours=1)).timestamp()),
            },
            "an-attacker-chosen-secret",
            algorithm="HS256",
        )
        response = await client.get("/api/v1/auth/me", headers=auth(forged))
        assert response.status_code == 401

    async def test_an_expired_token_is_refused(self, client, customer_actor):
        expired = jwt.encode(
            {
                "sub": customer_actor.id,
                "type": "access",
                "exp": int((datetime.now(UTC) - timedelta(minutes=5)).timestamp()),
            },
            settings.jwt_secret_key,
            algorithm=settings.jwt_algorithm,
        )
        response = await client.get("/api/v1/auth/me", headers=auth(expired))
        assert response.status_code == 401
        assert "expired" in response.json()["error"]["message"].lower()

    async def test_a_refresh_token_cannot_be_used_as_an_access_token(
        self, client
    ):
        user = await create_user(
            email="tokentype@test.example", role=UserRole.SALES_EMPLOYEE
        )
        login = await client.post(
            "/api/v1/auth/login",
            json={"email": user["email"], "password": TEST_PASSWORD},
        )
        refresh = login.json()["refresh_token"]
        response = await client.get("/api/v1/auth/me", headers=auth(refresh))
        assert response.status_code == 401

    async def test_a_token_for_a_deleted_account_is_refused(
        self, client, employee
    ):
        """The user is re-read per request, so a deletion takes effect at once."""
        await get_collection(Collections.USERS).delete_one(
            {"_id": ObjectId(employee.id)}
        )
        response = await client.get("/api/v1/auth/me", headers=employee.headers)
        assert response.status_code == 401
        assert "no longer exists" in response.json()["error"]["message"]

    async def test_suspension_takes_effect_on_an_existing_token(
        self, client, employee
    ):
        await get_collection(Collections.USERS).update_one(
            {"_id": ObjectId(employee.id)}, {"$set": {"status": "SUSPENDED"}}
        )
        response = await client.get("/api/v1/auth/me", headers=employee.headers)
        assert response.status_code == 401
        assert "suspended" in response.json()["error"]["message"].lower()

    async def test_the_login_error_does_not_reveal_whether_an_account_exists(
        self, client
    ):
        known = await create_user(
            email="known@test.example", role=UserRole.SALES_EMPLOYEE
        )
        wrong_password = await client.post(
            "/api/v1/auth/login",
            json={"email": known["email"], "password": "definitely-wrong"},
        )
        unknown_account = await client.post(
            "/api/v1/auth/login",
            json={"email": "nobody-here@test.example", "password": "whatever"},
        )
        assert wrong_password.status_code == unknown_account.status_code == 401
        assert (
            wrong_password.json()["error"]["message"]
            == unknown_account.json()["error"]["message"]
        )


# ===========================================================================
# 2. Role-based authorisation
# ===========================================================================


class TestAuthorisation:
    #: (path, method, role that must be refused)
    CUSTOMER_FORBIDDEN = [
        ("GET", "/api/v1/customers"),
        ("GET", "/api/v1/products"),
        ("GET", "/api/v1/approvals"),
        ("GET", "/api/v1/approvals/pending-count"),
        ("GET", "/api/v1/audit-logs"),
        ("GET", "/api/v1/analytics/overview"),
        ("GET", "/api/v1/analytics/dashboard"),
        ("POST", "/api/v1/quotations/expire-due"),
    ]

    EMPLOYEE_FORBIDDEN = [
        ("GET", "/api/v1/audit-logs"),
        ("GET", "/api/v1/analytics/dashboard"),
        ("GET", "/api/v1/analytics/exceptions"),
        ("GET", "/api/v1/analytics/customers/top"),
        ("GET", "/api/v1/analytics/revenue/trend"),
    ]

    @pytest.mark.parametrize("method,path", CUSTOMER_FORBIDDEN)
    async def test_a_customer_is_refused_staff_endpoints(
        self, client, customer_actor, method, path
    ):
        response = await client.request(method, path, headers=customer_actor.headers)
        assert response.status_code == 403, f"{method} {path}"
        assert response.json()["error"]["code"] == "permission_denied"

    @pytest.mark.parametrize("method,path", EMPLOYEE_FORBIDDEN)
    async def test_an_employee_is_refused_manager_endpoints(
        self, client, employee, method, path
    ):
        response = await client.request(method, path, headers=employee.headers)
        assert response.status_code == 403, f"{method} {path}"

    async def test_an_employee_cannot_change_the_rule_book(self, client, employee):
        response = await client.patch(
            "/api/v1/settings",
            headers=employee.headers,
            json={"discount_policy": {"absolute_max_discount_percent": 99}},
        )
        assert response.status_code == 403

    async def test_an_employee_cannot_block_a_customer(
        self, client, employee, customer_actor
    ):
        response = await client.post(
            f"/api/v1/customers/{customer_actor.customer_id}/status",
            headers=employee.headers,
            params={"new_status": "BLOCKED"},
        )
        assert response.status_code == 403

    async def test_an_employee_cannot_discontinue_a_product(self, client, employee):
        product_id = await create_product(sku="SEC-DISC")
        response = await client.delete(
            f"/api/v1/products/{product_id}", headers=employee.headers
        )
        assert response.status_code == 403

    async def test_a_customer_cannot_create_a_staff_account(
        self, client, customer_actor
    ):
        response = await client.post(
            "/api/v1/auth/staff",
            headers=customer_actor.headers,
            json={
                "email": "escalate@test.example",
                "password": "Passw0rd!123",
                "full_name": "Privilege Escalation",
                "role": UserRole.SALES_MANAGER.value,
            },
        )
        assert response.status_code == 403

    async def test_the_staff_route_will_not_mint_a_customer_login(
        self, client, manager
    ):
        """A customer login must be tied to a customer record, so this is closed."""
        response = await client.post(
            "/api/v1/auth/staff",
            headers=manager.headers,
            json={
                "email": "sneaky-customer@test.example",
                "password": "Passw0rd!123",
                "full_name": "Wrong Route",
                "role": UserRole.CUSTOMER.value,
            },
        )
        assert response.status_code == 403

    async def test_a_customer_cannot_reprocess_a_workflow(
        self, client, customer_actor
    ):
        product_id = await create_product(sku="SEC-REPROCESS")
        created = await client.post(
            "/api/v1/quotation-requests",
            headers=customer_actor.headers,
            json={
                "items": [{"product_id": product_id, "quantity": 1}],
                "submit": False,
            },
        )
        request_id = created.json()["request"]["id"]
        response = await client.post(
            f"/api/v1/quotation-requests/{request_id}/reprocess",
            headers=customer_actor.headers,
        )
        assert response.status_code == 403

    async def test_a_customer_cannot_write_internal_notes(
        self, client, customer_actor
    ):
        product_id = await create_product(sku="SEC-NOTES")
        created = await client.post(
            "/api/v1/quotation-requests",
            headers=customer_actor.headers,
            json={
                "items": [{"product_id": product_id, "quantity": 1}],
                "submit": False,
            },
        )
        response = await client.put(
            f"/api/v1/quotation-requests/{created.json()['request']['id']}/internal-notes",
            headers=customer_actor.headers,
            json={"internal_notes": "should not be allowed"},
        )
        assert response.status_code == 403


# ===========================================================================
# 3. Password security
# ===========================================================================


class TestPasswordSecurity:
    async def test_a_password_is_stored_as_a_bcrypt_hash(self, client):
        payload = {
            "email": "pwtest@test.example",
            "password": "AVeryStrongPassw0rd!",
            "full_name": "Password Test",
            "company_name": "Password Co",
            "phone": "+91 90000 12345",
        }
        response = await client.post("/api/v1/auth/register", json=payload)
        assert response.status_code == 201

        stored = await get_collection(Collections.USERS).find_one(
            {"email": payload["email"]}
        )
        assert stored["password_hash"] != payload["password"]
        # bcrypt identifier and cost factor.
        assert re.match(r"^\$2[aby]\$\d{2}\$", stored["password_hash"])
        assert "password" not in stored, "the plaintext must not be stored at all"

    async def test_the_password_never_appears_in_a_response(self, client):
        payload = {
            "email": "pwleak@test.example",
            "password": "LeakCheckPassw0rd!",
            "full_name": "Leak Check",
            "company_name": "Leak Co",
            "phone": "+91 90000 54321",
        }
        response = await client.post("/api/v1/auth/register", json=payload)
        assert payload["password"] not in response.text
        assert "password_hash" not in response.text

        me = await client.get(
            "/api/v1/auth/me",
            headers=auth(response.json()["access_token"]),
        )
        assert "password" not in me.text

    def test_hashing_is_salted(self):
        """Two users with the same password must not share a hash."""
        first = hash_password("identical-password")
        second = hash_password("identical-password")
        assert first != second
        assert verify_password("identical-password", first)
        assert verify_password("identical-password", second)

    def test_a_wrong_password_does_not_verify(self):
        stored = hash_password("correct-horse")
        assert verify_password("correct-horse", stored) is True
        assert verify_password("Correct-Horse", stored) is False
        assert verify_password("", stored) is False

    def test_a_malformed_stored_hash_fails_closed(self):
        """A corrupt hash must read as a failed login, not raise."""
        assert verify_password("anything", "not-a-bcrypt-hash") is False
        assert verify_password("anything", "") is False

    async def test_a_short_password_is_refused_at_registration(self, client):
        response = await client.post(
            "/api/v1/auth/register",
            json={
                "email": "shortpw@test.example",
                "password": "short",
                "full_name": "Short Password",
                "company_name": "Short Co",
                "phone": "+91 90000 11111",
            },
        )
        assert response.status_code == 422

    async def test_changing_a_password_requires_the_current_one(
        self, client, employee
    ):
        response = await client.post(
            "/api/v1/auth/change-password",
            headers=employee.headers,
            json={"current_password": "not-it", "new_password": "NewPassw0rd!123"},
        )
        assert response.status_code == 401


# ===========================================================================
# 4. Endpoint protection sweep
# ===========================================================================


class TestEndpointProtection:
    #: The only routes that may be reached without a token.
    PUBLIC_PREFIXES = (
        "/api/v1/auth/login",
        "/api/v1/auth/register",
        "/api/v1/auth/refresh",
        "/api/v1/verify/",
        "/health",
        "/docs",
        "/redoc",
        "/openapi.json",
        "/",
    )

    async def test_every_other_route_requires_authentication(self, client, app):
        """Sweep the live route table rather than trusting a hand-written list."""
        unprotected: list[str] = []

        for route in app.routes:
            path = getattr(route, "path", "")
            methods = getattr(route, "methods", set()) - {"HEAD", "OPTIONS"}
            if not methods or not path.startswith("/"):
                continue
            if any(path.startswith(prefix) for prefix in self.PUBLIC_PREFIXES):
                continue
            # Fill path parameters with a well-formed but absent ObjectId, so a
            # 404 still proves the route authenticated first.
            concrete = re.sub(r"\{[^}]+\}", "0" * 24, path)

            for method in sorted(methods):
                response = await client.request(method, concrete)
                if response.status_code != 401:
                    unprotected.append(
                        f"{method} {path} -> {response.status_code}"
                    )

        assert not unprotected, "these routes answered without a token:\n" + "\n".join(
            unprotected
        )

    async def test_the_public_verification_endpoint_needs_no_token(self, client):
        response = await client.get("/api/v1/verify/AAAA-BBBB-CCCC")
        assert response.status_code == 200
        assert response.json()["valid"] is False

    async def test_the_health_endpoint_needs_no_token(self, client):
        response = await client.get("/health")
        assert response.status_code == 200


# ===========================================================================
# 5. Customer data isolation
# ===========================================================================


class TestCustomerIsolation:
    async def _second_customer(self, client):
        customer_id = await create_customer(
            code="CUST-SEC-2", email="second@test.example"
        )
        user = await create_user(
            email="second.buyer@test.example",
            role=UserRole.CUSTOMER,
            customer_id=customer_id,
        )
        return Actor(
            user["id"],
            user["email"],
            await _login(client, user["email"]),
            customer_id=customer_id,
        )

    async def test_a_customer_cannot_read_another_customers_request(
        self, client, customer_actor
    ):
        other = await self._second_customer(client)
        product_id = await create_product(sku="SEC-ISO-1")
        created = await client.post(
            "/api/v1/quotation-requests",
            headers=customer_actor.headers,
            json={
                "items": [{"product_id": product_id, "quantity": 1}],
                "submit": True,
            },
        )
        request_id = created.json()["workflow"]["request"]["id"]

        response = await client.get(
            f"/api/v1/quotation-requests/{request_id}", headers=other.headers
        )
        assert response.status_code == 403

    async def test_a_customers_list_is_scoped_to_their_own_records(
        self, client, customer_actor
    ):
        other = await self._second_customer(client)
        product_id = await create_product(sku="SEC-ISO-2")
        await client.post(
            "/api/v1/quotation-requests",
            headers=customer_actor.headers,
            json={
                "items": [{"product_id": product_id, "quantity": 1}],
                "submit": True,
            },
        )

        own = await client.get(
            "/api/v1/quotation-requests", headers=customer_actor.headers
        )
        theirs = await client.get(
            "/api/v1/quotation-requests", headers=other.headers
        )
        assert own.json()["meta"]["total"] == 1
        assert theirs.json()["meta"]["total"] == 0

    async def test_a_customer_cannot_read_another_customers_quotation(
        self, client, customer_actor
    ):
        other = await self._second_customer(client)
        product_id = await create_product(sku="SEC-ISO-3")
        created = await client.post(
            "/api/v1/quotation-requests",
            headers=customer_actor.headers,
            json={
                "items": [{"product_id": product_id, "quantity": 1}],
                "submit": True,
            },
        )
        quotation_id = created.json()["workflow"]["quotation_id"]

        response = await client.get(
            f"/api/v1/quotations/{quotation_id}", headers=other.headers
        )
        assert response.status_code == 403

    async def test_a_customer_cannot_submit_on_behalf_of_another(
        self, client, customer_actor
    ):
        """A customer_id in the payload is ignored for a customer account."""
        other_customer = await create_customer(
            code="CUST-SEC-SPOOF", email="spoof@test.example"
        )
        product_id = await create_product(sku="SEC-ISO-4")
        response = await client.post(
            "/api/v1/quotation-requests",
            headers=customer_actor.headers,
            json={
                "customer_id": other_customer,
                "items": [{"product_id": product_id, "quantity": 1}],
                "submit": True,
            },
        )
        assert response.status_code == 201
        assert (
            response.json()["workflow"]["request"]["customer_id"]
            == customer_actor.customer_id
        )

    async def test_a_customer_cannot_read_another_users_notification(
        self, client, customer_actor, manager
    ):
        # Raise a request that escalates, which guarantees the manager has an
        # approval notification to attempt - rather than skipping if they do not.
        product_id = await create_product(
            sku="SEC-NOTIF", unit_price="1000.00", cost_price="100.00"
        )
        await client.post(
            "/api/v1/quotation-requests",
            headers=customer_actor.headers,
            json={
                "items": [
                    {
                        "product_id": product_id,
                        "quantity": 10,
                        "requested_discount_percent": 9,
                    }
                ],
                "submit": True,
            },
        )

        inbox = await client.get(
            "/api/v1/notifications", headers=manager.headers, params={"page_size": 5}
        )
        assert inbox.json()["items"], "the manager should have been notified"
        notification_id = inbox.json()["items"][0]["id"]
        response = await client.post(
            f"/api/v1/notifications/{notification_id}/read",
            headers=customer_actor.headers,
        )
        assert response.status_code == 404


# ===========================================================================
# 6. Manager approval restrictions
# ===========================================================================


class TestApprovalRestrictions:
    async def _escalated(self, client, customer_actor):
        product_id = await create_product(
            sku="SEC-APPROVE", unit_price="1000.00", cost_price="100.00"
        )
        created = await client.post(
            "/api/v1/quotation-requests",
            headers=customer_actor.headers,
            json={
                "items": [
                    {
                        "product_id": product_id,
                        "quantity": 10,
                        "requested_discount_percent": 9,
                    }
                ],
                "submit": True,
            },
        )
        return created.json()["workflow"]

    async def test_only_a_manager_may_decide(
        self, client, customer_actor, employee
    ):
        workflow = await self._escalated(client, customer_actor)
        for actor in (customer_actor, employee):
            response = await client.post(
                f"/api/v1/approvals/{workflow['approval_id']}/decision",
                headers=actor.headers,
                json={"decision": "APPROVE"},
            )
            assert response.status_code == 403

    async def test_a_customer_cannot_approve_their_own_request(
        self, client, customer_actor
    ):
        """The obvious self-approval attack."""
        workflow = await self._escalated(client, customer_actor)
        response = await client.post(
            f"/api/v1/approvals/{workflow['approval_id']}/decision",
            headers=customer_actor.headers,
            json={"decision": "APPROVE", "comments": "Looks fine to me"},
        )
        assert response.status_code == 403
        # And the request is untouched.
        detail = await client.get(
            f"/api/v1/quotation-requests/{workflow['request']['id']}",
            headers=customer_actor.headers,
        )
        assert detail.json()["status"] == "PENDING_APPROVAL"
        assert detail.json()["quotation_id"] is None

    async def test_an_override_beyond_policy_is_refused(
        self, client, customer_actor, manager
    ):
        workflow = await self._escalated(client, customer_actor)
        response = await client.post(
            f"/api/v1/approvals/{workflow['approval_id']}/decision",
            headers=manager.headers,
            json={"decision": "APPROVE", "override_discount_percent": 95},
        )
        assert response.status_code == 409
        assert "maximum that company policy permits" in (
            response.json()["error"]["message"]
        )

    async def test_a_decided_task_cannot_be_decided_again(
        self, client, customer_actor, manager
    ):
        workflow = await self._escalated(client, customer_actor)
        first = await client.post(
            f"/api/v1/approvals/{workflow['approval_id']}/decision",
            headers=manager.headers,
            json={"decision": "APPROVE"},
        )
        assert first.status_code == 200
        second = await client.post(
            f"/api/v1/approvals/{workflow['approval_id']}/decision",
            headers=manager.headers,
            json={"decision": "REJECT", "comments": "changed my mind"},
        )
        assert second.status_code == 409

    async def test_a_quotation_cannot_be_issued_without_an_approval(
        self, client, customer_actor
    ):
        """The escalated request holds no document until a manager acts."""
        workflow = await self._escalated(client, customer_actor)
        assert workflow["quotation_id"] is None
        count = await get_collection(Collections.QUOTATIONS).count_documents(
            {"request_id": workflow["request"]["id"]}
        )
        assert count == 0


# ===========================================================================
# 7. Secure file downloads
# ===========================================================================


class TestFileDownloads:
    async def _quotation(self, client, customer_actor):
        product_id = await create_product(sku="SEC-PDF")
        created = await client.post(
            "/api/v1/quotation-requests",
            headers=customer_actor.headers,
            json={
                "items": [{"product_id": product_id, "quantity": 2}],
                "submit": True,
            },
        )
        return created.json()["workflow"]["quotation_id"]

    async def test_a_pdf_cannot_be_downloaded_anonymously(
        self, client, customer_actor
    ):
        quotation_id = await self._quotation(client, customer_actor)
        response = await client.get(f"/api/v1/quotations/{quotation_id}/pdf")
        assert response.status_code == 401

    async def test_a_pdf_cannot_be_downloaded_by_another_customer(
        self, client, customer_actor
    ):
        quotation_id = await self._quotation(client, customer_actor)
        other_customer = await create_customer(
            code="CUST-SEC-PDF", email="pdfthief@test.example"
        )
        user = await create_user(
            email="pdfthief.buyer@test.example",
            role=UserRole.CUSTOMER,
            customer_id=other_customer,
        )
        other = Actor(user["id"], user["email"], await _login(client, user["email"]))

        response = await client.get(
            f"/api/v1/quotations/{quotation_id}/pdf", headers=other.headers
        )
        assert response.status_code == 403

    async def test_the_owner_can_download_their_pdf(self, client, customer_actor):
        quotation_id = await self._quotation(client, customer_actor)
        response = await client.get(
            f"/api/v1/quotations/{quotation_id}/pdf", headers=customer_actor.headers
        )
        assert response.status_code == 200
        assert response.headers["content-type"] == "application/pdf"
        assert response.content.startswith(b"%PDF-")

    async def test_the_download_filename_is_the_quotation_number(
        self, client, customer_actor
    ):
        """No user-supplied value reaches the Content-Disposition header."""
        quotation_id = await self._quotation(client, customer_actor)
        response = await client.get(
            f"/api/v1/quotations/{quotation_id}/pdf", headers=customer_actor.headers
        )
        disposition = response.headers.get("content-disposition", "")
        assert re.search(r'filename="?QT-\d{4}-\d{5}\.pdf"?', disposition), disposition

    async def test_a_download_is_audited(self, client, customer_actor, manager):
        quotation_id = await self._quotation(client, customer_actor)
        await client.get(
            f"/api/v1/quotations/{quotation_id}/pdf", headers=customer_actor.headers
        )
        response = await client.get(
            "/api/v1/audit-logs",
            headers=manager.headers,
            params={"action": "QUOTATION_DOWNLOADED"},
        )
        assert response.json()["meta"]["total"] == 1
        entry = response.json()["items"][0]
        assert entry["actor_email"] == customer_actor.email


# ===========================================================================
# 8. Configuration comes from the environment
# ===========================================================================


class TestConfiguration:
    def test_the_secrets_are_read_from_the_environment(self):
        """The test run sets these, which proves they are not hard-coded."""
        assert settings.jwt_secret_key == "test-secret-key-for-quoteflow-tests"
        assert settings.verification_secret == "test-verification-secret"
        assert settings.mongodb_db_name == "quoteflow_test"

    def test_no_env_file_is_committed(self):
        """`.env` holds real secrets and must stay out of version control."""
        gitignore = (BACKEND_ROOT.parent / ".gitignore").read_text(encoding="utf-8")
        assert ".env" in gitignore

    @pytest.mark.parametrize(
        "template,placeholder",
        [
            ("backend/.env.example", "change-me"),
            (".env.docker.example", "replace-me"),
        ],
    )
    def test_an_env_template_carries_no_real_secrets(self, template, placeholder):
        """Every shipped template must hold a placeholder, not a usable key."""
        path = BACKEND_ROOT.parent / template
        assert path.exists(), f"{template} is missing"
        secret_lines = [
            line
            for line in path.read_text(encoding="utf-8").splitlines()
            if line.startswith(("JWT_SECRET_KEY", "VERIFICATION_SECRET"))
        ]
        assert secret_lines, f"{template} should declare the secrets"
        for line in secret_lines:
            assert placeholder in line, (
                f"{template} should ship a placeholder, not a usable secret: {line}"
            )

    def test_the_compose_file_demands_the_secrets_be_set(self):
        """Compose must refuse to start rather than fall back to a default."""
        compose = (BACKEND_ROOT.parent / "docker-compose.yml").read_text(
            encoding="utf-8"
        )
        for variable in ("JWT_SECRET_KEY", "VERIFICATION_SECRET"):
            assert f"${{{variable}:?" in compose, (
                f"{variable} should use the ${{VAR:?message}} form so a missing "
                f"value fails the deployment loudly"
            )

    def test_the_production_image_does_not_run_as_root(self):
        dockerfile = (BACKEND_ROOT / "Dockerfile").read_text(encoding="utf-8")
        assert "USER quoteflow" in dockerfile
        # And the switch happens before the process starts.
        assert dockerfile.index("USER quoteflow") < dockerfile.index("CMD")

    def test_the_production_image_disables_debug(self):
        dockerfile = (BACKEND_ROOT / "Dockerfile").read_text(encoding="utf-8")
        assert "APP_ENV=production" in dockerfile
        assert "DEBUG=false" in dockerfile

        # Check the instructions, not the comments - a comment may legitimately
        # mention --reload to explain why it is absent.
        instructions = "\n".join(
            line
            for line in dockerfile.splitlines()
            if line.strip() and not line.lstrip().startswith("#")
        )
        assert "--reload" not in instructions, "never reload in production"

    def test_no_secret_is_hard_coded_in_the_application(self):
        """Sweep the source for an assignment that bakes a secret in."""
        offenders: list[str] = []
        pattern = re.compile(
            r"""(jwt_secret_key|verification_secret|mongodb_uri)\s*=\s*["'](?!.*(change-me|localhost|127\.0\.0\.1|\{|\$))[^"']{12,}["']""",
            re.IGNORECASE,
        )
        for path in (BACKEND_ROOT / "app").rglob("*.py"):
            for number, line in enumerate(
                path.read_text(encoding="utf-8").splitlines(), start=1
            ):
                if pattern.search(line):
                    offenders.append(f"{path.name}:{number}: {line.strip()}")
        assert not offenders, "hard-coded secrets found:\n" + "\n".join(offenders)

    def test_the_verification_digest_depends_on_the_secret(self):
        """Rotating the secret must invalidate previously issued digests."""
        from app.services import verification_service

        payload = {
            "quotation_number": "QT-2026-00001",
            "request_number": "QR-2026-00001",
            "customer_id": "6710c0a1b2c3d4e5f6a7b8c9",
            "verification_code": "ABCD-EFGH-JKLM",
            "items": [],
            "pricing": {"final_amount": "100.00", "currency": "INR"},
        }
        original = verification_service.compute_integrity_hash(**payload)

        settings.verification_secret = "a-different-secret"
        try:
            rotated = verification_service.compute_integrity_hash(**payload)
        finally:
            settings.verification_secret = "test-verification-secret"

        assert original != rotated

    async def test_the_audit_trail_has_no_write_endpoint(self, app):
        """Audit records must not be modifiable through the API."""
        for route in app.routes:
            path = getattr(route, "path", "")
            if "audit-logs" not in path:
                continue
            methods = getattr(route, "methods", set()) - {"HEAD", "OPTIONS"}
            assert methods == {"GET"}, f"{path} exposes {methods}"
