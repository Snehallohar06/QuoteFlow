"""Quotations: content, PDF rendering, download and public verification."""

import itertools

import pytest
from bson import ObjectId

from app.db.mongo import Collections, get_collection
from app.models.enums import QuotationStatus, UserRole
from app.services import verification_service
from tests.conftest import Actor, _login, create_customer, create_product, create_user

pytestmark = pytest.mark.workflow


_sku_counter = itertools.count(1)


async def issue_quotation(client, actor, *, quantity=4, unit_price="2500.00"):
    # A fresh SKU each call, so a test may issue several quotations.
    product_id = await create_product(
        sku=f"QT-ITEM-{next(_sku_counter)}",
        unit_price=unit_price,
        cost_price="100.00",
        stock_quantity=500,
    )
    response = await client.post(
        "/api/v1/quotation-requests",
        headers=actor.headers,
        json={
            "items": [{"product_id": product_id, "quantity": quantity}],
            "submit": True,
        },
    )
    assert response.status_code == 201, response.text
    workflow = response.json()["workflow"]
    assert workflow["quotation_id"], workflow
    return workflow["quotation_id"]


# ---------------------------------------------------------------------------
# Content
# ---------------------------------------------------------------------------


async def test_the_quotation_snapshots_both_parties(client, customer_actor):
    quotation_id = await issue_quotation(client, customer_actor)
    response = await client.get(
        f"/api/v1/quotations/{quotation_id}", headers=customer_actor.headers
    )
    assert response.status_code == 200
    body = response.json()

    assert body["seller"]["name"] == "Northwind Industrial Supplies"
    assert body["seller"]["tax_id"]
    assert body["buyer"]["name"] == "Test Industries"
    assert body["buyer"]["code"] == "CUST-TEST-1"
    assert body["buyer"]["address_lines"]
    assert body["terms"]
    assert body["status"] == QuotationStatus.ISSUED.value
    assert body["quotation_number"].startswith("QT-")


async def test_the_snapshot_is_frozen_against_later_customer_edits(
    client, customer_actor, employee
):
    """A reissued PDF must reproduce the original, not today's data."""
    quotation_id = await issue_quotation(client, customer_actor)

    await client.patch(
        f"/api/v1/customers/{customer_actor.customer_id}",
        headers=employee.headers,
        json={"company_name": "Renamed Industries"},
    )

    response = await client.get(
        f"/api/v1/quotations/{quotation_id}", headers=customer_actor.headers
    )
    assert response.json()["buyer"]["name"] == "Test Industries"


async def test_validity_window_is_set_from_policy(client, customer_actor):
    quotation_id = await issue_quotation(client, customer_actor)
    response = await client.get(
        f"/api/v1/quotations/{quotation_id}", headers=customer_actor.headers
    )
    body = response.json()
    assert body["valid_until"] > body["issued_at"]


async def test_quotation_numbers_are_sequential_and_unique(client, customer_actor):
    first = await issue_quotation(client, customer_actor)
    second = await issue_quotation(client, customer_actor)

    numbers = []
    for quotation_id in (first, second):
        response = await client.get(
            f"/api/v1/quotations/{quotation_id}", headers=customer_actor.headers
        )
        numbers.append(response.json()["quotation_number"])

    assert numbers[0] != numbers[1]
    assert sorted(numbers) == numbers


# ---------------------------------------------------------------------------
# PDF
# ---------------------------------------------------------------------------


async def test_the_pdf_downloads_and_is_a_real_pdf(client, customer_actor):
    quotation_id = await issue_quotation(client, customer_actor)

    response = await client.get(
        f"/api/v1/quotations/{quotation_id}/pdf", headers=customer_actor.headers
    )
    assert response.status_code == 200
    assert response.headers["content-type"] == "application/pdf"
    assert response.content.startswith(b"%PDF-")
    assert len(response.content) > 1500


async def test_downloads_are_counted(client, customer_actor):
    quotation_id = await issue_quotation(client, customer_actor)

    for _ in range(3):
        await client.get(
            f"/api/v1/quotations/{quotation_id}/pdf", headers=customer_actor.headers
        )

    response = await client.get(
        f"/api/v1/quotations/{quotation_id}", headers=customer_actor.headers
    )
    assert response.json()["download_count"] == 3


async def test_a_multi_line_quotation_renders(client, customer_actor):
    """Several lines with mixed discounts and tax rates must not break layout."""
    ids = [
        await create_product(
            sku=f"MULTI-{index}",
            name=f"Multi Line Product {index} With A Deliberately Long Name",
            unit_price=f"{1000 + index * 137}.50",
            cost_price="100.00",
            tax_rate="5" if index % 2 else None,
            stock_quantity=1000,
        )
        for index in range(6)
    ]
    response = await client.post(
        "/api/v1/quotation-requests",
        headers=customer_actor.headers,
        json={
            "items": [
                {
                    "product_id": product_id,
                    "quantity": 6 + index,
                    "requested_discount_percent": 2,
                }
                for index, product_id in enumerate(ids)
            ],
            "submit": True,
        },
    )
    quotation_id = response.json()["workflow"]["quotation_id"]

    pdf = await client.get(
        f"/api/v1/quotations/{quotation_id}/pdf", headers=customer_actor.headers
    )
    assert pdf.status_code == 200
    assert pdf.content.startswith(b"%PDF-")


# ---------------------------------------------------------------------------
# Access control
# ---------------------------------------------------------------------------


async def test_a_customer_cannot_read_another_customers_quotation(
    client, customer_actor
):
    quotation_id = await issue_quotation(client, customer_actor)

    other_customer = await create_customer(
        code="CUST-NOSY", email="nosy@test.example"
    )
    other_user = await create_user(
        email="nosy.buyer@test.example",
        role=UserRole.CUSTOMER,
        customer_id=other_customer,
    )
    other = Actor(
        other_user["id"], other_user["email"], await _login(client, other_user["email"])
    )

    detail = await client.get(
        f"/api/v1/quotations/{quotation_id}", headers=other.headers
    )
    assert detail.status_code == 403

    pdf = await client.get(
        f"/api/v1/quotations/{quotation_id}/pdf", headers=other.headers
    )
    assert pdf.status_code == 403

    listed = await client.get("/api/v1/quotations", headers=other.headers)
    assert listed.json()["meta"]["total"] == 0


async def test_staff_can_read_any_quotation(client, customer_actor, employee):
    quotation_id = await issue_quotation(client, customer_actor)
    response = await client.get(
        f"/api/v1/quotations/{quotation_id}", headers=employee.headers
    )
    assert response.status_code == 200


async def test_only_a_manager_can_change_a_quotation_status(
    client, customer_actor, employee, manager
):
    quotation_id = await issue_quotation(client, customer_actor)

    denied = await client.post(
        f"/api/v1/quotations/{quotation_id}/status",
        headers=employee.headers,
        params={"new_status": QuotationStatus.ACCEPTED.value},
    )
    assert denied.status_code == 403

    allowed = await client.post(
        f"/api/v1/quotations/{quotation_id}/status",
        headers=manager.headers,
        params={"new_status": QuotationStatus.ACCEPTED.value},
    )
    assert allowed.status_code == 200
    assert allowed.json()["status"] == QuotationStatus.ACCEPTED.value


# ---------------------------------------------------------------------------
# Verification
# ---------------------------------------------------------------------------


async def test_verification_needs_no_authentication(client, customer_actor):
    quotation_id = await issue_quotation(client, customer_actor)
    stored = await get_collection(Collections.QUOTATIONS).find_one(
        {"_id": ObjectId(quotation_id)}
    )
    code = stored["verification_code"]

    # No Authorization header at all.
    response = await client.get(f"/api/v1/verify/{code}")
    assert response.status_code == 200
    body = response.json()
    assert body["valid"] is True
    assert body["reason"] is None
    assert body["quotation_number"] == stored["quotation_number"]
    assert body["customer_name"] == "Test Industries"
    assert body["final_amount"] == 11800.0  # 4 x 2500 + 18%
    assert body["expired"] is False
    assert body["auto_approved"] is True


async def test_verification_is_case_insensitive(client, customer_actor):
    quotation_id = await issue_quotation(client, customer_actor)
    stored = await get_collection(Collections.QUOTATIONS).find_one(
        {"_id": ObjectId(quotation_id)}
    )
    response = await client.get(f"/api/v1/verify/{stored['verification_code'].lower()}")
    assert response.json()["valid"] is True


async def test_an_unknown_code_reports_not_found_without_leaking(client):
    response = await client.get("/api/v1/verify/AAAA-BBBB-CCCC")
    assert response.status_code == 200
    body = response.json()
    assert body["valid"] is False
    assert "No quotation matches" in body["reason"]
    assert body["quotation_number"] is None
    assert body["final_amount"] is None


async def test_tampering_with_a_stored_amount_invalidates_the_quotation(
    client, customer_actor
):
    """The integrity digest is the point of the exercise: prove it catches edits."""
    quotation_id = await issue_quotation(client, customer_actor)
    collection = get_collection(Collections.QUOTATIONS)
    stored = await collection.find_one({"_id": ObjectId(quotation_id)})
    code = stored["verification_code"]

    assert (await client.get(f"/api/v1/verify/{code}")).json()["valid"] is True

    # Someone edits the total directly in the database.
    from bson import Decimal128

    await collection.update_one(
        {"_id": ObjectId(quotation_id)},
        {"$set": {"pricing.final_amount": Decimal128("1.00")}},
    )

    response = await client.get(f"/api/v1/verify/{code}")
    body = response.json()
    assert body["valid"] is False
    assert "do not match the integrity digest" in body["reason"]


async def test_tampering_with_a_line_amount_is_also_caught(client, customer_actor):
    quotation_id = await issue_quotation(client, customer_actor)
    collection = get_collection(Collections.QUOTATIONS)
    stored = await collection.find_one({"_id": ObjectId(quotation_id)})

    from bson import Decimal128

    await collection.update_one(
        {"_id": ObjectId(quotation_id)},
        {"$set": {"items.0.unit_price": Decimal128("1.00")}},
    )

    response = await client.get(f"/api/v1/verify/{stored['verification_code']}")
    assert response.json()["valid"] is False


async def test_the_hash_is_stable_across_key_ordering():
    """Canonical serialisation, so dict order cannot change the digest."""
    args = {
        "quotation_number": "QT-2026-00001",
        "request_number": "QR-2026-00001",
        "customer_id": "6710c0a1b2c3d4e5f6a7b8c9",
        "verification_code": "ABCD-EFGH-JKLM",
    }
    first = verification_service.compute_integrity_hash(
        **args,
        items=[{"sku": "A", "quantity": 2, "unit_price": "10.00",
                "applied_discount_percent": "5", "line_total": "19.00"}],
        pricing={"subtotal": "20.00", "total_discount": "1.00",
                 "taxable_amount": "19.00", "total_tax": "0.00",
                 "final_amount": "19.00", "currency": "INR"},
    )
    second = verification_service.compute_integrity_hash(
        **args,
        items=[{"line_total": "19.00", "unit_price": "10.00", "quantity": 2,
                "applied_discount_percent": "5", "sku": "A"}],
        pricing={"currency": "INR", "final_amount": "19.00", "total_tax": "0.00",
                 "taxable_amount": "19.00", "total_discount": "1.00",
                 "subtotal": "20.00"},
    )
    assert first == second


async def test_a_different_amount_produces_a_different_hash():
    args = {
        "quotation_number": "QT-2026-00001",
        "request_number": "QR-2026-00001",
        "customer_id": "6710c0a1b2c3d4e5f6a7b8c9",
        "verification_code": "ABCD-EFGH-JKLM",
        "items": [],
    }
    base = verification_service.compute_integrity_hash(
        **args, pricing={"final_amount": "19.00", "currency": "INR"}
    )
    altered = verification_service.compute_integrity_hash(
        **args, pricing={"final_amount": "19.01", "currency": "INR"}
    )
    assert base != altered


async def test_verification_codes_use_an_unambiguous_alphabet():
    for _ in range(50):
        code = verification_service.generate_verification_code()
        assert len(code) == 14
        assert code.count("-") == 2
        # No characters that are easy to misread when typed from paper.
        assert not set("OI01") & set(code)


# ---------------------------------------------------------------------------
# Expiry
# ---------------------------------------------------------------------------


async def test_expired_quotations_are_flagged(client, customer_actor, employee):
    quotation_id = await issue_quotation(client, customer_actor)
    collection = get_collection(Collections.QUOTATIONS)
    stored = await collection.find_one({"_id": ObjectId(quotation_id)})

    from datetime import timedelta

    from app.models.common import utc_now

    await collection.update_one(
        {"_id": ObjectId(quotation_id)},
        {"$set": {"valid_until": utc_now() - timedelta(days=1)}},
    )

    verification = await client.get(f"/api/v1/verify/{stored['verification_code']}")
    body = verification.json()
    # Still authentic, but no longer current.
    assert body["valid"] is True
    assert body["expired"] is True

    swept = await client.post("/api/v1/quotations/expire-due", headers=employee.headers)
    assert swept.json()["expired"] == 1

    after = await client.get(
        f"/api/v1/quotations/{quotation_id}", headers=employee.headers
    )
    assert after.json()["status"] == QuotationStatus.EXPIRED.value
