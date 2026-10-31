# QuoteFlow — Demonstration Guide

Six scenarios, roughly 12 minutes. Each one maps to a test that already proves
it, so nothing here depends on luck.

---

## Setup (do this before the room is watching)

```bash
# Terminal 1
cd backend && .venv\Scripts\activate
python -m app.db.seed --reset
uvicorn app.main:app --reload --port 8000

# Terminal 2
cd frontend && npm run dev

# Terminal 3 — populates the dashboards and approval queue
cd backend && python scripts/demo_activity.py
```

Open the URL the dev server printed (`http://localhost:5173` by default) and
have two browser profiles or windows ready:

| Window | Account | Password |
| --- | --- | --- |
| Customer | `rohit.desai@acme-process.example` | `QuoteFlow@2026` |
| Manager | `manager@quoteflow.example` | `QuoteFlow@2026` |

In development the login page lists the accounts and fills the form on click.

---

## The one-sentence framing

> QuoteFlow turns a quotation request into a verified document using explicit
> business rules, and it can prove what it did at every step — there is no model
> and no inference anywhere in it.

---

## Scenario 1 — A valid request becomes a verified quotation

**Proves:** the happy path, the success gate, independent verification.

1. As the **customer**, go to **Product Catalogue**. Point out that each product
   shows *the discount this customer may request* — 4% on most items, because
   Acme is a Gold-tier account (2% band + 2% tier bonus).
2. **Add to request** on *Gate Valve 80 mm*. On the request form set quantity to
   **25** and discount to **10%**.
3. Note the right-hand panel says **Within policy** — 25 units sits in the 21–50
   band, which allows 10%.
4. **Submit request.**
5. The toast reads *approved automatically* and you land on the request detail.

**What to show on that page:**

- **Process stage** — nine stages, all green. These are read from the stored
  execution trace, not assumed.
- **Success gate** — all six conditions ticked. Say: *the request could not have
  been marked completed with any one of these unticked.*
- **Priced lines** — ₹1,06,250 subtotal, ₹10,625 discount, ₹17,212.50 tax,
  ₹1,12,837.50 total. Point out that tax is charged on the **discounted**
  amount, and that the lines add up to the total exactly because every figure
  is `Decimal`, rounded per line.
- **Workflow execution** — expand `VERIFY_DOCUMENT`. This is the checker tool:
  it re-read the product catalogue and recomputed every amount in longhand,
  independently of the code that produced them.
- Click through to the quotation, **Download** the PDF, then **Verify**. The
  verification code is printed on the document; the check is public and needs no
  login.

---

## Scenario 2 — Invalid information is caught and nothing is issued

**Proves:** validation, failure recording, information preserved.

1. As **staff** (`sales1@quoteflow.example`), go to **Products**, find
   `PMP-LEG-900 — Legacy Pump 900 LPM`. It is already **Discontinued**.
2. As the **customer**, submit a request for any product, then — quicker for a
   demo — open **Exception Management** as staff and show the request that
   already failed (`QR-2026-00012`, the below-cost one from the demo data).

**What to show:**

- Status **Validation Failed**, with the reason in plain language:
  *"WRN-0100: A discount of 15.00% prices the unit at 2040.00, below the cost
  price of 2100.00."*
- The **Success gate** panel: every condition unticked.
- The **workflow trace**: `VALIDATE_REQUEST` failed, and the remaining seven
  steps are recorded as **Skipped** — not omitted. Say: *we can tell the
  difference between "did not run" and "was never attempted".*
- The quantities and notes the customer submitted are still on the record.
- **No quotation exists.** There is nothing to download.

---

## Scenario 3 — A discount above policy goes to a manager

**Proves:** the discount rule engine, escalation, the approval interface.

1. As the **customer**, build a request for **Centrifugal Pump 1200 LPM**,
   quantity **8**, discount **12%**.
2. The right-hand panel turns amber: *This request will need manager approval —
   PMP-1200: 12.00% exceeds the 7.00% ceiling.* Explain the arithmetic: 8 units
   is the 6–20 band (5%), plus 2% for Gold = 7%.
3. **Submit.** Status becomes **Awaiting Approval**. Show that
   `GENERATE_DOCUMENT` is **Skipped** — nothing is issued before a decision.
4. Switch to the **manager** window. **Pending Approvals** → open the task.

**What to show on the decision screen:**

- The three figures side by side: **discount requested 12%**, **policy allows
  7%**, **final amount**.
- **Validation results** — the exception with its full context.
- The customer's **credit position**, so the manager sees exposure.
- Click **Approve**, tick *Apply a different discount instead*, enter **6%**.
  The dialog shows the repriced totals before you commit.
- Approve. The request goes to **Completed**, and the quotation shows
  *Manager approved* with the manager's name and a 6% line discount.

---

## Scenario 4 — A manager rejects a quotation

**Proves:** the rejection path, mandatory reasons, no document issued.

1. As the **manager**, open another pending approval.
2. Click **Reject** and try to confirm with the comment box empty — it is
   refused. The backend enforces this too, not just the form.
3. Enter *"Margin is too thin at this discount. Resubmit at 5% or less."* and
   reject.

**What to show:**

- Request status **Rejected**; `quotation_id` is null and no document exists.
- In the **customer** window, the notification bell carries the manager's exact
  words.
- **Audit Logs** (manager only) → filter by `Approval decided`. The entry names
  the actor, their role, their IP address, and the decision.
- Mention: *re-running the workflow on this request is now a no-op — it is
  settled, and the engine will not process it again.*

---

## Scenario 5 — A temporary failure is retried within its limits

**Proves:** retry classification, the maximum-iterations boundary, the budget.

This one is best shown from the **Company Settings** page plus a prepared
request, because injecting a real database fault live is awkward.

1. As the **manager**, open **Company Settings**. Scroll to the execution
   limits. Show that **max retries per step**, **max attempts per request**,
   **execution time** and the **resource ceilings** are all configuration, not
   code.
2. Explain the rule: **only transient failures are retried.** A dropped database
   connection is retried up to three times with exponential backoff. A
   validation verdict is never retried — retrying it would burn the budget to
   reach the same answer.
3. Open any completed request and show the **Execution budget** panel:
   attempts used against the ceiling, retries used, engine time against the
   limit.
4. Run the proof in a terminal — this is the honest version, since it injects
   the fault:

```bash
cd backend
python -m pytest tests/test_end_to_end_scenarios.py::TestScenario5TemporaryFailure -v
```

Four tests, all passing: a fault that clears after two retries completes; a
fault that never clears stops at exactly three retries and escalates; a PDF
failure withholds the document; a verification mismatch withholds it too.

---

## Scenario 6 — A sales employee cannot add a customer or product on their own

**What it shows:** the authorisation boundary around the data the rule engine
reads. Takes about ninety seconds.

### As the sales employee

1. Sign in as `sales1@quoteflow.example`.
2. Go to **Customers** and point at the amber notice above the table: *a sales
   manager approves new customers*.
3. Press **Add customer**. The dialog is titled **Request a new customer** and
   its button reads **Send for approval**. Fill it in — any company name, a
   contact, an email, a phone number — and add a line under *why this customer
   is needed*.
4. Send it. The toast gives you an `MDR-…` reference, not a `CUST-…` code:
   nothing has been created.
5. Open **My Add Requests**. The request is there, *Awaiting approval*, with the
   record exactly as you typed it.

> Worth saying out loud: the form is the same form a manager uses. The
> difference is where the payload goes.

### As the sales manager

6. Sign in as `manager@quoteflow.example`. **Add Requests** carries a badge.
7. Open it, press **Review**, and read the proposed record field by field,
   together with who asked and why.
8. Press **Refuse** without typing anything — it is refused, because an employee
   is owed a reason. Type one and refuse, or press **Approve and create**.
9. On approval the customer exists: the dialog's outcome column names the
   `CUST-…` code it produced. Go to **Customers** and find it.
10. Open **Audit Logs** and filter `entity_type` to `master_data_request`. Both
    events are there — `MASTER_DATA_REQUESTED` against the employee,
    `MASTER_DATA_APPROVED` against you — and the `CUSTOMER_CREATED` entry is
    recorded against you, because you authorised it.

**The point:** a product's price and a customer's credit limit are what the
discount rules are evaluated against. If the people who raise quotations could
also write those numbers, the policy would be advisory. The same control covers
products, with the same queue.

**What it does *not* cover:** editing an existing record. That stays with the
employee doing the work — say so rather than letting someone discover it.

---

## If someone asks: "how do you know it works?"

```bash
cd backend && python scripts/test_report.py --quiet
```

470 tests, grouped by area, with execution times. Point at these four rows:

| Area | Cases |
| --- | --- |
| Workflow boundaries (retries, gate, no-op, escalation, budget) | 47 |
| Failure handling and idempotency | 33 |
| Security (auth, RBAC, passwords, downloads, config) | 67 |
| Master-data authorisation (manager approval) | 48 |

Then:

```bash
# Every page, every role, rendered against the live backend
cd frontend && SMOKE_ORIGIN=http://localhost:5173 npm test

# The frontend's API contract against the running API
cd backend && python scripts/verify_integration.py --frontend http://localhost:5173
```

---

## Questions you should expect

**"Is there any AI in it?"**
No. The pricing is `Decimal` arithmetic, the discount decision is a table
lookup plus four comparisons, and the routing is a set of boolean rules read
from `company_settings`. Identical inputs always produce an identical execution
trace — the determinism test asserts exactly that.

**"What stops a customer approving their own discount?"**
Role-based authorisation on the endpoint, and a test named
`test_a_customer_cannot_approve_their_own_request` that asserts the attempt is
refused *and* that the request is left untouched.

**"What if someone edits the database directly?"**
Each quotation carries an HMAC-SHA256 digest over its financial content, keyed
with a deployment secret. Change a stored amount and verification fails —
demonstrate it live:

```bash
# in the mongo shell, drop a total to 1.00, then re-verify in the UI
```

The checker tool catches it too, and a document that fails verification is
escalated rather than delivered.

**"What happens if the PDF service dies mid-run?"**
The failure is classified transient, retried three times, and then the request
is **escalated** — not completed. The success gate's `document_generated`
condition stays false, so nothing claims to have been delivered.

**"Could a sales employee give themselves a better price by adding a product?"**
No. Adding a customer or a product is manager-only; an employee's add is
submitted to the manager's master-data queue and nothing is written until it is
approved. 48 tests cover the boundary, including that an employee cannot decide
their own request and that a refused proposal creates nothing. Changing an
*existing* record is not gated — that is stated as a known limitation rather
than claimed as covered.

**"Can the same request produce two quotations?"**
No. A unique index on `quotations.request_id` makes it impossible at the
database level, and the action tool returns the existing quotation if one is
already there. Two tests cover it, including the concurrent case.
