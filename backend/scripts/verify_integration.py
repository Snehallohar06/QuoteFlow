"""End-to-end verification: drive the API exactly as the frontend does.

Every call below mirrors a function in ``frontend/src/api/*.js`` - same path,
same params, same payload shape - and goes through the Vite dev-server proxy, so
the proxy, the auth flow and the response shapes the React code depends on are
all exercised the way the browser exercises them.

Both servers must be running::

    cd backend  && uvicorn app.main:app --port 8000
    cd frontend && npm run dev

Then, passing whatever origin the dev server printed::

    python scripts/verify_integration.py
    python scripts/verify_integration.py --frontend http://localhost:5174

It is safe to re-run: the script raises the demo customer's credit limit up
front so that requests which should auto-approve still do, however much
quotation history has accumulated from previous runs.
"""

import argparse
import sys
import time

import httpx

PW = "QuoteFlow@2026"

MANAGER = "manager@quoteflow.example"
EMPLOYEE = "sales1@quoteflow.example"
CUSTOMER = "rohit.desai@acme-process.example"

passed = 0
failed = []


def check(name, condition, detail=""):
    global passed
    if condition:
        passed += 1
        print(f"  PASS  {name}")
    else:
        failed.append(f"{name} — {detail}")
        print(f"  FAIL  {name}  {detail}")


def section(title):
    print(f"\n{'=' * 72}\n{title}\n{'=' * 72}")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--frontend",
        default="http://localhost:5173",
        help="Origin the Vite dev server is serving on (default: %(default)s)",
    )
    args = parser.parse_args()

    global FRONTEND, API
    FRONTEND = args.frontend.rstrip("/")
    API = f"{FRONTEND}/api/v1"

    client = httpx.Client(timeout=30, follow_redirects=False)

    # ---- wait for the dev server ------------------------------------------
    for _ in range(60):
        try:
            if client.get(FRONTEND, timeout=2).status_code == 200:
                break
        except httpx.HTTPError:
            time.sleep(0.5)
    else:
        sys.exit("Vite dev server never became ready on :5173")

    section("0. Dev server and proxy")
    page = client.get(FRONTEND)
    check("index.html served", page.status_code == 200, f"got {page.status_code}")
    check(
        "app mount point present",
        'id="root"' in page.text,
        "no #root div in index.html",
    )
    check(
        "entry script injected",
        "/src/main.jsx" in page.text,
        "main.jsx not referenced",
    )

    health = client.get(f"{FRONTEND}/health")
    check(
        "proxy forwards non-/api path to backend? (expected 404 from Vite)",
        health.status_code in (200, 404),
        f"got {health.status_code}",
    )

    # ---- auth (api/auth.js) ----------------------------------------------
    section("1. Authentication through the proxy")

    anon = client.get(f"{API}/customers")
    check("unauthenticated request rejected", anon.status_code == 401,
          f"got {anon.status_code}")
    check(
        "error envelope shape matches client.js expectations",
        anon.json().get("error", {}).get("code") == "authentication_failed",
        anon.text[:120],
    )

    tokens = {}
    for label, email in [("manager", MANAGER), ("employee", EMPLOYEE), ("customer", CUSTOMER)]:
        response = client.post(f"{API}/auth/login", json={"email": email, "password": PW})
        ok = response.status_code == 200
        check(f"{label} login", ok, response.text[:120])
        if ok:
            body = response.json()
            check(
                f"{label} token response has access_token/refresh_token/user",
                all(k in body for k in ("access_token", "refresh_token", "user")),
                list(body),
            )
            tokens[label] = {"Authorization": f"Bearer {body['access_token']}"}

    bad = client.post(f"{API}/auth/login", json={"email": CUSTOMER, "password": "wrong"})
    check("wrong password rejected", bad.status_code == 401, f"got {bad.status_code}")

    me = client.get(f"{API}/auth/me", headers=tokens["customer"])
    check("GET /auth/me returns {user, customer}",
          me.status_code == 200 and "user" in me.json() and "customer" in me.json(),
          me.text[:120])
    customer_record = me.json()["customer"]
    check("customer record linked to the login",
          customer_record and customer_record.get("code", "").startswith("CUST-"),
          str(customer_record)[:120])

    staff_me = client.get(f"{API}/auth/me", headers=tokens["employee"])
    check("staff profile has customer=None",
          staff_me.json().get("customer") is None, staff_me.text[:120])

    refresh_token = client.post(
        f"{API}/auth/login", json={"email": CUSTOMER, "password": PW}
    ).json()["refresh_token"]
    refreshed = client.post(f"{API}/auth/refresh", json={"refresh_token": refresh_token})
    check("refresh token exchange", refreshed.status_code == 200, refreshed.text[:120])

    # Accumulated quotation history raises the demo customer's credit
    # exposure, which would eventually make a request that should auto-approve
    # escalate on the credit rule instead. Lifting the limit keeps the run
    # repeatable; the credit rule itself is covered by the backend test suite.
    gold_customer_id = me.json()["customer"]["id"]
    lifted = client.patch(
        f"{API}/customers/{gold_customer_id}",
        headers=tokens["manager"],
        json={"credit_limit": 999_000_000},
    )
    check("demo customer's credit limit lifted for a repeatable run",
          lifted.status_code == 200, lifted.text[:120])

    # ---- RBAC -------------------------------------------------------------
    section("2. Role-based access control (ProtectedRoute's server-side twin)")

    rbac = [
        ("customer -> /customers", "customer", "/customers", 403),
        ("customer -> /products", "customer", "/products", 403),
        ("customer -> /analytics/overview", "customer", "/analytics/overview", 403),
        ("customer -> /audit-logs", "customer", "/audit-logs", 403),
        ("customer -> /approvals", "customer", "/approvals", 403),
        ("employee -> /audit-logs", "employee", "/audit-logs", 403),
        ("employee -> /analytics/dashboard", "employee", "/analytics/dashboard", 403),
        ("employee -> /customers", "employee", "/customers", 200),
        ("employee -> /approvals", "employee", "/approvals", 200),
        ("manager -> /audit-logs", "manager", "/audit-logs", 200),
        ("manager -> /analytics/dashboard", "manager", "/analytics/dashboard", 200),
        ("customer -> /settings (readable by all)", "customer", "/settings", 200),
        ("customer -> /products/catalogue", "customer", "/products/catalogue", 200),
    ]
    for name, role, path, expect in rbac:
        response = client.get(f"{API}{path}", headers=tokens[role])
        check(name, response.status_code == expect,
              f"expected {expect}, got {response.status_code}")

    patch = client.patch(
        f"{API}/settings", headers=tokens["employee"],
        json={"approval_policy": {"order_value_threshold": 1}},
    )
    check("employee cannot PATCH /settings", patch.status_code == 403,
          f"got {patch.status_code}")

    # ---- catalogue (api/products.js) --------------------------------------
    section("3. Product catalogue")

    cat = client.get(f"{API}/products/catalogue", headers=tokens["customer"],
                     params={"page": 1, "page_size": 12})
    check("catalogue returns a page envelope",
          cat.status_code == 200 and {"items", "meta"} <= set(cat.json()),
          cat.text[:120])
    items = cat.json()["items"]
    check("catalogue has products", len(items) > 0, "empty catalogue")
    first = items[0]
    for field in ("id", "sku", "name", "unit_price", "available_quantity",
                  "indicative_max_discount_percent", "low_stock"):
        check(f"catalogue item has {field}", field in first, list(first))
    check("catalogue hides cost_price from a customer",
          "cost_price" not in first, "cost_price leaked to the customer view")
    check("money arrives as a JSON number",
          isinstance(first["unit_price"], (int, float)),
          f"{type(first['unit_price'])}")

    staff_products = client.get(f"{API}/products", headers=tokens["employee"],
                                params={"page_size": 5})
    check("staff product list includes cost_price",
          "cost_price" in staff_products.json()["items"][0], "missing cost_price")

    cats = client.get(f"{API}/products/categories", headers=tokens["customer"])
    check("categories endpoint", cats.status_code == 200 and len(cats.json()) > 0,
          cats.text[:120])

    search = client.get(f"{API}/products/catalogue", headers=tokens["customer"],
                        params={"search": "pump"})
    check("catalogue search filters", search.status_code == 200,
          search.text[:120])

    avail = client.post(
        f"{API}/products/check-availability", headers=tokens["customer"],
        json={"items": [{"product_id": first["id"], "quantity": 5}]},
    )
    check("availability pre-check",
          avail.status_code == 200 and "all_available" in avail.json(),
          avail.text[:150])
    check("availability line carries status/shortfall/message",
          {"status", "shortfall", "message"} <= set(avail.json()["lines"][0]),
          list(avail.json()["lines"][0]))

    # ---- request submission (api/requests.js) -----------------------------
    section("4. Quotation request submission and the workflow")

    by_sku = {}
    page = 1
    while True:
        response = client.get(f"{API}/products/catalogue", headers=tokens["manager"],
                              params={"page": page, "page_size": 50})
        body = response.json()
        by_sku.update({item["sku"]: item for item in body["items"]})
        if page >= body["meta"]["total_pages"]:
            break
        page += 1
    check("full catalogue paged through", len(by_sku) >= 15, f"{len(by_sku)} products")

    # 4a. auto-approved
    auto = client.post(
        f"{API}/quotation-requests", headers=tokens["customer"],
        json={
            "items": [{"product_id": by_sku["VLV-NRV-50"]["id"], "quantity": 30,
                       "requested_discount_percent": 10}],
            "customer_notes": "Integration test — within policy.",
            "submit": True,
        },
    )
    check("create+submit returns 201", auto.status_code == 201, auto.text[:200])
    auto_body = auto.json()
    check("response has {submitted, workflow}",
          auto_body.get("submitted") is True and "workflow" in auto_body,
          list(auto_body))
    wf = auto_body["workflow"]
    check("completed outcome", wf["outcome"] == "COMPLETED", wf["outcome"])
    check(
        "success gate fully satisfied",
        all(wf["gate"].values()),
        wf["gate"],
    )
    check(
        "independent verification passed",
        wf["check_report"]["passed"] is True,
        wf.get("check_report"),
    )
    check("quotation issued immediately", bool(wf["quotation_id"]), "no quotation_id")
    check("no approval task", wf["approval_id"] is None, wf["approval_id"])
    check("workflow exposes duration_ms", isinstance(wf["duration_ms"], int),
          type(wf["duration_ms"]))
    pricing = wf["request"]["pricing"]
    for field in ("subtotal", "total_discount", "taxable_amount", "total_tax",
                  "final_amount", "effective_discount_percent", "currency",
                  "tax_label", "line_count", "total_quantity"):
        check(f"pricing has {field}", field in pricing, list(pricing))
    check("totals reconcile: taxable = subtotal - discount",
          abs(pricing["taxable_amount"] - (pricing["subtotal"] - pricing["total_discount"])) < 0.005,
          str(pricing))
    check("totals reconcile: final = taxable + tax",
          abs(pricing["final_amount"] - (pricing["taxable_amount"] + pricing["total_tax"])) < 0.005,
          str(pricing))
    check("status history recorded",
          len(wf["request"]["status_history"]) >= 3,
          wf["request"]["status_history"])

    # 4b. draft, then submit separately
    draft = client.post(
        f"{API}/quotation-requests", headers=tokens["customer"],
        json={"items": [{"product_id": by_sku["GSK-CAF-150"]["id"], "quantity": 100}],
              "submit": False},
    )
    check("draft creation returns {submitted: false, request}",
          draft.status_code == 201 and draft.json()["submitted"] is False,
          draft.text[:150])
    draft_request = draft.json()["request"]
    check("draft status is DRAFT", draft_request["status"] == "DRAFT",
          draft_request["status"])
    check("draft is not priced", draft_request["pricing"] is None,
          str(draft_request["pricing"]))

    patched = client.patch(
        f"{API}/quotation-requests/{draft_request['id']}", headers=tokens["customer"],
        json={"items": [{"product_id": by_sku["GSK-CAF-150"]["id"], "quantity": 150}],
              "customer_notes": "Quantity revised."},
    )
    check("draft can be edited", patched.status_code == 200, patched.text[:150])
    check("edit applied", patched.json()["items"][0]["quantity"] == 150,
          patched.json()["items"][0]["quantity"])

    submitted = client.post(
        f"{API}/quotation-requests/{draft_request['id']}/submit",
        headers=tokens["customer"],
    )
    check("draft submit runs the workflow", submitted.status_code == 200,
          submitted.text[:150])
    check("submitted draft reached a settled state",
          submitted.json()["resulting_status"] in ("COMPLETED", "PENDING_APPROVAL"),
          submitted.json()["resulting_status"])

    # 4c. escalated
    escalated = client.post(
        f"{API}/quotation-requests", headers=tokens["customer"],
        json={
            "items": [{"product_id": by_sku["PMP-1200"]["id"], "quantity": 8,
                       "requested_discount_percent": 12}],
            "submit": True,
        },
    )
    esc = escalated.json()["workflow"]
    check("over-ceiling discount escalates",
          esc["outcome"] == "PENDING_APPROVAL", esc["outcome"])
    check("approval task created", bool(esc["approval_id"]), "no approval_id")
    check("exception reported with context",
          esc["exceptions"] and "context" in esc["exceptions"][0],
          str(esc["exceptions"])[:150])
    check("exception context money is numeric",
          isinstance(esc["exceptions"][0]["context"].get("max_allowed_percent"), (int, float)),
          str(esc["exceptions"][0]["context"])[:150])
    check("line flagged as a discount exception",
          esc["request"]["items"][0]["discount_exception"] is True,
          esc["request"]["items"][0])

    # 4d. validation failure
    failed_request = client.post(
        f"{API}/quotation-requests", headers=tokens["customer"],
        json={
            "items": [{"product_id": by_sku["WRN-0100"]["id"], "quantity": 60,
                       "requested_discount_percent": 15}],
            "submit": True,
        },
    )
    fail_wf = failed_request.json()["workflow"]
    check("below-cost discount fails validation",
          fail_wf["outcome"] == "VALIDATION_FAILED", fail_wf["outcome"])
    check("validation errors are human readable",
          fail_wf["validation_errors"] and "cost price" in fail_wf["validation_errors"][0],
          str(fail_wf["validation_errors"])[:150])

    # 4e. schema rejections the form guards against
    dup = client.post(
        f"{API}/quotation-requests", headers=tokens["customer"],
        json={"items": [
            {"product_id": by_sku["PMP-0600"]["id"], "quantity": 2},
            {"product_id": by_sku["PMP-0600"]["id"], "quantity": 3}],
            "submit": True},
    )
    check("duplicate product line rejected (422)", dup.status_code == 422,
          f"got {dup.status_code}")
    zero = client.post(
        f"{API}/quotation-requests", headers=tokens["customer"],
        json={"items": [{"product_id": by_sku["PMP-0600"]["id"], "quantity": 0}],
              "submit": True},
    )
    check("zero quantity rejected (422)", zero.status_code == 422,
          f"got {zero.status_code}")
    empty = client.post(
        f"{API}/quotation-requests", headers=tokens["customer"],
        json={"items": [], "submit": True},
    )
    check("empty line list rejected (422)", empty.status_code == 422,
          f"got {empty.status_code}")

    # ---- execution trace --------------------------------------------------
    section("5. Workflow execution trace")

    execs = client.get(
        f"{API}/quotation-requests/{esc['request']['id']}/executions",
        headers=tokens["customer"],
    )
    check("executions endpoint", execs.status_code == 200, execs.text[:150])
    trace = execs.json()[0]
    check("all eight pipeline steps recorded",
          [s["step"] for s in trace["steps"]] == [
              "VALIDATE_REQUEST", "CHECK_AVAILABILITY", "CALCULATE_PRICING",
              "EVALUATE_DISCOUNT_RULES", "DETERMINE_APPROVAL_ROUTE",
              "GENERATE_DOCUMENT", "VERIFY_DOCUMENT", "FINALISE"],
          [s["step"] for s in trace["steps"]])
    check("execution records the attempt and retry counts",
          trace["attempt_number"] >= 1 and trace["retries_used"] == 0,
          (trace.get("attempt_number"), trace.get("retries_used")))
    check("execution records the budget",
          trace["budget"].get("max_attempts", 0) > 0,
          trace.get("budget"))
    check("steps carry status + duration + output",
          all({"status", "duration_ms", "output"} <= set(s) for s in trace["steps"]),
          "missing step fields")
    pricing_step = next(s for s in trace["steps"] if s["step"] == "CALCULATE_PRICING")
    check("pricing step output is numeric",
          isinstance(pricing_step["output"].get("final_amount"), (int, float)),
          str(pricing_step["output"])[:150])
    rules_step = next(s for s in trace["steps"]
                      if s["step"] == "EVALUATE_DISCOUNT_RULES")
    check("discount step carries the rule trace",
          isinstance(rules_step["output"].get("rules"), list),
          str(rules_step["output"])[:150])
    check("engine version present", trace.get("engine_version") == "2.0.0",
          trace.get("engine_version"))

    # ---- approvals (api/approvals.js) -------------------------------------
    section("6. Manager approval interface")

    count = client.get(f"{API}/approvals/pending-count", headers=tokens["manager"])
    check("pending-count endpoint",
          count.status_code == 200 and "pending" in count.json(), count.text[:120])

    queue = client.get(f"{API}/approvals", headers=tokens["manager"],
                       params={"status": "PENDING", "page_size": 20})
    check("approval queue lists tasks",
          queue.status_code == 200 and queue.json()["meta"]["total"] >= 1,
          queue.text[:150])

    detail = client.get(f"{API}/approvals/{esc['approval_id']}",
                        headers=tokens["manager"])
    check("approval detail bundles full context",
          detail.status_code == 200 and
          {"approval", "request", "customer", "latest_execution",
           "recent_quotations"} <= set(detail.json()),
          list(detail.json()))

    employee_decide = client.post(
        f"{API}/approvals/{esc['approval_id']}/decision", headers=tokens["employee"],
        json={"decision": "APPROVE"},
    )
    check("employee cannot decide", employee_decide.status_code == 403,
          f"got {employee_decide.status_code}")

    no_comment = client.post(
        f"{API}/approvals/{esc['approval_id']}/decision", headers=tokens["manager"],
        json={"decision": "REJECT"},
    )
    check("rejection without a comment refused (409)", no_comment.status_code == 409,
          f"got {no_comment.status_code}")

    bad_override = client.post(
        f"{API}/approvals/{esc['approval_id']}/decision", headers=tokens["manager"],
        json={"decision": "APPROVE", "override_discount_percent": 55},
    )
    check("override above policy refused (409)", bad_override.status_code == 409,
          f"got {bad_override.status_code}")

    approved = client.post(
        f"{API}/approvals/{esc['approval_id']}/decision", headers=tokens["manager"],
        json={"decision": "APPROVE", "override_discount_percent": 8,
              "comments": "Integration test: 8% authorised."},
    )
    check("approve with override succeeds", approved.status_code == 200,
          approved.text[:200])
    decision = approved.json()
    check("decision response shape",
          {"approval", "request", "quotation_id", "execution_id"} <= set(decision),
          list(decision))
    check("override applied to the line",
          decision["request"]["items"][0]["applied_discount_percent"] == 8.0,
          decision["request"]["items"][0]["applied_discount_percent"])
    check("request now COMPLETED", decision["request"]["status"] == "COMPLETED",
          decision["request"]["status"])
    check("quotation generated on approval", bool(decision["quotation_id"]),
          "no quotation_id")

    double = client.post(
        f"{API}/approvals/{esc['approval_id']}/decision", headers=tokens["manager"],
        json={"decision": "REJECT", "comments": "second attempt"},
    )
    check("same task cannot be decided twice (409)", double.status_code == 409,
          f"got {double.status_code}")

    reruns = client.get(
        f"{API}/quotation-requests/{esc['request']['id']}/executions",
        headers=tokens["manager"],
    ).json()
    check("approval left its own execution trace",
          len(reruns) == 2 and {e["trigger"] for e in reruns} == {"SUBMISSION", "APPROVAL"},
          [e["trigger"] for e in reruns])

    # reject + modification paths on fresh tasks
    for decision_kind, expect_status in [("REJECT", "REJECTED"),
                                         ("REQUEST_MODIFICATION", "MODIFICATION_REQUESTED")]:
        fresh = client.post(
            f"{API}/quotation-requests", headers=tokens["customer"],
            json={"items": [{"product_id": by_sku["MTR-IE3-75"]["id"], "quantity": 10,
                             "requested_discount_percent": 11}],
                  "submit": True},
        ).json()["workflow"]
        if not fresh.get("approval_id"):
            check(f"{decision_kind}: task raised", False, fresh["outcome"])
            continue
        response = client.post(
            f"{API}/approvals/{fresh['approval_id']}/decision",
            headers=tokens["manager"],
            json={"decision": decision_kind, "comments": f"Integration test {decision_kind}."},
        )
        check(f"{decision_kind} recorded", response.status_code == 200,
              response.text[:150])
        if response.status_code == 200:
            check(f"{decision_kind} -> request {expect_status}",
                  response.json()["request"]["status"] == expect_status,
                  response.json()["request"]["status"])
            check(f"{decision_kind} produced no quotation",
                  response.json()["quotation_id"] is None,
                  response.json()["quotation_id"])

    # ---- quotations (api/quotations.js) -----------------------------------
    section("7. Quotations, PDF and verification")

    quotation_id = wf["quotation_id"]
    quotation = client.get(f"{API}/quotations/{quotation_id}", headers=tokens["customer"])
    check("quotation detail", quotation.status_code == 200, quotation.text[:150])
    qdata = quotation.json()
    for field in ("quotation_number", "seller", "buyer", "items", "pricing", "terms",
                  "verification_code", "integrity_hash", "valid_until",
                  "auto_approved", "download_count"):
        check(f"quotation has {field}", field in qdata, list(qdata))

    pdf = client.get(f"{API}/quotations/{quotation_id}/pdf", headers=tokens["customer"])
    check("PDF download returns application/pdf",
          pdf.status_code == 200 and pdf.headers["content-type"] == "application/pdf",
          f"{pdf.status_code} {pdf.headers.get('content-type')}")
    check("PDF body is a real PDF", pdf.content.startswith(b"%PDF-"),
          pdf.content[:8])
    check("PDF has reasonable size", len(pdf.content) > 2000, len(pdf.content))

    after = client.get(f"{API}/quotations/{quotation_id}", headers=tokens["customer"])
    check("download counter incremented", after.json()["download_count"] >= 1,
          after.json()["download_count"])

    verify = client.get(f"{API}/verify/{qdata['verification_code']}")
    check("public verification needs no token", verify.status_code == 200,
          verify.text[:150])
    check("verification reports valid", verify.json()["valid"] is True,
          verify.text[:200])
    check("verification payload is thin but useful",
          {"quotation_number", "customer_name", "final_amount", "expired"}
          <= set(verify.json()),
          list(verify.json()))

    lower = client.get(f"{API}/verify/{qdata['verification_code'].lower()}")
    check("verification is case-insensitive", lower.json()["valid"] is True,
          lower.text[:120])

    unknown = client.get(f"{API}/verify/AAAA-BBBB-CCCC")
    check("unknown code reports invalid without leaking",
          unknown.status_code == 200 and unknown.json()["valid"] is False
          and unknown.json()["quotation_number"] is None,
          unknown.text[:150])

    # customer isolation
    other_login = client.post(
        f"{API}/auth/login",
        json={"email": "imran@sunrise-fab.example", "password": PW},
    ).json()
    other = {"Authorization": f"Bearer {other_login['access_token']}"}
    cross = client.get(f"{API}/quotations/{quotation_id}", headers=other)
    check("customer cannot read another's quotation", cross.status_code == 403,
          f"got {cross.status_code}")
    cross_request = client.get(
        f"{API}/quotation-requests/{wf['request']['id']}", headers=other
    )
    check("customer cannot read another's request", cross_request.status_code == 403,
          f"got {cross_request.status_code}")

    malformed = client.get(f"{API}/quotations/not-an-id", headers=tokens["manager"])
    check("malformed id returns 422 not 500", malformed.status_code == 422,
          f"got {malformed.status_code}")

    # ---- customers & products CRUD ----------------------------------------
    section("8. Customer and product management")

    customers = client.get(f"{API}/customers", headers=tokens["employee"],
                           params={"page_size": 20})
    check("customer list", customers.status_code == 200, customers.text[:120])
    check("customer has available_credit",
          "available_credit" in customers.json()["items"][0],
          list(customers.json()["items"][0]))

    target = customers.json()["items"][0]
    summary = client.get(f"{API}/customers/{target['id']}/summary",
                         headers=tokens["employee"])
    check("customer summary",
          summary.status_code == 200 and
          {"customer", "total_requests", "requests_by_status", "quoted_value"}
          <= set(summary.json()),
          list(summary.json()))

    # Creating master data is manager-only; an employee goes through the
    # approval queue, which section 8b exercises.
    new_customer = client.post(
        f"{API}/customers", headers=tokens["manager"],
        json={"company_name": "Integration Test Co", "contact_name": "Test Contact",
              "email": f"it-{int(time.time())}@test.example", "phone": "+91 90000 00001",
              "tier": "SILVER", "credit_limit": 250000},
    )
    check("create customer", new_customer.status_code == 201, new_customer.text[:150])
    created_id = new_customer.json()["id"]
    check("generated customer code",
          new_customer.json()["code"].startswith("CUST-"), new_customer.json()["code"])

    # Editing an existing record still needs no approval.
    updated = client.patch(f"{API}/customers/{created_id}", headers=tokens["employee"],
                           json={"tier": "GOLD", "credit_limit": 500000})
    check("update customer", updated.status_code == 200 and
          updated.json()["tier"] == "GOLD", updated.text[:150])

    blocked = client.post(f"{API}/customers/{created_id}/status",
                          headers=tokens["manager"],
                          params={"new_status": "BLOCKED"})
    check("manager can block a customer", blocked.status_code == 200,
          blocked.text[:150])
    emp_block = client.post(f"{API}/customers/{created_id}/status",
                            headers=tokens["employee"],
                            params={"new_status": "ACTIVE"})
    check("employee cannot block a customer", emp_block.status_code == 403,
          f"got {emp_block.status_code}")

    sku = f"IT-{int(time.time())}"
    new_product = client.post(
        f"{API}/products", headers=tokens["manager"],
        json={"sku": sku.lower(), "name": "Integration Test Widget",
              "category": "Testing", "unit_price": 1500, "cost_price": 900,
              "stock_quantity": 40, "reorder_level": 10, "lead_time_days": 5},
    )
    check("create product", new_product.status_code == 201, new_product.text[:150])
    check("SKU normalised to upper case", new_product.json()["sku"] == sku,
          new_product.json()["sku"])
    product_id = new_product.json()["id"]

    stock_up = client.post(f"{API}/products/{product_id}/stock",
                           headers=tokens["employee"],
                           json={"delta": 25, "reason": "Integration test receipt"})
    check("stock movement applied",
          stock_up.status_code == 200 and stock_up.json()["stock_quantity"] == 65,
          stock_up.text[:150])
    stock_down = client.post(f"{API}/products/{product_id}/stock",
                             headers=tokens["employee"], json={"delta": -1000})
    check("stock cannot go negative (409)", stock_down.status_code == 409,
          f"got {stock_down.status_code}")

    dup_sku = client.post(
        f"{API}/products", headers=tokens["manager"],
        json={"sku": sku, "name": "Duplicate", "category": "Testing",
              "unit_price": 100},
    )
    check("duplicate SKU refused (409)", dup_sku.status_code == 409,
          f"got {dup_sku.status_code}")

    emp_delete = client.delete(f"{API}/products/{product_id}",
                               headers=tokens["employee"])
    check("employee cannot discontinue a product", emp_delete.status_code == 403,
          f"got {emp_delete.status_code}")
    mgr_delete = client.delete(f"{API}/products/{product_id}",
                               headers=tokens["manager"])
    check("manager discontinues (soft delete)",
          mgr_delete.status_code == 200 and
          mgr_delete.json()["status"] == "DISCONTINUED",
          mgr_delete.text[:150])
    still = client.get(f"{API}/products/{product_id}", headers=tokens["manager"])
    check("discontinued product still retrievable", still.status_code == 200,
          f"got {still.status_code}")

    # ---- master-data approval (api/masterData.js) --------------------------
    section("8b. Master-data approval (employee proposes, manager decides)")

    stamp = int(time.time())
    proposed_customer = {
        "company_name": f"Approval Flow Co {stamp}",
        "contact_name": "Queue Contact",
        "email": f"queue-{stamp}@test.example",
        "phone": "+91 90000 00009",
        "tier": "SILVER",
        "credit_limit": 180000,
    }
    proposed_product = {
        "sku": f"MDR-{stamp}",
        "name": "Approval Flow Widget",
        "category": "Testing",
        "unit_price": 2100,
        "cost_price": 1300,
        "stock_quantity": 25,
        "lead_time_days": 4,
    }

    emp_customer = client.post(f"{API}/customers", headers=tokens["employee"],
                               json=proposed_customer)
    check("employee cannot create a customer directly (403)",
          emp_customer.status_code == 403, f"got {emp_customer.status_code}")
    check("the refusal names the approval route",
          emp_customer.json().get("error", {}).get("details", {}).get("submit_route")
          == "/api/v1/master-data-requests/customers",
          emp_customer.text[:150])
    emp_product = client.post(f"{API}/products", headers=tokens["employee"],
                              json=proposed_product)
    check("employee cannot create a product directly (403)",
          emp_product.status_code == 403, f"got {emp_product.status_code}")

    raised = client.post(f"{API}/master-data-requests/customers",
                         headers=tokens["employee"],
                         json={"customer": proposed_customer,
                               "reason": "Integration check."})
    check("employee can submit a customer for approval",
          raised.status_code == 201, raised.text[:180])
    for field in ("id", "reference", "entity_type", "status", "label", "payload",
                  "reason", "requested_by_name", "created_at"):
        check(f"proposal has {field}", field in raised.json(), list(raised.json()))
    check("proposal starts PENDING", raised.json()["status"] == "PENDING",
          raised.json()["status"])
    check("proposal reference is numbered",
          raised.json()["reference"].startswith("MDR-"), raised.json()["reference"])
    check("nothing created yet", raised.json()["created_entity_id"] is None,
          raised.json()["created_entity_id"])
    raised_id = raised.json()["id"]

    dup_raise = client.post(f"{API}/master-data-requests/customers",
                            headers=tokens["employee"],
                            json={"customer": proposed_customer})
    check("the same record cannot be queued twice (409)",
          dup_raise.status_code == 409, f"got {dup_raise.status_code}")

    product_raised = client.post(f"{API}/master-data-requests/products",
                                 headers=tokens["employee"],
                                 json={"product": proposed_product,
                                       "reason": "Integration check."})
    check("employee can submit a product for approval",
          product_raised.status_code == 201, product_raised.text[:180])
    product_raised_id = product_raised.json()["id"]

    queue = client.get(f"{API}/master-data-requests", headers=tokens["manager"],
                       params={"status": "PENDING", "page_size": 100})
    check("manager sees the queue", queue.status_code == 200, queue.text[:150])
    check("the proposal is in it",
          raised.json()["reference"] in
          [item["reference"] for item in queue.json()["items"]],
          queue.json()["meta"])
    check("queue is paginated like every other list",
          {"items", "meta"} <= set(queue.json()), list(queue.json()))

    counted = client.get(f"{API}/master-data-requests/pending-count",
                         headers=tokens["manager"])
    check("pending count for the sidebar badge",
          counted.status_code == 200 and counted.json()["pending"] >= 2,
          counted.text[:120])

    filtered = client.get(f"{API}/master-data-requests", headers=tokens["manager"],
                          params={"entity_type": "PRODUCT", "page_size": 100})
    check("queue filters by entity type",
          all(item["entity_type"] == "PRODUCT" for item in filtered.json()["items"]),
          filtered.json()["meta"])

    own = client.get(f"{API}/master-data-requests", headers=tokens["employee"],
                     params={"page_size": 100})
    check("employee sees only their own requests",
          all(item["requested_by_name"] for item in own.json()["items"]),
          own.json()["meta"])

    one = client.get(f"{API}/master-data-requests/{raised_id}",
                     headers=tokens["employee"])
    check("employee can read their own request", one.status_code == 200,
          one.text[:150])

    self_decide = client.post(f"{API}/master-data-requests/{raised_id}/decision",
                              headers=tokens["employee"], json={"approve": True})
    check("employee cannot decide (403)", self_decide.status_code == 403,
          f"got {self_decide.status_code}")
    cust_decide = client.post(f"{API}/master-data-requests/{raised_id}/decision",
                              headers=tokens["customer"], json={"approve": True})
    check("customer cannot decide (403)", cust_decide.status_code == 403,
          f"got {cust_decide.status_code}")

    blank_refusal = client.post(
        f"{API}/master-data-requests/{product_raised_id}/decision",
        headers=tokens["manager"], json={"approve": False})
    check("refusal without a reason is refused (409)",
          blank_refusal.status_code == 409, f"got {blank_refusal.status_code}")
    refused = client.post(
        f"{API}/master-data-requests/{product_raised_id}/decision",
        headers=tokens["manager"],
        json={"approve": False, "comments": "Check the cost price."})
    check("manager can refuse", refused.status_code == 200, refused.text[:180])
    check("a refusal creates nothing", refused.json()["product"] is None,
          refused.json()["product"])
    check("the refusal is recorded on the request",
          refused.json()["request"]["status"] == "REJECTED",
          refused.json()["request"]["status"])

    approved = client.post(f"{API}/master-data-requests/{raised_id}/decision",
                           headers=tokens["manager"],
                           json={"approve": True, "comments": "Approved."})
    check("manager can approve", approved.status_code == 200, approved.text[:180])
    check("approving returns the created customer",
          approved.json()["customer"]["company_name"]
          == proposed_customer["company_name"],
          approved.json()["customer"])
    check("the created customer has a generated code",
          approved.json()["customer"]["code"].startswith("CUST-"),
          approved.json()["customer"]["code"])
    check("the submitted tier survived the round trip",
          approved.json()["customer"]["tier"] == "SILVER",
          approved.json()["customer"]["tier"])
    check("the request links to what it created",
          approved.json()["request"]["created_entity_id"]
          == approved.json()["customer"]["id"],
          approved.json()["request"])

    decided_twice = client.post(f"{API}/master-data-requests/{raised_id}/decision",
                                headers=tokens["manager"], json={"approve": True})
    check("a decided request cannot be decided again (409)",
          decided_twice.status_code == 409, f"got {decided_twice.status_code}")

    withdrawable = client.post(
        f"{API}/master-data-requests/customers", headers=tokens["employee"],
        json={"customer": {**proposed_customer,
                           "email": f"wd-{stamp}@test.example",
                           "company_name": f"Withdraw Me {stamp}"}})
    withdrawn = client.post(
        f"{API}/master-data-requests/{withdrawable.json()['id']}/withdraw",
        headers=tokens["employee"])
    check("employee can withdraw their own request",
          withdrawn.status_code == 200 and withdrawn.json()["status"] == "WITHDRAWN",
          withdrawn.text[:150])

    # ---- analytics (api/analytics.js) --------------------------------------
    section("9. Analytics")

    dash = client.get(f"{API}/analytics/dashboard", headers=tokens["manager"],
                      params={"days": 30})
    check("dashboard endpoint", dash.status_code == 200, dash.text[:150])
    sections = {"overview", "request_trend", "revenue_trend", "top_products",
                "top_customers", "exception_breakdown", "approval_performance",
                "workflow_performance"}
    check("dashboard returns every section", sections <= set(dash.json()),
          list(dash.json()))
    ov = dash.json()["overview"]
    for field in ("total_requests", "requests_by_status", "open_requests",
                  "approval_rate_percent", "quotations_issued", "quoted_value",
                  "average_quotation_value", "total_discount_given",
                  "discount_rate_percent", "automation_rate_percent",
                  "pending_approvals", "overdue_approvals", "live_quotations"):
        check(f"overview has {field}", field in ov, list(ov))
    check("overview money is numeric, not a string",
          isinstance(ov["quoted_value"], (int, float)), type(ov["quoted_value"]))
    check("request_trend rows shaped for the chart",
          not dash.json()["request_trend"] or
          {"date", "total", "approved", "rejected", "pending", "failed"}
          <= set(dash.json()["request_trend"][0]),
          str(dash.json()["request_trend"][:1])[:150])
    check("revenue_trend rows shaped for the chart",
          not dash.json()["revenue_trend"] or
          {"month", "quotations", "quoted_value", "discount"}
          <= set(dash.json()["revenue_trend"][0]),
          str(dash.json()["revenue_trend"][:1])[:150])
    wp = dash.json()["workflow_performance"]
    check("workflow_performance has per-step rows",
          wp["steps"] and {"step", "executions", "average_duration_ms", "failures"}
          <= set(wp["steps"][0]),
          str(wp["steps"][:1])[:150])

    for path in ("/analytics/overview", "/analytics/requests/trend",
                 "/analytics/products/top"):
        response = client.get(f"{API}{path}", headers=tokens["employee"])
        check(f"employee can read {path}", response.status_code == 200,
              f"got {response.status_code}")

    # ---- notifications, audit, settings -----------------------------------
    section("10. Notifications, audit trail and settings")

    notifs = client.get(f"{API}/notifications", headers=tokens["manager"],
                        params={"page_size": 10})
    check("notification inbox", notifs.status_code == 200, notifs.text[:120])
    unread = client.get(f"{API}/notifications/unread-count", headers=tokens["manager"])
    check("unread count", unread.status_code == 200 and "unread" in unread.json(),
          unread.text[:120])
    if notifs.json()["items"]:
        nid = notifs.json()["items"][0]["id"]
        marked = client.post(f"{API}/notifications/{nid}/read",
                             headers=tokens["manager"])
        check("mark one read", marked.status_code == 200, marked.text[:120])
        wrong_user = client.post(f"{API}/notifications/{nid}/read",
                                 headers=tokens["customer"])
        check("cannot mark another user's notification (404)",
              wrong_user.status_code == 404, f"got {wrong_user.status_code}")
    all_read = client.post(f"{API}/notifications/read-all", headers=tokens["manager"])
    check("mark all read", all_read.status_code == 200, all_read.text[:120])

    audit = client.get(f"{API}/audit-logs", headers=tokens["manager"],
                       params={"page_size": 25})
    check("audit log list", audit.status_code == 200 and audit.json()["meta"]["total"] > 0,
          audit.text[:150])
    entry = audit.json()["items"][0]
    for field in ("action", "entity_type", "summary", "actor_email", "actor_role",
                  "changes", "metadata", "created_at"):
        check(f"audit entry has {field}", field in entry, list(entry))

    trail = client.get(
        f"{API}/audit-logs/quotation_request/{wf['request']['id']}",
        headers=tokens["employee"],
    )
    check("entity audit trail", trail.status_code == 200 and len(trail.json()) > 0,
          trail.text[:150])

    settings = client.get(f"{API}/settings", headers=tokens["customer"])
    check("settings readable by a customer", settings.status_code == 200,
          settings.text[:120])
    policy = client.get(f"{API}/settings/discount-policy", headers=tokens["customer"])
    check("discount policy endpoint",
          policy.status_code == 200 and "tiers" in policy.json(), policy.text[:150])
    check("policy tier percentages are numeric",
          isinstance(policy.json()["tiers"][0]["max_discount_percent"], (int, float)),
          str(policy.json()["tiers"][0]))

    original_threshold = settings.json()["approval_policy"]["order_value_threshold"]
    tuned = client.patch(f"{API}/settings", headers=tokens["manager"],
                         json={"approval_policy": {"order_value_threshold": 123456}})
    check("manager can retune the rule book", tuned.status_code == 200,
          tuned.text[:150])
    check("patch applied",
          tuned.json()["approval_policy"]["order_value_threshold"] == 123456,
          tuned.json()["approval_policy"]["order_value_threshold"])
    check("sibling fields preserved by the nested merge",
          tuned.json()["approval_policy"]["approval_sla_hours"] ==
          settings.json()["approval_policy"]["approval_sla_hours"],
          tuned.json()["approval_policy"])
    invalid = client.patch(f"{API}/settings", headers=tokens["manager"],
                           json={"discount_policy": {"tiers": []}})
    check("invalid rule book rejected (422)", invalid.status_code == 422,
          f"got {invalid.status_code}")
    client.patch(f"{API}/settings", headers=tokens["manager"],
                 json={"approval_policy": {"order_value_threshold": original_threshold}})

    # ---- cancel / reprocess ------------------------------------------------
    section("11. Cancel and reprocess")

    cancellable = client.post(
        f"{API}/quotation-requests", headers=tokens["customer"],
        json={"items": [{"product_id": by_sku["GAU-DIA-100"]["id"], "quantity": 2}],
              "submit": False},
    ).json()["request"]
    cancelled = client.post(
        f"{API}/quotation-requests/{cancellable['id']}/cancel",
        headers=tokens["customer"], json={"reason": "Integration test"},
    )
    check("cancel a draft", cancelled.status_code == 200 and
          cancelled.json()["status"] == "CANCELLED", cancelled.text[:150])
    recancel = client.post(
        f"{API}/quotation-requests/{cancellable['id']}/cancel",
        headers=tokens["customer"], json={},
    )
    check("cancelled request cannot be cancelled again (409)",
          recancel.status_code == 409, f"got {recancel.status_code}")

    reprocess = client.post(
        f"{API}/quotation-requests/{fail_wf['request']['id']}/reprocess",
        headers=tokens["employee"],
    )
    check("staff can reprocess a failed request", reprocess.status_code == 200,
          reprocess.text[:150])
    cust_reprocess = client.post(
        f"{API}/quotation-requests/{fail_wf['request']['id']}/reprocess",
        headers=tokens["customer"],
    )
    check("customer cannot reprocess", cust_reprocess.status_code == 403,
          f"got {cust_reprocess.status_code}")

    notes = client.put(
        f"{API}/quotation-requests/{wf['request']['id']}/internal-notes",
        headers=tokens["employee"], json={"internal_notes": "Integration test note."},
    )
    check("staff can set internal notes", notes.status_code == 200, notes.text[:150])
    cust_notes = client.put(
        f"{API}/quotation-requests/{wf['request']['id']}/internal-notes",
        headers=tokens["customer"], json={"internal_notes": "nope"},
    )
    check("customer cannot set internal notes", cust_notes.status_code == 403,
          f"got {cust_notes.status_code}")

    client.close()

    # ---- summary -----------------------------------------------------------
    print(f"\n{'=' * 72}")
    print(f"  {passed} passed, {len(failed)} failed")
    print("=" * 72)
    if failed:
        print("\nFailures:")
        for item in failed:
            print(f"  - {item}")
        return 1
    print("\nALL INTEGRATION CHECKS PASSED\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
