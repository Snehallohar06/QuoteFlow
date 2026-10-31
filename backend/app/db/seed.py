"""Seed data: a working demo dataset.

Run with ``python -m app.db.seed`` (add ``--reset`` to wipe first). The data is
chosen so each branch of the workflow can be demonstrated immediately:

* ``ACME-GOLD`` has a GOLD tier bonus and a credit limit that a large order
  will breach.
* ``PRX-5500`` is deliberately low on stock, to show the shortfall path.
* ``WRN-0100`` has a tight cost price, so a deep discount hits the cost floor.
"""

from __future__ import annotations

import argparse
import asyncio
import logging

from app.core.security import hash_password
from app.db.indexes import ensure_indexes
from app.db.mongo import (
    Collections,
    close_mongo_connection,
    connect_to_mongo,
    get_collection,
    get_database,
)
from app.models.common import utc_now
from app.models.customer import Address, Customer
from app.models.enums import CustomerStatus, CustomerTier, ProductStatus, UserRole
from app.models.product import Product
from app.models.user import User
from app.services import settings_service
from app.utils.money import encode_decimals

logging.basicConfig(level=logging.INFO, format="%(levelname)-8s %(message)s")
logger = logging.getLogger("seed")

DEMO_PASSWORD = "QuoteFlow@2026"

PRODUCTS: list[dict] = [
    # --- Pumps -------------------------------------------------------------
    {
        "sku": "PMP-1200",
        "name": "Centrifugal Pump 1200 LPM",
        "description": "Cast-iron centrifugal pump, 1200 litres per minute, 7.5 kW.",
        "category": "Pumps",
        "unit_price": "48500.00",
        "cost_price": "36000.00",
        "stock_quantity": 64,
        "reserved_quantity": 6,
        "reorder_level": 15,
        "lead_time_days": 10,
    },
    {
        "sku": "PMP-0600",
        "name": "Centrifugal Pump 600 LPM",
        "description": "Compact centrifugal pump, 600 litres per minute, 3 kW.",
        "category": "Pumps",
        "unit_price": "27900.00",
        "cost_price": "20500.00",
        "stock_quantity": 120,
        "reserved_quantity": 10,
        "reorder_level": 25,
        "lead_time_days": 7,
    },
    {
        "sku": "PMP-SUB-30",
        "name": "Submersible Pump 3 HP",
        "description": "Stainless submersible borewell pump, 3 HP, single phase.",
        "category": "Pumps",
        "unit_price": "19750.00",
        "cost_price": "14800.00",
        "stock_quantity": 85,
        "reserved_quantity": 0,
        "reorder_level": 20,
        "lead_time_days": 5,
    },
    # --- Valves ------------------------------------------------------------
    {
        "sku": "VLV-GTE-80",
        "name": "Gate Valve 80 mm",
        "description": "Flanged cast-iron gate valve, PN16, 80 mm bore.",
        "category": "Valves",
        "unit_price": "4250.00",
        "cost_price": "2900.00",
        "stock_quantity": 480,
        "reserved_quantity": 40,
        "reorder_level": 100,
        "lead_time_days": 4,
    },
    {
        "sku": "VLV-BFL-150",
        "name": "Butterfly Valve 150 mm",
        "description": "Wafer-type butterfly valve with EPDM seat, 150 mm.",
        "category": "Valves",
        "unit_price": "7850.00",
        "cost_price": "5400.00",
        "stock_quantity": 260,
        "reserved_quantity": 20,
        "reorder_level": 60,
        "lead_time_days": 6,
    },
    {
        "sku": "VLV-NRV-50",
        "name": "Non-Return Valve 50 mm",
        "description": "Swing-type non-return valve, bronze trim, 50 mm.",
        "category": "Valves",
        "unit_price": "2180.00",
        "cost_price": "1450.00",
        "stock_quantity": 640,
        "reserved_quantity": 0,
        "reorder_level": 150,
        "lead_time_days": 3,
    },
    # --- Motors & drives ---------------------------------------------------
    {
        "sku": "MTR-IE3-75",
        "name": "IE3 Induction Motor 7.5 kW",
        "description": "Three-phase IE3 premium-efficiency motor, 7.5 kW, B3 mount.",
        "category": "Motors & Drives",
        "unit_price": "38400.00",
        "cost_price": "29500.00",
        "stock_quantity": 72,
        "reserved_quantity": 4,
        "reorder_level": 18,
        "lead_time_days": 12,
    },
    {
        "sku": "VFD-0110",
        "name": "Variable Frequency Drive 11 kW",
        "description": "Sensorless vector VFD, 11 kW, IP20, built-in EMC filter.",
        "category": "Motors & Drives",
        "unit_price": "52600.00",
        "cost_price": "41000.00",
        "stock_quantity": 40,
        "reserved_quantity": 2,
        "reorder_level": 10,
        "lead_time_days": 14,
    },
    # --- Pipes & fittings --------------------------------------------------
    {
        "sku": "PIP-GI-100",
        "name": "GI Pipe 100 mm (6 m length)",
        "description": "Galvanised iron pipe, medium class, 100 mm nominal bore.",
        "category": "Pipes & Fittings",
        "unit": "length",
        "unit_price": "5620.00",
        "cost_price": "4300.00",
        "stock_quantity": 920,
        "reserved_quantity": 120,
        "reorder_level": 200,
        "lead_time_days": 5,
    },
    {
        "sku": "PIP-ELB-100",
        "name": "GI Elbow 100 mm",
        "description": "Threaded galvanised iron elbow, 90 degrees, 100 mm.",
        "category": "Pipes & Fittings",
        "unit_price": "685.00",
        "cost_price": "430.00",
        "stock_quantity": 1500,
        "reserved_quantity": 0,
        "reorder_level": 300,
        "lead_time_days": 2,
    },
    {
        "sku": "PIP-FLG-150",
        "name": "Slip-On Flange 150 mm",
        "description": "Carbon steel slip-on flange, ASA 150, 150 mm.",
        "category": "Pipes & Fittings",
        "unit_price": "1340.00",
        "cost_price": "890.00",
        "stock_quantity": 880,
        "reserved_quantity": 60,
        "reorder_level": 200,
        "lead_time_days": 3,
    },
    # --- Instrumentation ---------------------------------------------------
    {
        "sku": "PRX-5500",
        "name": "Pressure Transmitter 0-16 bar",
        "description": "4-20 mA pressure transmitter, 0-16 bar, IP67.",
        "category": "Instrumentation",
        "unit_price": "14900.00",
        "cost_price": "11200.00",
        # Deliberately short: demonstrates the stock shortfall exception.
        "stock_quantity": 9,
        "reserved_quantity": 3,
        "reorder_level": 12,
        "lead_time_days": 21,
    },
    {
        "sku": "FLW-ELC-80",
        "name": "Electromagnetic Flow Meter 80 mm",
        "description": "Battery-powered electromagnetic flow meter, 80 mm, IP68.",
        "category": "Instrumentation",
        "unit_price": "86500.00",
        "cost_price": "68000.00",
        "stock_quantity": 24,
        "reserved_quantity": 0,
        "reorder_level": 6,
        "lead_time_days": 18,
        # Tighter than the policy ceiling: shows a per-product discount cap.
        "max_discount_percent": "6",
    },
    {
        "sku": "GAU-DIA-100",
        "name": "Diaphragm Pressure Gauge 100 mm",
        "description": "Glycerine-filled diaphragm gauge, 100 mm dial, 0-10 bar.",
        "category": "Instrumentation",
        "unit_price": "3450.00",
        "cost_price": "2300.00",
        "stock_quantity": 340,
        "reserved_quantity": 0,
        "reorder_level": 80,
        "lead_time_days": 4,
    },
    # --- Consumables -------------------------------------------------------
    {
        "sku": "WRN-0100",
        "name": "Mechanical Seal Kit (Standard)",
        "description": "Replacement mechanical seal kit for 1200 LPM pump series.",
        "category": "Consumables",
        "unit_price": "2400.00",
        # Thin margin: a discount beyond ~12% breaches the cost floor.
        "cost_price": "2100.00",
        "stock_quantity": 760,
        "reserved_quantity": 0,
        "reorder_level": 150,
        "lead_time_days": 3,
    },
    {
        "sku": "GSK-CAF-150",
        "name": "CAF Gasket 150 mm",
        "description": "Compressed asbestos-free gasket, 3 mm, 150 mm.",
        "category": "Consumables",
        "unit_price": "320.00",
        "cost_price": "180.00",
        "stock_quantity": 2400,
        "reserved_quantity": 0,
        "reorder_level": 500,
        "lead_time_days": 2,
    },
    {
        "sku": "LUB-SYN-20",
        "name": "Synthetic Gear Oil 20 L",
        "description": "ISO VG 220 synthetic industrial gear oil, 20 litre pail.",
        "category": "Consumables",
        "unit": "pail",
        "unit_price": "8600.00",
        "cost_price": "6900.00",
        "stock_quantity": 180,
        "reserved_quantity": 0,
        "reorder_level": 40,
        "lead_time_days": 5,
    },
    {
        "sku": "FIL-CRT-10",
        "name": "Filter Cartridge 10 inch",
        "description": "Polypropylene wound filter cartridge, 10 inch, 5 micron.",
        "category": "Consumables",
        "unit_price": "285.00",
        "cost_price": "160.00",
        "stock_quantity": 3200,
        "reserved_quantity": 0,
        "reorder_level": 600,
        "lead_time_days": 2,
    },
    # --- Discontinued, to exercise the validation path ---------------------
    {
        "sku": "PMP-LEG-900",
        "name": "Legacy Pump 900 LPM (discontinued)",
        "description": "Superseded by PMP-1200. Retained for historical quotations.",
        "category": "Pumps",
        "unit_price": "41200.00",
        "cost_price": "33000.00",
        "stock_quantity": 0,
        "reserved_quantity": 0,
        "status": ProductStatus.DISCONTINUED.value,
        "lead_time_days": 0,
    },
]

CUSTOMERS: list[dict] = [
    {
        "code": "CUST-0001",
        "company_name": "Acme Process Engineering",
        "contact_name": "Rohit Desai",
        "email": "rohit.desai@acme-process.example",
        "phone": "+91 98200 11223",
        "tier": CustomerTier.GOLD.value,
        "credit_limit": "1200000.00",
        "tax_id": "27AAACA1234B1ZX",
        "billing_address": {
            "line1": "Unit 7, Bhosari Industrial Estate",
            "city": "Pune",
            "state": "Maharashtra",
            "postal_code": "411026",
            "country": "India",
        },
        "notes": "Long-standing account. Gold tier discount bonus applies.",
    },
    {
        "code": "CUST-0002",
        "company_name": "Deccan Water Infrastructure",
        "contact_name": "Priya Nair",
        "email": "priya.nair@deccan-water.example",
        "phone": "+91 99400 55667",
        "tier": CustomerTier.PLATINUM.value,
        "credit_limit": "4500000.00",
        "tax_id": "29AAFCD5678C1ZP",
        "billing_address": {
            "line1": "Plot 22, Peenya Industrial Area",
            "city": "Bengaluru",
            "state": "Karnataka",
            "postal_code": "560058",
            "country": "India",
        },
        "notes": "Framework agreement. Large tenders, usually above threshold.",
    },
    {
        "code": "CUST-0003",
        "company_name": "Sunrise Fabrication Works",
        "contact_name": "Imran Shaikh",
        "email": "imran@sunrise-fab.example",
        "phone": "+91 97300 44556",
        "tier": CustomerTier.STANDARD.value,
        # Low limit on purpose: a mid-sized order breaches it.
        "credit_limit": "150000.00",
        "billing_address": {
            "line1": "Shed 4, GIDC Phase II",
            "city": "Vadodara",
            "state": "Gujarat",
            "postal_code": "390010",
            "country": "India",
        },
    },
    {
        "code": "CUST-0004",
        "company_name": "Konkan Marine Services",
        "contact_name": "Anita Rane",
        "email": "anita.rane@konkan-marine.example",
        "phone": "+91 96100 77889",
        "tier": CustomerTier.SILVER.value,
        "credit_limit": "600000.00",
        "billing_address": {
            "line1": "Dockyard Road, Mazgaon",
            "city": "Mumbai",
            "state": "Maharashtra",
            "postal_code": "400010",
            "country": "India",
        },
    },
    {
        "code": "CUST-0005",
        "company_name": "Halted Industries",
        "contact_name": "Suresh Menon",
        "email": "suresh@halted-industries.example",
        "phone": "+91 95000 33221",
        "tier": CustomerTier.STANDARD.value,
        "status": CustomerStatus.ON_HOLD.value,
        "credit_limit": "0.00",
        "notes": "On hold pending payment of overdue invoices.",
    },
]

STAFF: list[dict] = [
    {
        "email": "manager@quoteflow.example",
        "full_name": "Meera Iyer",
        "role": UserRole.SALES_MANAGER.value,
        "phone": "+91 20 4000 1201",
    },
    {
        "email": "sales1@quoteflow.example",
        "full_name": "Arjun Kulkarni",
        "role": UserRole.SALES_EMPLOYEE.value,
        "phone": "+91 20 4000 1202",
    },
    {
        "email": "sales2@quoteflow.example",
        "full_name": "Fatima Qureshi",
        "role": UserRole.SALES_EMPLOYEE.value,
        "phone": "+91 20 4000 1203",
    },
]

#: Customer logins, matched to the customer records above by email.
CUSTOMER_LOGINS: list[tuple[str, str, str]] = [
    ("rohit.desai@acme-process.example", "Rohit Desai", "CUST-0001"),
    ("priya.nair@deccan-water.example", "Priya Nair", "CUST-0002"),
    ("imran@sunrise-fab.example", "Imran Shaikh", "CUST-0003"),
    ("anita.rane@konkan-marine.example", "Anita Rane", "CUST-0004"),
]


async def _reset() -> None:
    database = get_database()
    for name in Collections.all():
        await database[name].delete_many({})
    logger.info("Cleared %d collections", len(Collections.all()))


async def _seed_products() -> int:
    collection = get_collection(Collections.PRODUCTS)
    inserted = 0
    for entry in PRODUCTS:
        if await collection.find_one({"sku": entry["sku"]}, {"_id": 1}):
            continue
        product = Product.model_validate(entry)
        await collection.insert_one(
            encode_decimals(product.model_dump(exclude={"id"}))
        )
        inserted += 1
    return inserted


async def _seed_customers() -> dict[str, str]:
    collection = get_collection(Collections.CUSTOMERS)
    ids: dict[str, str] = {}
    for entry in CUSTOMERS:
        existing = await collection.find_one({"code": entry["code"]}, {"_id": 1})
        if existing:
            ids[entry["email"]] = str(existing["_id"])
            continue
        payload = dict(entry)
        if isinstance(payload.get("billing_address"), dict):
            payload["billing_address"] = Address.model_validate(
                payload["billing_address"]
            )
        customer = Customer.model_validate(payload)
        result = await collection.insert_one(
            encode_decimals(customer.model_dump(exclude={"id"}))
        )
        ids[entry["email"]] = str(result.inserted_id)
    return ids


async def _seed_users(customer_ids: dict[str, str]) -> int:
    collection = get_collection(Collections.USERS)
    password_hash = hash_password(DEMO_PASSWORD)
    inserted = 0

    for entry in STAFF:
        if await collection.find_one({"email": entry["email"]}, {"_id": 1}):
            continue
        user = User.model_validate({**entry, "password_hash": password_hash})
        await collection.insert_one(user.model_dump(exclude={"id"}))
        inserted += 1

    for email, full_name, code in CUSTOMER_LOGINS:
        if await collection.find_one({"email": email}, {"_id": 1}):
            continue
        customer_id = customer_ids.get(email)
        if customer_id is None:
            logger.warning("No customer record for %s (%s); skipping login", email, code)
            continue
        user = User(
            email=email,
            password_hash=password_hash,
            full_name=full_name,
            role=UserRole.CUSTOMER,
            customer_id=customer_id,
        )
        await collection.insert_one(user.model_dump(exclude={"id"}))
        inserted += 1

    return inserted


async def _seed_counters() -> None:
    """Align the numbering counters with the hand-written customer codes."""
    year = utc_now().year
    await get_collection(Collections.COUNTERS).update_one(
        {"_id": f"CUST-{year}"},
        {"$max": {"value": len(CUSTOMERS)}},
        upsert=True,
    )


async def seed(reset: bool = False) -> dict[str, int]:
    await connect_to_mongo()
    try:
        database = get_database()
        await ensure_indexes(database)

        if reset:
            await _reset()

        settings_document = await settings_service.initialise_settings()
        products = await _seed_products()
        customer_ids = await _seed_customers()
        users = await _seed_users(customer_ids)
        await _seed_counters()

        summary = {
            "products": products,
            "customers": len(customer_ids),
            "users": users,
        }
        logger.info(
            "Seed complete: %d product(s), %d customer(s), %d user(s)",
            products,
            len(customer_ids),
            users,
        )
        tiers = settings_document.discount_policy.tiers
        logger.info(
            "Discount policy: %s",
            ", ".join(
                f"{tier.min_quantity}-{tier.max_quantity or '+'}: "
                f"{tier.max_discount_percent}%"
                for tier in tiers
            ),
        )
        logger.info("Demo password for every seeded account: %s", DEMO_PASSWORD)
        return summary
    finally:
        await close_mongo_connection()


def main() -> None:
    parser = argparse.ArgumentParser(description="Seed the QuoteFlow database.")
    parser.add_argument(
        "--reset",
        action="store_true",
        help="Delete every document in every collection before seeding.",
    )
    args = parser.parse_args()

    if args.reset:
        logger.warning("--reset will delete all existing QuoteFlow data.")
    asyncio.run(seed(reset=args.reset))


if __name__ == "__main__":
    main()
