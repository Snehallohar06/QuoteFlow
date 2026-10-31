"""Generate a realistic spread of demo activity against a running API.

`app.db.seed` creates the master data (products, customers, logins). This script
adds *transactional* activity on top, so the dashboards, analytics charts and
approval queue have something to show:

* auto-approved requests (within policy)
* requests escalated for a discount exception, an order-value breach,
  a credit-limit breach and a stock shortfall
* one approval granted with an override discount, one rejection, one
  modification request
* requests that fail validation (below cost price, discontinued product)

Usage, with the API already running on :8000::

    python scripts/demo_activity.py
    python scripts/demo_activity.py --base-url http://127.0.0.1:8000

Re-running it adds more activity; it never deletes anything. Use
``python -m app.db.seed --reset`` first for a clean slate.
"""

from __future__ import annotations

import argparse
import sys

import httpx

PASSWORD = "QuoteFlow@2026"

MANAGER = "manager@quoteflow.example"
EMPLOYEE = "sales1@quoteflow.example"
GOLD_CUSTOMER = "rohit.desai@acme-process.example"  # GOLD, high credit
PLATINUM_CUSTOMER = "priya.nair@deccan-water.example"  # PLATINUM, very high credit
SMALL_CUSTOMER = "imran@sunrise-fab.example"  # STANDARD, low credit
SILVER_CUSTOMER = "anita.rane@konkan-marine.example"  # SILVER


#: Master-data additions a sales employee has asked a manager to authorise.
#: Left pending, so the manager's queue has something to decide in a demo.
MASTER_DATA_PROPOSALS = [
    (
        "customer - Western Hydraulics",
        "customers",
        {
            "customer": {
                "company_name": "Western Hydraulics Pvt Ltd",
                "contact_name": "Sunil Kulkarni",
                "email": "sunil@western-hydraulics.example",
                "phone": "9822011234",
                "tier": "SILVER",
                "credit_limit": 400000,
                "notes": "Referred by Deccan Water Systems.",
            },
            "reason": "They want to order monthly; opening the account unblocks it.",
        },
    ),
    (
        "product - PMP-1800 booster pump",
        "products",
        {
            "product": {
                "sku": "PMP-1800",
                "name": "Booster Pump 1800 LPM",
                "description": "Higher-capacity sibling of the PMP-1200.",
                "category": "Pumps",
                "unit": "pcs",
                "unit_price": 128000,
                "cost_price": 86000,
                "stock_quantity": 12,
                "reorder_level": 4,
                "lead_time_days": 21,
            },
            "reason": "Three customers have asked for a larger pump this quarter.",
        },
    ),
]


class Api:
    def __init__(self, base_url: str) -> None:
        self.base = base_url.rstrip("/")
        self.api = f"{self.base}/api/v1"
        self.client = httpx.Client(timeout=60)
        self.tokens: dict[str, dict[str, str]] = {}

    def close(self) -> None:
        self.client.close()

    def login(self, email: str) -> dict[str, str]:
        if email not in self.tokens:
            response = self.client.post(
                f"{self.api}/auth/login", json={"email": email, "password": PASSWORD}
            )
            response.raise_for_status()
            token = response.json()["access_token"]
            self.tokens[email] = {"Authorization": f"Bearer {token}"}
        return self.tokens[email]

    def get(self, path: str, email: str, **params):
        response = self.client.get(
            f"{self.api}{path}", headers=self.login(email), params=params or None
        )
        response.raise_for_status()
        return response.json()

    def post(self, path: str, email: str, payload: dict | None = None, **params):
        response = self.client.post(
            f"{self.api}{path}",
            headers=self.login(email),
            json=payload,
            params=params or None,
        )
        return response


def catalogue(api: Api) -> dict[str, dict]:
    """SKU -> product, for the whole active catalogue."""
    page = api.get("/products/catalogue", MANAGER, page_size=100)
    return {item["sku"]: item for item in page["items"]}


def submit(
    api: Api, email: str, lines: list[tuple[str, int, float]], products, note=None
):
    """Submit a request. ``lines`` is a list of (sku, quantity, discount%)."""
    payload = {
        "items": [
            {
                "product_id": products[sku]["id"],
                "quantity": quantity,
                "requested_discount_percent": discount,
            }
            for sku, quantity, discount in lines
        ],
        "submit": True,
    }
    if note:
        payload["customer_notes"] = note

    response = api.post("/quotation-requests", email, payload)
    if response.status_code != 201:
        return {"error": response.json(), "status_code": response.status_code}
    return response.json()["workflow"]


def decide(api: Api, approval_id: str, decision: str, **extra):
    response = api.post(
        f"/approvals/{approval_id}/decision",
        MANAGER,
        {"decision": decision, **extra},
    )
    return response


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", default="http://127.0.0.1:8000")
    args = parser.parse_args()

    api = Api(args.base_url)
    try:
        try:
            health = api.client.get(f"{api.base}/health", timeout=5).json()
        except httpx.HTTPError:
            print(
                f"Could not reach the API at {api.base}. Start it with:\n"
                f"  uvicorn app.main:app --reload --port 8000",
                file=sys.stderr,
            )
            return 1
        if not health.get("database", {}).get("connected"):
            print("The API is up but MongoDB is not reachable.", file=sys.stderr)
            return 1

        products = catalogue(api)
        if "PMP-1200" not in products:
            print(
                "The catalogue looks unseeded. Run: python -m app.db.seed --reset",
                file=sys.stderr,
            )
            return 1

        created: list[str] = []
        print("Generating demo activity\n")

        # -- Auto-approved, comfortably within policy -----------------------
        for email, lines, note in [
            (
                GOLD_CUSTOMER,
                [("VLV-GTE-80", 25, 10), ("GSK-CAF-150", 200, 5)],
                "Annual maintenance stock for the Bhosari plant.",
            ),
            (
                PLATINUM_CUSTOMER,
                [("PIP-GI-100", 60, 15), ("PIP-ELB-100", 120, 12)],
                "Phase 2 pipeline package.",
            ),
            (SILVER_CUSTOMER, [("VLV-NRV-50", 40, 8)], "Replacement non-return valves."),
            (GOLD_CUSTOMER, [("GAU-DIA-100", 12, 4)], "Gauges for the test bench."),
            (
                SILVER_CUSTOMER,
                [("FIL-CRT-10", 300, 10), ("LUB-SYN-20", 8, 2)],
                "Quarterly consumables.",
            ),
        ]:
            result = submit(api, email, lines, products, note)
            created.append(result.get("request", {}).get("request_number", "?"))
            print(f"  {result['request']['request_number']:<16} {result['outcome']}")

        # -- Escalated: discount above the tier ceiling ----------------------
        escalated = []
        for email, lines in [
            (GOLD_CUSTOMER, [("PMP-1200", 8, 12)]),
            (SMALL_CUSTOMER, [("PMP-SUB-30", 4, 9)]),
            (SILVER_CUSTOMER, [("MTR-IE3-75", 15, 11)]),
        ]:
            result = submit(api, email, lines, products)
            escalated.append(result)
            print(
                f"  {result['request']['request_number']:<16} {result['outcome']}"
                f"  ({len(result['exceptions'])} exception(s))"
            )

        # -- Escalated: order value over the threshold ----------------------
        big = submit(
            api,
            PLATINUM_CUSTOMER,
            [("FLW-ELC-80", 8, 5)],
            products,
            "Flow metering for the new intake works.",
        )
        escalated.append(big)
        print(
            f"  {big['request']['request_number']:<16} {big['outcome']}"
            f"  ({', '.join(e['type'] for e in big['exceptions'])})"
        )

        # -- Escalated: credit limit breach ---------------------------------
        credit = submit(api, SMALL_CUSTOMER, [("PMP-0600", 10, 5)], products)
        escalated.append(credit)
        print(
            f"  {credit['request']['request_number']:<16} {credit['outcome']}"
            f"  ({', '.join(e['type'] for e in credit['exceptions'])})"
        )

        # -- Escalated: stock shortfall -------------------------------------
        short = submit(
            api,
            GOLD_CUSTOMER,
            [("PRX-5500", 25, 2)],
            products,
            "Needed on site in three weeks.",
        )
        escalated.append(short)
        print(
            f"  {short['request']['request_number']:<16} {short['outcome']}"
            f"  ({', '.join(e['type'] for e in short['exceptions'])})"
        )

        # -- Validation failures --------------------------------------------
        below_cost = submit(api, GOLD_CUSTOMER, [("WRN-0100", 60, 15)], products)
        print(
            f"  {below_cost['request']['request_number']:<16} "
            f"{below_cost['outcome']}  (below cost price)"
        )

        print("\nResolving a few approvals\n")

        # -- Approve with an override ---------------------------------------
        first = escalated[0]
        response = decide(
            api,
            first["approval_id"],
            "APPROVE",
            override_discount_percent=8,
            comments="8% authorised for this account; 12% is outside my limit.",
        )
        if response.status_code == 200:
            body = response.json()
            print(
                f"  {first['request']['request_number']:<16} APPROVED with override 8% "
                f"-> quotation {body['quotation_id'][:8]}..."
            )

        # -- Straight approval ----------------------------------------------
        response = decide(
            api,
            escalated[1]["approval_id"],
            "APPROVE",
            comments="Within my discretion for a repeat customer.",
        )
        if response.status_code == 200:
            print(
                f"  {escalated[1]['request']['request_number']:<16} APPROVED as requested"
            )

        # -- Rejection -------------------------------------------------------
        response = decide(
            api,
            escalated[2]["approval_id"],
            "REJECT",
            comments="Margin is too thin at this discount. Resubmit at 5% or less.",
        )
        if response.status_code == 200:
            print(f"  {escalated[2]['request']['request_number']:<16} REJECTED")

        # -- Modification requested ------------------------------------------
        response = decide(
            api,
            escalated[3]["approval_id"],
            "REQUEST_MODIFICATION",
            comments="Please split this across two deliveries and resubmit.",
        )
        if response.status_code == 200:
            print(
                f"  {escalated[3]['request']['request_number']:<16} "
                f"MODIFICATION REQUESTED"
            )

        # -- Master data awaiting a manager ----------------------------------
        # A sales employee cannot add a customer or a product on their own
        # authority, so the manager's master-data queue needs something in it.
        print("\nQueuing master data for approval\n")
        for label, path, payload in MASTER_DATA_PROPOSALS:
            response = api.post(f"/master-data-requests/{path}", EMPLOYEE, payload)
            if response.status_code == 201:
                print(f"  {response.json()['reference']:<16} {label}")
            elif response.status_code == 409:
                # Already queued, or already created by an earlier run.
                print(f"  {'-':<16} {label} (already present)")

        # -- Leave the rest pending, so the queue is not empty ---------------
        pending = api.get("/approvals", MANAGER, status="PENDING")["meta"]["total"]
        master_data_pending = api.get("/master-data-requests/pending-count", MANAGER)[
            "pending"
        ]
        overview = api.get("/analytics/overview", MANAGER)

        print("\nDemo activity ready")
        print(f"  requests created      {overview['total_requests']}")
        print(f"  quotations issued     {overview['quotations_issued']}")
        print(f"  quoted value          {overview['quoted_value']:,.2f}")
        print(f"  automation rate       {overview['automation_rate_percent']}%")
        print(f"  approvals still open  {pending}")
        print(f"  master data to approve {master_data_pending}")
        return 0
    finally:
        api.close()


if __name__ == "__main__":
    sys.exit(main())
