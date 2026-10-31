# QuoteFlow — Backend

Automated Quotation Request and Approval Management System.

A customer submits a quotation request; the backend validates it, verifies stock,
calculates prices with `Decimal` arithmetic, applies the configured discount
policy, routes anything outside policy to a sales manager, and issues a verified
PDF quotation.

Every decision is made by **explicit business rules** held in the
`company_settings` collection and recorded **step by step** in
`workflow_executions`. There is no LLM, no generative model and no inference
anywhere in the codebase: identical inputs always produce an identical execution
trace.

---

## 1. Quick start

**Prerequisites:** Python 3.12+, MongoDB 6+ running locally.

```bash
cd backend

# 1. Virtual environment
py -3.12 -m venv .venv
.venv\Scripts\activate            # Windows
# source .venv/bin/activate       # macOS / Linux

# 2. Dependencies
pip install -r requirements.txt   # or requirements-dev.txt for ruff + pypdf

# 3. Configuration
copy .env.example .env            # cp on macOS / Linux, then edit the secrets

# 4. Seed the demo dataset (19 products, 5 customers, 7 logins)
python -m app.db.seed --reset

# 5. Run
uvicorn app.main:app --reload --port 8000
```

Then open **<http://127.0.0.1:8000/docs>** for interactive API documentation.

### Seeded logins

Every seeded account uses the password `QuoteFlow@2026`.

| Role | Email | Notes |
| --- | --- | --- |
| `SALES_MANAGER` | `manager@quoteflow.example` | Approvals, analytics, settings |
| `SALES_EMPLOYEE` | `sales1@quoteflow.example` | Customers, products, queue |
| `SALES_EMPLOYEE` | `sales2@quoteflow.example` | |
| `CUSTOMER` | `rohit.desai@acme-process.example` | GOLD tier (+2% discount bonus) |
| `CUSTOMER` | `priya.nair@deccan-water.example` | PLATINUM tier, high credit limit |
| `CUSTOMER` | `imran@sunrise-fab.example` | Low credit limit — triggers the credit rule |
| `CUSTOMER` | `anita.rane@konkan-marine.example` | SILVER tier |

The seed data is deliberately shaped so every branch of the workflow can be
demonstrated straight away:

- `PRX-5500` holds only 6 sellable units → **stock shortfall** path.
- `WRN-0100` has a thin margin (₹2400 list / ₹2100 cost) → **cost-floor refusal**.
- `FLW-ELC-80` caps discount at 6% regardless of quantity → **per-product cap**.
- `PMP-LEG-900` is discontinued → **validation failure**.
- `CUST-0005` (Halted Industries) is `ON_HOLD` → **customer status refusal**.

### Tests

```bash
pytest                      # 470 tests
pytest -m engine            # pure rule-engine tests, no database needed
pytest -m workflow          # end-to-end workflow tests
ruff check app/ tests/      # lint
```

Tests run against a separate `quoteflow_test` database, which is created and
dropped automatically. `tests/conftest.py` refuses to run if the configured
database name does not contain `test`.

---

## 2. Architecture

The backend is a four-layer application. Dependencies point in one direction
only — a layer never imports from the layer above it.

```
      HTTP
        │
┌───────▼─────────────────────────────────────────────────────┐
│ app/api/v1/        Routers: HTTP concerns only.             │
│                    Validate input, call a service, shape    │
│                    the response. No business logic.         │
├─────────────────────────────────────────────────────────────┤
│ app/services/      Business logic.                          │
│                                                             │
│   Pure engines (no I/O, directly unit-testable):            │
│     pricing_engine     — the arithmetic                     │
│     discount_engine    — the policy verdicts                │
│     verification_service — integrity hashing                │
│                                                             │
│   Orchestration:                                            │
│     workflow_engine    — the 6-step pipeline                │
│     approval_service, request_service, quotation_service,   │
│     customer_service, product_service, availability_service │
│                                                             │
│   Cross-cutting:                                            │
│     audit_service, notification_service, analytics_service, │
│     settings_service, numbering, pdf_service                │
├─────────────────────────────────────────────────────────────┤
│ app/models/        Pydantic documents + enums + the state   │
│ app/schemas/       machine. Request/response contracts.     │
├─────────────────────────────────────────────────────────────┤
│ app/db/            MongoDB connection, index plan, seed     │
└─────────────────────────────────────────────────────────────┘
                              │
                          MongoDB
```

### Design decisions worth knowing

**Money is `Decimal`, end to end.** Floats are never used for arithmetic.
Amounts are quantised to 2dp with `ROUND_HALF_UP` and persisted as BSON
`Decimal128`, which is lossless. `app/utils/money.py` holds the helpers;
`encode_decimals` / `decode_decimals` convert at the persistence boundary so
service code works with plain `Decimal` throughout. At the HTTP boundary
amounts are serialised as JSON **numbers** (2dp values are exact in float), so
the frontend's charting library receives numbers rather than strings.

**The rule book is data, not code.** No engine hard-codes a threshold. Discount
tiers, the tier bonus table, tax rate, approval thresholds, SLA hours, validity
period and the cost-floor switch all live in the single `company_settings`
document and are editable by a sales manager through `PATCH /api/v1/settings`.
A test asserts that the *same* request is auto-approved or escalated purely by
reconfiguring the tier table.

**Illegal states are unreachable.** `REQUEST_TRANSITIONS` in
`app/models/enums.py` is the authoritative state machine; every transition goes
through `assert_transition`, which raises `409` on anything not in the table.
Tests verify that every status has a rule, that terminal statuses allow nothing
further, and that no status can trap a request forever.

**One pricing path.** When a manager approves a request, the approval service
does not build the quotation itself — it re-runs the workflow pipeline with
`auto_approve=True` and the override discount. A manager-approved quotation is
therefore priced by exactly the same code as an auto-approved one, and the
decision leaves its own execution trace.

**Audit is append-only.** `audit_logs` has no update or delete path anywhere in
the API; a test asserts that every audit route exposes `GET` only. Audit and
notification writes are best-effort: a logging failure is reported to the
application log and never fails the business operation that triggered it.

**Products are soft-deleted.** `DELETE /products/{id}` marks a product
`DISCONTINUED`. Historical quotations reference it, and an audit trail that
points at a missing document is not an audit trail.

**Quotations are immutable snapshots.** A quotation copies the company and
customer blocks as they were at issue time, so reprinting the PDF years later
reproduces the original document even if the customer has since been renamed.

---

## 3. The workflow pipeline

Every submitted request runs through the same eight steps, in the same order.
Each step's inputs, decision, duration and any errors are persisted as one
`workflow_executions` document.

| # | Step | What it decides |
| --- | --- | --- |
| 1 | `VALIDATE_REQUEST` | Customer exists and is not blocked/on hold; at least one line; no duplicate products; quantities ≥ 1; every product exists and is active |
| 2 | `CHECK_AVAILABILITY` | Sellable stock per line (`stock − reserved`); classifies `IN_STOCK` / `PARTIAL` / `OUT_OF_STOCK`; fails the request if backorders are disabled by policy |
| 3 | `CALCULATE_PRICING` | Resolves each line's discount ceiling, then computes the six line amounts and the document totals — arithmetic only |
| 4 | `EVALUATE_DISCOUNT_RULES` | Applies policy to those numbers: allowed / needs approval / refused |
| 5 | `DETERMINE_APPROVAL_ROUTE` | Combines discount exceptions with order value, credit exposure and stock shortfall to decide auto-approve vs. manager review |
| 6 | `GENERATE_DOCUMENT` | The **action tool**: issues the quotation and renders its PDF. Skipped when the request is queued for a manager |
| 7 | `VERIFY_DOCUMENT` | The **checker tool**: independently recalculates every amount and verifies the document |
| 8 | `FINALISE` | Evaluates the success gate, writes the outcome, notifies the right people |

Steps 3 and 4 are deliberately separate: step 3 only computes numbers, step 4
only applies policy to them. That split keeps the arithmetic testable without a
rule book, and the rules testable without re-deriving totals.

If a step fails, the remaining steps are recorded as `SKIPPED` rather than
omitted, so the trace always shows the full pipeline.

### Request lifecycle

```
                                            ┌─> VALIDATION_FAILED ─┐
DRAFT ─> SUBMITTED ─> UNDER_VALIDATION ─────┤                      │
  ▲                                         └─> PRICED ─┬─> APPROVED ─> COMPLETED
  │                                                     │                (terminal)
  │                                                     └─> PENDING_APPROVAL
  │                                                              │
  │                                        ┌─────────────────────┼──────────┐
  │                                        ▼                     ▼          ▼
  └────────────────── MODIFICATION_REQUESTED               APPROVED     REJECTED
                              (resubmit, revision + 1)                  (terminal)

  CANCELLED   reachable from any open state                         (terminal)
  ESCALATED   reachable from every live state; resubmittable
```

Three statuses are terminal: **COMPLETED**, **REJECTED** and **CANCELLED**.

`APPROVED` is *not* terminal — it means "authorised, document not yet verified".
The request only becomes `COMPLETED` once the action tool has issued the document
and the checker tool has verified it, which is what the success gate enforces.

`VALIDATION_FAILED`, `MODIFICATION_REQUESTED` and `ESCALATED` are all editable
and resubmittable; resubmitting increments `revision`.

`ESCALATED` means the workflow parked the request for a human rather than
guessing. It is reachable from every live state, because an escalation condition
can be hit at any point — including before validation, when a budget is already
spent.

---

## 4. Workflow boundaries

Five controls bound what the engine may do. Every limit is a value in
`company_settings.execution_policy`, so a deployment can re-tune them and a test
can shrink one to prove the limit is real.

| Control | Default | Enforced by |
| --- | --- | --- |
| Retries per step | 3 | `ExecutionBudget.run_step` — transient failures only |
| Attempts per request | 10 | Checked before any work; the counter is committed first, so it survives a crash |
| Execution time, one run | 30 s | Checked before each step |
| Execution time, whole request | 180 s | Accumulated across attempts on the request |
| Lines per request | 50 | Validation step |
| Quantity per line | 1,000,000 | Validation step |

### A. Maximum iterations

A failure is either **transient** or **permanent**, and only a transient one is
retried:

- **Transient** — `ConnectionFailure`, `ServerSelectionTimeoutError`,
  `NetworkTimeout`, `OSError` (a PDF that could not be written), `TimeoutError`.
  Retried up to the configured maximum with exponential backoff
  (50 ms, 100 ms, 200 ms by default).
- **Permanent** — `ValidationError`, `BusinessRuleError`, `WorkflowError`,
  `NotFoundError`, `PermissionDeniedError`. Not retried at all: these are
  verdicts, and retrying one would burn the budget to reach the same answer.

An unclassified exception is treated as **permanent**. Retrying an unknown fault
risks repeating a side effect, and failing fast surfaces the gap instead of
hiding it behind three silent retries.

Retries are counted on the step, on the execution's `budget.retries` log, and on
the request's `retry_count`. When the allowance is spent the request is
**escalated** with `REPEATED_PROCESSING_FAILURE` — it is never left to surface
as an unhandled error to the submitter.

### B. Success gate

A request reaches `COMPLETED` only when all six conditions hold:

```
input_validation_passed
product_verification_passed
pricing_validation_passed
approval_recorded
document_generated
independent_verification_passed
```

The gate is **allow-on-proof**: a condition that was never evaluated counts as
unmet, so the default is refusal rather than acceptance. The state of all six is
recorded on every execution, including the runs that failed, and the UI shows
which one is outstanding. If the gate is not satisfied the request escalates
instead of completing.

### C. No-op condition

A request in a settled status (`COMPLETED`, `REJECTED`, `CANCELLED`, `ESCALATED`)
has nothing left for the engine to do. Running the pipeline again would burn
budget and could issue a second document, so the run stops immediately, records
a `NO_OP` outcome with all eight steps marked skipped, increments the request's
`no_op_count`, and writes an audit entry. Repeated pointless triggers are
therefore visible rather than silent.

### D. Escalation condition

Seven reasons park a request for a human, each recorded as an
`EscalationReason` on the request and the execution:

| Reason | Raised when |
| --- | --- |
| `MISSING_CUSTOMER_INFORMATION` | The customer record lacks a name, contact, email or telephone number |
| `PRODUCT_UNAVAILABLE` | A line cannot be met from stock and backorders are disabled |
| `DISCOUNT_EXCEPTION` | A discount is above its ceiling — the approval task *is* the escalation |
| `MANAGER_REJECTION` | A manager rejected the request |
| `REPEATED_PROCESSING_FAILURE` | A step exhausted its retries, or the gate could not be satisfied |
| `VERIFICATION_MISMATCH` | The checker tool rejected the issued document |
| `BUDGET_EXCEEDED` | An attempt, duration or resource limit was reached |

Escalation is reachable from **every live status**. An earlier version allowed it
only from a hand-picked few, and a request whose budget was spent before
validation was left stranded with a reason recorded but its status unchanged —
the transition table now derives the escalation edges rather than listing them.

Escalating notifies every active sales manager and writes an audit entry
carrying the reason, the attempt number and the retry count.

### E. Budget limit

Three things make infinite execution impossible:

1. **Attempts are counted and committed before work starts**, so a crash mid-run
   still consumes the attempt.
2. **Time is checked before every step**, against both a per-run and a
   whole-request ceiling.
3. **Resource ceilings** bound how much work one request can ask for, checked
   during validation.

Exceeding any of them escalates with `BUDGET_EXCEEDED`. The engine never loops.

---

## 5. The action tool and the checker tool

The two are deliberately separate modules, and the checker does not trust the
action tool's output.

### Action tool — `app/services/action_tool.py`

Does the work: allocates the quotation number, stores the quotation, renders the
PDF, records the path. It reports what it did and makes no claim that the result
is correct.

It is also where **idempotency** lives. A request may only ever hold one
quotation:

- The tool looks for an existing quotation before issuing, and returns it
  unchanged if found (`reused_existing: true`).
- A **unique index on `quotations.request_id`** is the actual guarantee. Two
  concurrent runs cannot both insert; the loser catches the duplicate-key error
  and adopts the winner's document.
- `assert_single_quotation` is a final check that a request never ended up with
  more than one.

### Checker tool — `app/services/checker_tool.py`

Decides whether to believe the action tool. Two things make the check
independent rather than ceremonial:

1. **The data is re-fetched from source.** Products, the customer and the rule
   book are read again from their own collections. Nothing is taken from the
   action tool's return value or from the request's priced lines.

2. **The money is recomputed in longhand.** The arithmetic is written out with
   `Decimal` in the checker rather than calling `pricing_engine.price_line`.
   That is the point: sharing the pricing function would mean a bug in it
   produced the same wrong answer twice and the check would pass. Writing the
   sums out separately means the checker disagrees with the engine whenever one
   of them is wrong.

It runs eight checks and reports findings rather than raising:

| Check | What it compares |
| --- | --- |
| `product_information` | Each line's product still exists, is active, and its SKU matches |
| `quantities` | Every quantity is positive; the document's line count and total quantity match its lines |
| `unit_prices` | Each quoted unit price against the live catalogue |
| `discount_calculations` | Line subtotal, discount and taxable amount, recomputed |
| `tax_calculations` | The tax rate applied and the tax amount, recomputed |
| `final_amount` | Each line total; the document totals against the sum of lines; and the totals' internal consistency (`subtotal − discount = taxable`, `taxable + tax = final`) |
| `approval_status` | Either auto-approved within policy, or a named approval task that is genuinely `APPROVED` |
| `document_consistency` | The HMAC integrity digest against the stored amounts, plus the PDF exists, is non-empty and begins `%PDF-` |

A rejection escalates the request with `VERIFICATION_MISMATCH` and writes a
`QUOTATION_VERIFICATION_FAILED` audit entry. **A document that fails independent
recalculation is never delivered as though it were sound.**


---

## 6. Master-data authorisation

A sales employee cannot add a customer or a product. They propose the record and
a sales manager authorises it; only then does the customer or product exist.

The reason is that both collections feed the rule engine. A product's
`unit_price` and `cost_price` become the price a customer is quoted and the
floor no discount may breach; a customer's `tier` and `credit_limit` decide what
discount they may ask for and how much exposure is allowed. Letting anyone who
can raise a quotation also write those numbers would make the discount policy
advisory rather than binding.

### How it works

```
employee fills the same form
          │
          ▼
POST /master-data-requests/customers      ─> master_data_requests (PENDING)
POST /master-data-requests/products            nothing else is written
          │
          ▼
manager's queue ──> approve ──> customer_service.create_customer(actor=manager)
                 │              product_service.create_product(actor=manager)
                 │                        │
                 │                        ▼
                 │              the record exists; the proposal is marked
                 │              APPROVED and links to what it created
                 │
                 └─> refuse ──> REJECTED, with a reason, and nothing created
```

The approved record is created by **the same service functions** the direct
route calls, with the manager as the actor. There is no second write path: an
authorised addition is indistinguishable in the data from one a manager typed in
themselves, and the audit trail names both people — `MASTER_DATA_REQUESTED` by
the employee, `MASTER_DATA_APPROVED` by the manager, and the usual
`CUSTOMER_CREATED` / `PRODUCT_CREATED` entry against the manager.

### What is enforced

| Rule | How |
| --- | --- |
| An employee cannot create master data | `POST /customers` and `POST /products` require a manager; the 403 names the route to submit to instead |
| Nothing exists before approval | The proposal holds the payload; neither collection is touched until a manager approves |
| An employee cannot approve their own request | `POST /{id}/decision` is manager-only |
| The same record cannot be queued twice | Partial unique index on `(entity_type, dedupe_key)` over `PENDING` rows |
| A decision cannot be taken twice | The status is part of the update filter, so a second decision matches nothing |
| A refusal must say why | A blank comment is refused with 409 |
| A refused record is not blacklisted | The uniqueness constraint only covers open proposals, so a corrected version can be resubmitted |
| The payload is still valid at approval | It is re-validated against the current create schema before anything is written |

### What is deliberately *not* gated

**Editing** an existing customer or product. The control exists so new records
enter the catalogue deliberately; day-to-day upkeep — a corrected phone number,
a stock movement, a price change — stays with the employee doing the work. If a
deployment wants price changes gated too, the same queue would carry an `UPDATE`
action; the model has room for it.

A manager still has the direct route. The queue is a route for employees, not a
ceremony imposed on everyone.

---

## 7. Business rules

### Discount ceilings

The default policy is the one from the brief, configurable per deployment:

| Quantity | Max discount |
| --- | --- |
| 1 – 5 | 2% |
| 6 – 20 | 5% |
| 21 – 50 | 10% |
| 51+ | 15% |

The ceiling for a line is:

```
ceiling = quantity-band maximum
        + customer-tier bonus          (STANDARD 0, SILVER 1, GOLD 2, PLATINUM 3)
then clamped by the product's own max_discount_percent, if set
then clamped by absolute_max_discount_percent  (default 40%)
```

The engine then returns one of four verdicts, in precedence order:

1. **Refused** — the requested discount exceeds `absolute_max_discount_percent`.
   No approval can grant it, so the request fails validation outright.
2. **Refused** — the discount would price the unit below its `cost_price`
   (when `enforce_cost_floor` is on).
3. **Needs approval** — above the ceiling but within the absolute maximum.
4. **Allowed** — at or below the ceiling.

A line that needs approval is still **priced at the discount the customer asked
for**, so the manager sees the actual ask rather than a clamped figure.

### Other escalation triggers

| Exception | Raised when |
| --- | --- |
| `DISCOUNT_LIMIT_EXCEEDED` | A line is above its ceiling |
| `ORDER_VALUE_THRESHOLD` | Final amount ≥ `order_value_threshold` (default ₹500,000; set to 0 to disable) |
| `CREDIT_LIMIT_EXCEEDED` | `outstanding_amount + this quotation > credit_limit` (skipped when the limit is 0) |
| `STOCK_SHORTFALL` | Any line cannot be met from sellable stock |

### Calculation order

Per line:

```
line_subtotal        = unit_price × quantity
line_discount_amount = line_subtotal × discount_percent / 100
line_taxable_amount  = line_subtotal − line_discount_amount
line_tax_amount      = line_taxable_amount × tax_rate / 100
line_total           = line_taxable_amount + line_tax_amount
```

Tax is charged on the **discounted** amount, not the gross. The tax rate is the
product's own `tax_rate` when set, otherwise the company default (18%).

Document totals are the sum of the already-rounded line amounts, so the printed
lines always add up to the printed total. Summing first and rounding last would
let the two disagree by a cent.

---

## 8. Folder structure

```
backend/
├── app/
│   ├── main.py                     FastAPI app, lifespan, CORS, /health
│   ├── api/v1/
│   │   ├── router.py               Aggregates every router
│   │   ├── auth.py                 Register, login, refresh, staff accounts
│   │   ├── customers.py            Customer CRUD, status, activity summary
│   │   ├── products.py             Catalogue, internal CRUD, stock, availability
│   │   ├── requests.py             Quotation requests + workflow execution
│   │   ├── approvals.py            Manager queue and decisions
│   │   ├── quotations.py           Quotations, PDF, public verification
│   │   ├── audit.py                Read-only audit trail
│   │   ├── notifications.py        In-app inbox
│   │   ├── analytics.py            Dashboard aggregations
│   │   └── settings.py             The editable rule book
│   ├── core/
│   │   ├── config.py               Settings from .env (cached singleton)
│   │   ├── security.py             bcrypt hashing, JWT issue/decode
│   │   ├── deps.py                 Principal + RBAC guards
│   │   └── exceptions.py           Domain errors → HTTP responses
│   ├── db/
│   │   ├── mongo.py                AsyncMongoClient lifecycle, collection names
│   │   ├── indexes.py              Index plan, applied on startup
│   │   └── seed.py                 Demo dataset (`python -m app.db.seed`)
│   ├── models/
│   │   ├── common.py               PyObjectId, Money/Rate, Page[T], base models
│   │   ├── enums.py                Enums + the request state machine
│   │   ├── user.py  customer.py  product.py
│   │   ├── quotation_request.py  quotation.py  approval.py
│   │   ├── workflow.py  audit.py  notification.py
│   │   └── company_settings.py     The rule book schema
│   ├── schemas/                    Request/response contracts
│   │   ├── auth.py  customer.py  product.py  quotation.py
│   ├── services/
│   │   ├── pricing_engine.py       Pure: the arithmetic
│   │   ├── discount_engine.py      Pure: the policy verdicts
│   │   ├── verification_service.py Pure: HMAC integrity hashing
│   │   ├── execution_budget.py     Pure: retry classification + budgets
│   │   ├── action_tool.py          Issues the quotation; idempotent
│   │   ├── checker_tool.py         Independently recalculates and verifies
│   │   ├── workflow_engine.py      The 8-step pipeline + the 5 boundaries
│   │   ├── master_data_service.py  Employee proposes, manager authorises
│   │   ├── request_service.py      Create, edit, submit, cancel
│   │   ├── approval_service.py     Manager decisions
│   │   ├── quotation_service.py    Issue, read, verify, expire
│   │   ├── availability_service.py Stock verification
│   │   ├── customer_service.py  product_service.py
│   │   ├── analytics_service.py  audit_service.py
│   │   ├── notification_service.py settings_service.py
│   │   ├── pdf_service.py          ReportLab rendering
│   │   └── numbering.py            Gap-free document numbers
│   └── utils/money.py              Decimal helpers
├── Dockerfile                      Production image (non-root, 2 workers)
├── scripts/
│   ├── demo_activity.py            Generates demo requests and decisions
│   ├── verify_integration.py       Drives the API as the frontend does
│   └── test_report.py              Runs pytest and renders TEST_REPORT.md
├── tests/
│   ├── conftest.py                 Test DB, fixtures, actor builders
│   ├── test_pricing_engine.py      16  pure arithmetic
│   ├── test_discount_engine.py     35  tier boundaries, caps, overrides
│   ├── test_state_machine.py       39  transitions, ids, money helpers
│   ├── test_auth.py                25  auth + RBAC
│   ├── test_catalogue.py           32  catalogue, products, customers
│   ├── test_workflow.py            46  every pipeline branch, end to end
│   ├── test_approvals.py           23  decisions, overrides, concurrency
│   ├── test_quotations.py          19  documents, PDF, verification
│   ├── test_analytics_and_audit.py 27  aggregations, audit, configurability
│   ├── test_workflow_boundaries.py 47  retries, gate, no-op, escalation, budget
│   ├── test_failure_handling.py    33  the 12 failure scenarios + idempotency
│   ├── test_end_to_end_scenarios.py 13 the 5 demonstration scenarios
│   ├── test_security.py            67  auth, RBAC, passwords, downloads, config
│   └── test_master_data_requests.py 48 the manager-approval boundary
├── storage/quotations/             Generated PDFs (git-ignored)
├── requirements.txt
├── requirements-dev.txt
├── ruff.toml
├── pytest.ini
└── .env.example
```

---

## 9. Database schemas

Twelve collections. `counters` supports `numbering.py`; the other eleven are the
domain.

### `users`

| Field | Type | Notes |
| --- | --- | --- |
| `email` | string | **unique** |
| `password_hash` | string | bcrypt |
| `full_name` | string | |
| `role` | enum | `CUSTOMER` / `SALES_EMPLOYEE` / `SALES_MANAGER` |
| `status` | enum | `ACTIVE` / `SUSPENDED` — re-checked on every request |
| `customer_id` | ObjectId? | Set only for `CUSTOMER` accounts |
| `last_login_at` | datetime? | |

Indexes: `email` (unique), `(role, status)`, `customer_id` (sparse).

### `customers`

| Field | Type | Notes |
| --- | --- | --- |
| `code` | string | **unique**, e.g. `CUST-0007` |
| `company_name`, `contact_name`, `email`, `phone` | string | `email` unique |
| `tier` | enum | `STANDARD` / `SILVER` / `GOLD` / `PLATINUM` — drives the discount bonus |
| `status` | enum | `ACTIVE` / `ON_HOLD` / `BLOCKED` |
| `billing_address` | subdocument | Printed on the quotation |
| `credit_limit` | Decimal128 | 0 disables the credit check |
| `outstanding_amount` | Decimal128 | Derived from live quotations, never incremented |
| `tax_id`, `notes` | string? | |

Indexes: `code` (unique), `email` (unique), `(status, tier)`, text index on
`company_name`/`contact_name`/`code`.

### `products`

| Field | Type | Notes |
| --- | --- | --- |
| `sku` | string | **unique**, upper-cased on write |
| `name`, `description`, `category`, `unit` | string | |
| `unit_price` | Decimal128 | Re-read at pricing time, not copied from the draft |
| `cost_price` | Decimal128 | The discount floor |
| `tax_rate` | Decimal128? | Overrides the company default when set |
| `stock_quantity`, `reserved_quantity` | int | Sellable = stock − reserved |
| `reorder_level`, `lead_time_days` | int | Low-stock flag, backorder lead time |
| `max_discount_percent` | Decimal128? | Per-product discount cap |
| `status` | enum | `ACTIVE` / `DISCONTINUED` (soft delete) |

Indexes: `sku` (unique), `(status, category)`, text index on
`name`/`description`/`sku`.

### `quotation_requests`

The working document of the workflow. Carries its own priced lines, the
exceptions the rule engine raised and the status it reached, so one read fills
the whole detail screen.

| Field | Type | Notes |
| --- | --- | --- |
| `request_number` | string | **unique**, `QR-2026-00001` |
| `customer_id`, `customer_code`, `customer_name` | | Denormalised for list views |
| `created_by`, `created_by_role` | | Customer or the staff member acting for them |
| `status` | enum | See the lifecycle diagram |
| `items[]` | subdocuments | Fully priced lines (see below) |
| `pricing` | subdocument? | `null` until the workflow prices it |
| `validation_errors[]` | string[] | Why it failed, in plain language |
| `exceptions[]` | subdocuments | `{type, message, context}` |
| `requires_approval` | bool | |
| `last_execution_id`, `approval_id`, `quotation_id` | ObjectId? | Cross-references |
| `revision` | int | Incremented on resubmission |
| `status_history[]` | subdocuments | `{from_status, to_status, actor, note, at}` |
| `attempt_count` | int | Pipeline runs consumed, against `max_attempts_per_request` |
| `retry_count` | int | Transient-failure retries across every attempt |
| `total_execution_ms` | int | Cumulative engine time, against `max_total_execution_ms` |
| `no_op_count` | int | Times the engine ran with nothing to do |
| `escalation_reason` | enum? | Why the request was parked; see the escalation table |
| `escalation_detail` | string? | The reason in words |
| `escalated_at` | datetime? | |
| `completed_at` | datetime? | Set only once the success gate passed |
| `customer_notes`, `internal_notes` | string? | Internal notes are staff-only |

Each `items[]` entry: `product_id`, `sku`, `name`, `unit`, `quantity`,
`unit_price`, `requested_discount_percent`, `max_allowed_discount_percent`,
`applied_discount_percent`, `discount_exception`, `line_subtotal`,
`line_discount_amount`, `line_taxable_amount`, `tax_rate`, `line_tax_amount`,
`line_total`, `availability{status, available_quantity, shortfall,
lead_time_days, backorder_allowed}`.

`pricing`: `subtotal`, `total_discount`, `taxable_amount`, `total_tax`,
`final_amount`, `effective_discount_percent`, `currency`, `tax_label`,
`total_quantity`, `line_count`.

Indexes: `request_number` (unique), `(customer_id, created_at desc)`,
`(status, created_at desc)`, `submitted_at desc`.

### `quotations`

The immutable issued document.

| Field | Type | Notes |
| --- | --- | --- |
| `quotation_number` | string | **unique**, `QT-2026-00001` |
| `request_id`, `request_number`, `customer_id` | | |
| `seller`, `buyer` | subdocuments | Frozen party snapshots |
| `items[]`, `pricing` | | Copied from the request at issue time |
| `terms[]` | string[] | Printed on the PDF |
| `status` | enum | `ISSUED` / `EXPIRED` / `ACCEPTED` / `WITHDRAWN` |
| `verification_code` | string | **unique**, `A3KP-7WQX-R9MT` |
| `integrity_hash` | string | HMAC-SHA256 over the financial payload |
| `approval_id`, `approved_by`, `approved_by_name`, `auto_approved` | | |
| `issued_at`, `valid_until` | datetime | |
| `pdf_path`, `pdf_generated_at`, `download_count` | | PDF is rendered on first request |

Indexes: `quotation_number` (unique), `verification_code` (unique),
**`request_id` (unique)**, `(customer_id, issued_at desc)`,
`(status, valid_until)`.

The unique index on `request_id` is the idempotency guarantee: a request can
never hold two quotations, however many times the pipeline runs.

### `approvals`

One task per request needing a manager decision.

| Field | Type | Notes |
| --- | --- | --- |
| `request_id`, `request_number`, `customer_id`, `customer_name` | | |
| `status` | enum | `PENDING` / `APPROVED` / `REJECTED` / `MODIFICATION_REQUESTED` |
| `exceptions[]`, `pricing_snapshot` | | Frozen at creation, so the task stays meaningful |
| `requested_amount`, `requested_discount_percent` | Decimal128 | |
| `decision`, `decided_by`, `decided_by_name`, `decided_at`, `comments` | | |
| `override_discount_percent` | Decimal128? | Manager-imposed discount |
| `sla_due_at` | datetime | From `approval_sla_hours`; drives the SLA metric |

Indexes: `(status, created_at desc)`, `request_id`, `decided_by` (sparse).

### `master_data_requests`

A sales employee's proposal to add a customer or a product. See section 6.

| Field | Type | Notes |
| --- | --- | --- |
| `reference` | string | `MDR-2026-00001`, from the `counters` collection |
| `entity_type` | enum | `CUSTOMER` / `PRODUCT` |
| `status` | enum | `PENDING` / `APPROVED` / `REJECTED` / `WITHDRAWN` |
| `payload` | document | The create payload as submitted, re-validated at approval |
| `label` | string | Human identity of the record: a company name, or SKU — name |
| `dedupe_key` | string | Normalised email or SKU; backs the pending-uniqueness index |
| `reason` | string? | Why the employee needs it |
| `requested_by`, `requested_by_name`, `requested_by_email` | | Who proposed it |
| `decided_by`, `decided_by_name`, `decided_at`, `decision_comments` | | Who decided, and why |
| `created_entity_id`, `created_entity_label` | | Set on approval: what it produced |

Indexes: `(status, created_at desc)`, `(requested_by, created_at desc)`,
`reference` (unique), and **`(entity_type, dedupe_key)` unique over `PENDING`
rows only** — so the same record cannot sit in the queue twice while a refused
proposal can still be corrected and resubmitted.

### `workflow_executions`

The audit trail of the rule engine — what makes the automation explainable.

| Field | Type | Notes |
| --- | --- | --- |
| `request_id`, `request_number` | | |
| `triggered_by`, `trigger` | | `SUBMISSION` / `APPROVAL` / `REPROCESS` |
| `engine_version` | string | Bumped when step semantics change |
| `outcome` | enum | `AUTO_APPROVED` / `PENDING_APPROVAL` / `VALIDATION_FAILED` |
| `steps[]` | subdocuments | `{step, status, message, retries, output, errors, started_at, completed_at, duration_ms}` |
| `resulting_status` | string | What was written onto the request |
| `attempt_number` | int | This request's lifetime attempt number |
| `retries_used` | int | Retries across every step of this run |
| `budget` | subdocument | The limits in force, consumption, and the retry log |
| `gate` | subdocument | The state of all six success-gate conditions |
| `escalation_reason` | enum? | Set when the run parked the request |
| `started_at`, `completed_at`, `duration_ms` | | |

Indexes: `(request_id, started_at desc)`, `outcome`.

### `audit_logs`

Append-only. `{action, entity_type, entity_id, summary, actor_id, actor_email,
actor_role, changes, metadata, ip_address, user_agent, created_at}`. `changes`
holds a field-level `{field: {before, after}}` diff.

Indexes: `created_at desc`, `(entity_type, entity_id)`, `actor_id` (sparse),
`action`.

### `notifications`

`{user_id, type, title, message, channel, entity_type, entity_id, read,
read_at, created_at}`. Index: `(user_id, read, created_at desc)`.

### `company_settings`

A single document, `key: "default"`, holding `profile`, `discount_policy`,
`tax_policy`, `approval_policy`, `quotation_policy` and `execution_policy`.
Index: `key` (unique).

`execution_policy` is what makes the workflow boundaries configurable:
`max_retries_per_step`, `max_attempts_per_request`, `max_execution_ms`,
`max_total_execution_ms`, `max_lines_per_request`, `max_quantity_per_line` and
`retry_backoff_ms`.

---

## 10. API reference

65 operations under `/api/v1`, plus `/` and `/health`. Full interactive
documentation at `/docs`.

Authenticate with `POST /api/v1/auth/login`, then send
`Authorization: Bearer <access_token>`.

Role key: **C** = customer, **E** = sales employee, **M** = sales manager,
**—** = no authentication required.

### Authentication

| Method | Path | Roles | Summary |
| --- | --- | --- | --- |
| `POST` | `/auth/register` | — | Create a customer login *and* its customer record |
| `POST` | `/auth/login` | — | Sign in |
| `POST` | `/auth/refresh` | — | Exchange a refresh token |
| `GET` | `/auth/me` | C E M | Current user and linked customer record |
| `POST` | `/auth/change-password` | C E M | Change your own password |
| `POST` | `/auth/staff` | M | Create a sales employee or manager account |

### Products

| Method | Path | Roles | Summary |
| --- | --- | --- | --- |
| `GET` | `/products/catalogue` | C E M | Active products + the discount the caller may request |
| `GET` | `/products/categories` | C E M | Category facets with counts |
| `POST` | `/products/check-availability` | C E M | Pre-flight stock check for a set of lines |
| `GET` | `/products` | E M | Full records including cost price |
| `POST` | `/products` | M | Add a product — an employee submits for approval instead |
| `GET` | `/products/{id}` | E M | Get a product |
| `PATCH` | `/products/{id}` | E M | Update a product |
| `POST` | `/products/{id}/stock` | E M | Apply a relative stock movement |
| `DELETE` | `/products/{id}` | M | Discontinue (soft delete) |

### Customers

| Method | Path | Roles | Summary |
| --- | --- | --- | --- |
| `GET` | `/customers` | E M | List, with search / status / tier filters |
| `POST` | `/customers` | M | Create a customer — an employee submits for approval instead |
| `GET` | `/customers/{id}` | E M | Get a customer |
| `PATCH` | `/customers/{id}` | E M | Update a customer |
| `GET` | `/customers/{id}/summary` | E M | Request and quotation activity |
| `POST` | `/customers/{id}/status` | M | Activate, hold or block |

### Quotation requests and workflow

| Method | Path | Roles | Summary |
| --- | --- | --- | --- |
| `GET` | `/quotation-requests` | C E M | List — customers see only their own |
| `POST` | `/quotation-requests` | C E M | Create, and run the workflow unless `submit: false` |
| `GET` | `/quotation-requests/{id}` | C E M | Get a request |
| `PATCH` | `/quotation-requests/{id}` | C E M | Edit a draft or returned request |
| `POST` | `/quotation-requests/{id}/submit` | C E M | Submit and run the pipeline |
| `POST` | `/quotation-requests/{id}/cancel` | C E M | Cancel |
| `POST` | `/quotation-requests/{id}/reprocess` | E M | Re-run after a stock/catalogue correction |
| `PUT` | `/quotation-requests/{id}/internal-notes` | E M | Staff-only annotation |
| `GET` | `/quotation-requests/{id}/executions` | C E M | Step-by-step workflow trace |

`POST /quotation-requests` returns `{"submitted": true, "workflow": {...}}`, so
one call tells the client whether the quotation is ready or waiting on a manager.

### Approvals

| Method | Path | Roles | Summary |
| --- | --- | --- | --- |
| `GET` | `/approvals` | E M | Queue, with `status` / `overdue_only` filters |
| `GET` | `/approvals/pending-count` | E M | Badge count |
| `GET` | `/approvals/{id}` | E M | Task + request + customer + latest execution |
| `POST` | `/approvals/{id}/decision` | M | `APPROVE` / `REJECT` / `REQUEST_MODIFICATION` |

A decision body is `{decision, comments?, override_discount_percent?}`. A
comment is **required** for `REJECT` and `REQUEST_MODIFICATION`; an override may
only accompany `APPROVE`.

### Master-data approval

| Method | Path | Roles | Summary |
| --- | --- | --- | --- |
| `POST` | `/master-data-requests/customers` | E M | Propose a customer; nothing is created yet |
| `POST` | `/master-data-requests/products` | E M | Propose a product |
| `GET` | `/master-data-requests` | E M | Queue — an employee sees only their own |
| `GET` | `/master-data-requests/pending-count` | E M | Badge count |
| `GET` | `/master-data-requests/{id}` | E M | One proposal, with the payload as submitted |
| `POST` | `/master-data-requests/{id}/decision` | M | `{approve, comments?}` — approving creates the record |
| `POST` | `/master-data-requests/{id}/withdraw` | E M | Take back your own open proposal |

A refusal **requires** `comments`; a blank one is rejected rather than recorded
as a silent no. Approving returns `{request, customer?, product?}` — the settled
proposal plus whatever it created.

### Quotations and verification

| Method | Path | Roles | Summary |
| --- | --- | --- | --- |
| `GET` | `/quotations` | C E M | List — customers see only their own |
| `GET` | `/quotations/{id}` | C E M | Get a quotation |
| `GET` | `/quotations/{id}/pdf` | C E M | Download the PDF (rendered on first request) |
| `POST` | `/quotations/{id}/status` | M | Mark accepted / withdrawn / expired |
| `POST` | `/quotations/expire-due` | E M | Sweep quotations past validity |
| `GET` | `/verify/{code}` | — | **Public**: confirm a quotation is genuine and unaltered |

### Analytics

| Method | Path | Roles | Summary |
| --- | --- | --- | --- |
| `GET` | `/analytics/dashboard` | M | Every section in one call |
| `GET` | `/analytics/overview` | E M | Headline KPIs |
| `GET` | `/analytics/requests/trend` | E M | Daily counts by outcome |
| `GET` | `/analytics/products/top` | E M | Most-quoted products by value |
| `GET` | `/analytics/revenue/trend` | M | Monthly quoted value and discount |
| `GET` | `/analytics/customers/top` | M | Highest-value customers |
| `GET` | `/analytics/exceptions` | M | Which rules drive manual review |
| `GET` | `/analytics/approvals/performance` | M | Turnaround and SLA compliance |
| `GET` | `/analytics/workflow/performance` | M | Automation rate and per-step timings |

### Audit, notifications, settings, service

| Method | Path | Roles | Summary |
| --- | --- | --- | --- |
| `GET` | `/audit-logs` | M | Search the trail |
| `GET` | `/audit-logs/{entity_type}/{entity_id}` | E M | Full history for one entity |
| `GET` | `/notifications` | C E M | Your inbox |
| `GET` | `/notifications/unread-count` | C E M | Badge count |
| `POST` | `/notifications/{id}/read` | C E M | Mark one read |
| `POST` | `/notifications/read-all` | C E M | Mark everything read |
| `GET` | `/settings` | C E M | Read the active rule book |
| `GET` | `/settings/discount-policy` | C E M | Tier table and ceilings |
| `PATCH` | `/settings` | M | Re-tune the deployed workflow |
| `GET` | `/health` | — | Liveness and database check |
| `GET` | `/` | — | Service banner |
| `GET` | `/docs`, `/redoc`, `/openapi.json` | — | API documentation |

### Error format

Every handled failure returns the same envelope:

```json
{
  "error": {
    "code": "business_rule_violation",
    "message": "A comment explaining the decision is required when rejecting a request.",
    "details": { "...": "optional structured context" }
  }
}
```

| Status | Codes |
| --- | --- |
| `401` | `authentication_failed` |
| `403` | `permission_denied` |
| `404` | `not_found` |
| `409` | `business_rule_violation`, `workflow_error`, `conflict` |
| `422` | `validation_error`, `request_validation_error` |

### Pagination

List endpoints take `page` (≥1) and `page_size` (1–100) and return:

```json
{
  "items": [],
  "meta": { "total": 0, "page": 1, "page_size": 20, "total_pages": 0 }
}
```

---

## 11. Document verification

Every issued quotation carries a short `verification_code` printed on the PDF
(`A3KP-7WQX-R9MT` — drawn from an alphabet with no `O`/`0` or `I`/`1`, so it
survives being read aloud) and an `integrity_hash`: an HMAC-SHA256, keyed with
`VERIFICATION_SECRET`, over a canonical serialisation of the quotation's
financial content.

`GET /api/v1/verify/{code}` re-derives the hash from the stored document and
compares it to the one recorded at issue. Any later edit to a line amount or a
total — including a direct database edit — makes the two disagree and the
quotation reports as invalid. Because the HMAC is keyed, a tampered document
cannot be given a matching hash without the secret.

The response is deliberately thin: enough to confirm what was quoted, to whom
and for how much, without exposing line-level internals to an unauthenticated
caller.

---

## 12. Configuration

All settings come from `.env` (see `.env.example`).

| Variable | Default | Purpose |
| --- | --- | --- |
| `APP_ENV` | `development` | Environment label |
| `DEBUG` | `true` | Enables debug logging |
| `MONGODB_URI` | `mongodb://localhost:27017` | Connection string |
| `MONGODB_DB_NAME` | `quoteflow` | Database name |
| `JWT_SECRET_KEY` | — | **Change in production** |
| `JWT_ALGORITHM` | `HS256` | |
| `ACCESS_TOKEN_EXPIRE_MINUTES` | `60` | |
| `REFRESH_TOKEN_EXPIRE_DAYS` | `7` | |
| `VERIFICATION_SECRET` | — | **Change in production**; rotating it invalidates existing verification hashes |
| `CORS_ORIGINS` | `http://localhost:5173,...` | Comma-separated |
| `PDF_STORAGE_DIR` | `storage/quotations` | Where PDFs are written |

Business thresholds are **not** environment variables — they live in
`company_settings` and are edited through the API.

---

## 13. Status

### Complete

- **Authentication & authorisation** — bcrypt hashing, JWT access + refresh
  tokens, three roles with route-level guards, self-service customer
  registration that provisions the customer record, manager-only staff
  provisioning, password change. The user is re-read on every request, so a
  suspension takes effect immediately rather than at token expiry.
- **Customer management** — CRUD, search, tiers, status (active / on hold /
  blocked), credit limits, derived outstanding exposure, activity summary.
- **Product catalogue** — CRUD, SKU normalisation, soft delete, stock movements
  with floor checks, reserved-stock handling, per-product tax and discount
  overrides, customer-facing catalogue that hides cost price and shows each
  viewer's discount entitlement, category facets, text search.
- **Quotation requests** — drafts, edit, submit, cancel, resubmit with revision
  tracking, staff-raised requests on a customer's behalf, internal notes,
  per-role visibility scoping.
- **Availability verification** — sellable-stock classification, shortfall and
  lead-time reporting, configurable backorder policy, stand-alone pre-flight
  check endpoint.
- **Pricing engine** — pure, `Decimal` throughout, `ROUND_HALF_UP`, tax on the
  discounted amount, line-then-total rounding so printed figures reconcile.
- **Discount rule engine** — pure, configurable quantity tiers, customer-tier
  bonuses, per-product caps, absolute ceiling, cost-price floor, manager
  overrides, four explainable verdicts.
- **Workflow engine** — the deterministic six-step pipeline, a persisted
  execution trace per run with per-step timings and outputs, skipped-step
  recording, enforced state machine.
- **Approval management** — SLA-stamped tasks, bundled decision context,
  approve / reject / request-modification, override discounts re-priced through
  the normal pipeline, stale-request detection that reopens the task rather
  than losing the decision, protection against double decisions.
- **Quotation generation** — gap-free numbering, frozen party snapshots,
  validity windows, expiry sweep, ReportLab PDF (header, both parties, line
  table, totals, terms, verification block, page furniture), download counting.
- **Verification** — public, unauthenticated, keyed-HMAC integrity checking.
- **Audit logging** — append-only, field-level diffs, actor and client
  metadata, per-entity history.
- **Notifications** — in-app, raised by the workflow and approval services,
  role fan-out for the manager queue, inbox scoped per user.
- **Analytics** — nine aggregation endpoints covering pipeline, revenue,
  discount, exception mix, approval SLA and automation rate.
- **Configurable rule book** — validated partial updates, nested merge that
  does not wipe sibling fields, audited.
- **Master-data authorisation** — a sales employee proposes a customer or
  product and a manager authorises it; neither collection is written before
  then (48 tests). See section 6.
- **Workflow boundaries** — maximum iterations, success gate, no-op
  condition, escalation condition and budget limits, all configurable and all
  tested (47 tests). See section 4.
- **Action and checker tools** — separate modules, with the checker
  re-fetching source data and recomputing money in longhand rather than
  trusting the action tool. See section 5.
- **Failure handling** — the twelve listed failure scenarios, plus idempotency
  backed by a unique index (33 tests).
- **Tests** — 470 passing: `pytest`. Lint clean:
  `ruff check app/ tests/ scripts/`. Report:
  `python scripts/test_report.py --output TEST_REPORT.md`.
- **Frontend** — built and wired to this API; see
  [../frontend/README.md](../frontend/README.md). 200 end-to-end integration
  checks cover auth, RBAC, the workflow, approvals, PDF download, verification,
  analytics and the audit trail.
- **Demo data** — `python scripts/demo_activity.py` adds transactional activity
  (auto-approved, escalated, rejected and failed requests) on top of the seed, so
  the dashboards and approval queue have something to show.

### Not yet done
- **Email / SMS delivery** — `notifications` has a `channel` field and only
  `IN_APP` is implemented. An SMTP sender would slot in behind
  `notification_service.notify`.
- **Multi-step approval chains** — one manager decision is final. The
  `approvals` schema would carry a `level` field for value-banded escalation.
- **Quotation revisions** — a new quotation is issued per approval; superseding
  an existing quotation number (`QT-…-A`, `-B`) is not modelled.
- **Stock reservation on issue** — `reserved_quantity` is respected when
  quoting but is not incremented when a quotation is issued, so two concurrent
  quotations can promise the same units. Deliberate: reservation belongs with
  order confirmation, which is out of scope.
- **Refresh-token revocation** — refresh tokens are stateless and valid until
  expiry; there is no deny-list, so a password change does not invalidate
  outstanding tokens.
- **Rate limiting** on the login and public verification endpoints.
- **MongoDB transactions** — multi-document writes (e.g. approval + quotation)
  are sequenced rather than transactional. A replica set would allow wrapping
  them; the compensating paths (task reopening, derived outstanding amounts) are
  in place in the meantime.
