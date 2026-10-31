# QuoteFlow — Final Report

**Automated Quotation Request and Approval Management System**

An enterprise workflow that turns a customer's quotation request into a verified
document using explicit business rules. No LLM, no generative model, no
inference: the pricing is `Decimal` arithmetic, the discount decision is a table
lookup plus four comparisons, and the routing is boolean rules read from
configuration. Identical inputs always produce an identical execution trace, and
a test asserts exactly that.

| | |
| --- | --- |
| Backend | Python 3.12, FastAPI, Pydantic v2, MongoDB |
| Frontend | React 18, Vite 6, Tailwind CSS 4, Recharts 3 |
| API | 67 operations across 59 paths |
| Database | 12 collections |
| Tests | **470 backend**, **42 frontend page**, **242 integration** — all passing |
| Verified | 2026-10-31 against a live stack |

---

## 1. Implemented features

### Workflow boundaries — all five controls

| Control | How it works | Tests |
| --- | --- | --- |
| **Maximum iterations** | 3 retries per step, transient failures only. A permanent failure (a validation verdict) consumes zero retries. Counts recorded on the step, the execution and the request. Exhaustion escalates rather than surfacing an unhandled error. | 11 |
| **Success gate** | Six conditions, all required for `COMPLETED`. Allow-on-proof: an unevaluated condition counts as unmet. State recorded on every execution, including failed ones. | 10 |
| **No-op condition** | A settled request stops the run immediately, records `NO_OP` with all eight steps skipped, increments `no_op_count`, writes an audit entry. No second document is possible. | 5 |
| **Escalation condition** | Seven reasons, each recorded as an `EscalationReason`. Reachable from every live status. Notifies all active managers and audits the reason, attempt and retry count. | 8 |
| **Budget limit** | Attempts committed before work starts (so a crash still consumes one); time checked before every step against per-run and whole-request ceilings; resource ceilings on lines and quantity. | 13 |

Every limit is a field in `company_settings.execution_policy`, changeable
through the API at runtime. A test re-tunes each one and proves the new value
takes effect.

### Action tool and checker tool

Two separate modules, and the checker does not trust the action tool.

- **`action_tool.py`** issues the quotation, renders the PDF, records the path.
  It owns **idempotency**: a unique index on `quotations.request_id` makes a
  second quotation impossible, and a concurrent loser adopts the winner's
  document.
- **`checker_tool.py`** re-fetches products, the customer and the rule book from
  their own collections, then **recomputes every amount in longhand with
  `Decimal`** rather than calling the pricing engine. That is the point: sharing
  the pricing function would mean a bug produced the same wrong answer twice and
  the check would pass. It runs nine checks covering product information,
  quantities, unit prices, discount and tax calculations, the final amount,
  approval status, the integrity digest and the PDF file. A rejection escalates
  with `VERIFICATION_MISMATCH` — **a document that fails independent
  recalculation is never delivered.**

### Master-data authorisation

A sales employee cannot add a customer or a product. They fill in the normal
form, it is submitted to a manager, and the record exists only once a manager
approves it.

The reason is that both collections are what the rule engine reads: a product's
`unit_price` and `cost_price` become the price quoted and the floor no discount
may breach, and a customer's `tier` and `credit_limit` decide what discount they
may ask for. Letting whoever raises a quotation also write those numbers would
make the discount policy advisory rather than binding.

| Rule | How it is enforced | Tests |
| --- | --- | --- |
| An employee cannot create master data | `POST /customers` and `POST /products` require a manager; the 403 names the route to submit to instead | 6 |
| Nothing exists before approval | The proposal holds the payload; neither collection is touched | 9 |
| An employee cannot approve their own request | The decision endpoint is manager-only | 7 |
| The same record cannot be queued twice | Partial unique index on `(entity_type, dedupe_key)` over `PENDING` rows | 3 |
| A decision cannot be taken twice | The status is part of the update filter, so a second decision matches nothing | 3 |
| A refusal must say why | A blank comment is refused with 409 | 2 |
| A refused record is not blacklisted | The constraint covers only open proposals, so a corrected version can be resubmitted | 2 |

An approved record is created by **the same service functions** the direct route
calls, with the manager as the actor — there is no second write path. The audit
trail names both people: `MASTER_DATA_REQUESTED` by the employee,
`MASTER_DATA_APPROVED` by the manager, and `CUSTOMER_CREATED` /
`PRODUCT_CREATED` against the manager who authorised it.

**Editing** an existing record is deliberately not gated. The control exists so
new records enter the catalogue deliberately; a corrected phone number or a
stock movement stays with the employee doing the work.

### Core application

- **Authentication** — bcrypt (salted, cost-factor verified), JWT access +
  refresh, silent refresh with replay, three roles. The user is re-read on every
  request, so a suspension takes effect immediately rather than at token expiry.
- **Customers** — CRUD (adding needs manager approval), tiers driving discount
  bonuses, credit limits driving the exposure rule, status (active / on hold /
  blocked), derived outstanding amount, activity roll-up.
- **Products** — CRUD (adding needs manager approval), SKU normalisation, soft
  delete (historical quotations still reference them), stock movements with
  floor checks, reserved-stock
  handling, per-product tax and discount overrides, a customer-facing catalogue
  that hides cost price and shows each viewer's entitlement.
- **Requests** — drafts, edit, submit, cancel, resubmit with revision tracking,
  staff-raised requests on a customer's behalf, internal notes, per-role
  visibility scoping.
- **Pricing** — `Decimal` throughout, `ROUND_HALF_UP`, tax on the discounted
  amount, line-then-total rounding so printed figures reconcile exactly.
- **Discounts** — configurable quantity tiers, customer-tier bonuses,
  per-product caps, an absolute ceiling, a cost-price floor, manager overrides,
  four explainable verdicts.
- **Approvals** — SLA-stamped tasks, bundled decision context, approve / reject
  / request-modification, override discounts repriced through the normal
  pipeline, stale-request detection that reopens the task rather than losing the
  decision, protection against double decisions.
- **Quotations** — gap-free numbering, frozen party snapshots, validity windows,
  expiry sweep, ReportLab PDF, download counting, public HMAC-keyed verification.
- **Audit** — append-only, field-level diffs, actor and client metadata.
- **Notifications** — in-app, raised by the workflow and approval services, with
  role fan-out for the manager queue.
- **Analytics** — nine aggregations covering pipeline, revenue, discount,
  exception mix, approval SLA and automation rate.
- **Frontend** — 24 pages across three role experiences, all reading and writing
  the live API.

---

## 2. Workflow architecture

```
┌─────────────────────────────────────────────────────────────────────┐
│  Customer / staff submits a request                                 │
└───────────────────────────────┬─────────────────────────────────────┘
                               ▼
                ┌──────────────────────────────┐
                │  No-op guard                 │  settled? stop, record
                ├──────────────────────────────┤
                │  Budget guard                │  attempts/time spent? escalate
                └──────────────┬───────────────┘
                               ▼
  ┌─────────────────────────────────────────────────────────────────┐
  │  1  VALIDATE_REQUEST          customer, lines, products, limits │ retried
  │  2  CHECK_AVAILABILITY        sellable stock per line           │
  │  3  CALCULATE_PRICING         Decimal arithmetic only           │ pure
  │  4  EVALUATE_DISCOUNT_RULES   policy applied to those numbers   │ pure
  │  5  DETERMINE_APPROVAL_ROUTE  auto-approve, or escalate         │
  │  6  GENERATE_DOCUMENT         ACTION TOOL  — issue + render PDF │ retried
  │  7  VERIFY_DOCUMENT           CHECKER TOOL — recompute, verify  │ retried
  │  8  FINALISE                  evaluate the success gate         │
  └───────────────────────────────┬─────────────────────────────────┘
                                  ▼
          ┌───────────────────────┼───────────────────────┐
          ▼                       ▼                       ▼
     COMPLETED             PENDING_APPROVAL          ESCALATED
  (gate fully met)        (manager decides)     (parked for a human)
```

Steps 3 and 4 are deliberately separate: step 3 only computes numbers, step 4
only applies policy to them. That split keeps the arithmetic testable without a
rule book and the rules testable without re-deriving totals. Steps 3–5 are not
retried, because retrying pure arithmetic over in-memory data recomputes the
identical answer.

Every run persists one `workflow_executions` document holding the per-step
inputs, decision, retry count, duration and errors, plus the budget state, the
retry log and the six gate conditions. **The automation is explainable after the
fact rather than a black box.**

### Request lifecycle

Twelve statuses. Three are terminal: `COMPLETED`, `REJECTED`, `CANCELLED`.
`APPROVED` is *not* terminal — it means "authorised, document not yet verified".
`ESCALATED` is reachable from every live status and is resubmittable.
`REQUEST_TRANSITIONS` is the authoritative table; every transition goes through
`assert_transition`, which refuses anything not listed.

---

## 3. Database collections

| Collection | Holds | Key indexes |
| --- | --- | --- |
| `users` | Authentication identities and roles | `email` unique |
| `customers` | The commercial party a quotation addresses | `code` unique, `email` unique, text search |
| `products` | The sellable catalogue | `sku` unique, text search |
| `quotation_requests` | The working document of the workflow | `request_number` unique, `(customer_id, created_at)`, `(status, created_at)` |
| `quotations` | The immutable issued document | `quotation_number` unique, `verification_code` unique, **`request_id` unique (idempotency)** |
| `approvals` | One task per request needing a decision | `(status, created_at)`, `request_id` |
| `master_data_requests` | An employee's proposal to add a customer or product | `reference` unique, `(status, created_at)`, **`(entity_type, dedupe_key)` unique over `PENDING`** |
| `workflow_executions` | The rule engine's own audit trail | `(request_id, started_at)`, `outcome` |
| `audit_logs` | Append-only record of every state change | `created_at`, `(entity_type, entity_id)`, `action` |
| `notifications` | In-app messages | `(user_id, read, created_at)` |
| `company_settings` | The editable rule book | `key` unique |
| `counters` | Gap-free document numbering | `_id` |

Money is stored as BSON `Decimal128`, which is lossless. Indexes are applied
idempotently at startup; there is no migration step.

Full field-by-field schemas: [backend/README.md §8](backend/README.md).

---

## 4. API endpoints

67 operations across 59 paths: 65 under `/api/v1`, plus `/` and `/health`.
Counted from the live OpenAPI document. Interactive documentation at `/docs`.

| Group | Operations | Access |
| --- | --- | --- |
| Authentication | 6 | public / all / manager |
| Products | 9 | catalogue all roles; staff maintain; **add and delete manager** |
| Customers | 6 | staff maintain; **add and status change manager** |
| Master-data approval | 7 | staff propose; only managers decide |
| Quotation requests & workflow | 9 | customers scoped to their own; staff all |
| Approvals | 4 | staff may watch; only managers decide |
| Quotations & verification | 6 | customers scoped; `/verify/{code}` public |
| Analytics | 9 | employee for operational; manager for commercial |
| Audit logs | 2 | manager (read-only — no write endpoint exists) |
| Notifications | 4 | own inbox only |
| Company settings | 3 | all read; manager writes |
| Service | 2 | public |

Every handled failure returns the same envelope:
`{"error": {"code", "message", "details"}}` with `401` / `403` / `404` / `409` /
`422` used consistently.

Full reference: [backend/README.md §9](backend/README.md).

---

## 5. Testing results

Generated by `python scripts/test_report.py` — full output in
[backend/TEST_REPORT.md](backend/TEST_REPORT.md).

### Backend — 470 tests, 100% pass, 644 s

| Area | Cases |
| --- | --- |
| Security (auth, RBAC, passwords, downloads, config) | 67 |
| Master-data authorisation (manager approval) | 48 |
| Workflow boundaries (retries, gate, no-op, escalation, budget) | 47 |
| Workflow pipeline | 46 |
| Request state machine and money helpers | 39 |
| Discount rule engine (pure policy) | 35 |
| Failure handling and idempotency | 33 |
| Catalogue, products and customers | 32 |
| Analytics, audit trail and settings | 27 |
| Authentication and access control | 25 |
| Manager approvals | 23 |
| Quotations, PDF and verification | 19 |
| Pricing engine (pure arithmetic) | 16 |
| End-to-end demonstration scenarios | 13 |

### The twelve required failure scenarios

All tested, each asserting that the error is recorded, the status updated, the
submitted information preserved, and a retry attempted only where it could help.

| # | Scenario | Outcome asserted |
| --- | --- | --- |
| 1 | Missing customer information | `VALIDATION_FAILED`, 0 retries, lines preserved |
| 2 | Invalid product ID | `404`; malformed ID `422`; discontinued mid-draft fails with notes intact |
| 3 | Invalid quantity | `422` at the schema; over-ceiling fails validation |
| 4 | Product unavailable | Escalates with shortfall and lead time; fails when backorders are off |
| 5 | Excessive discount | Escalates; beyond the absolute ceiling or below cost is refused |
| 6 | Database connection failure | Retried then recovers; persistent fault escalates with the error on the step |
| 7 | Duplicate request | One quotation per request, enforced by a unique index; action tool idempotent |
| 8 | Manager rejection | `REJECTED`, no document, reason mandatory |
| 9 | PDF generation failure | Retried then escalates; an empty file is caught too |
| 10 | Verification mismatch | Tampered total and tampered unit price both caught; escalates and audits |
| 11 | Maximum retries exceeded | Stops at exactly the limit, retry log on the execution |
| 12 | Workflow timeout | Escalates with `BUDGET_EXCEEDED`, no document issued |

### Frontend — 42 page tests, 100% pass

Mounts **every routed page, for every role, against the live backend** and fails
if any page logs a `console.error` or renders without real data. Covers both auth
pages and the signed-out redirect, all seven customer pages, all eight employee
pages, all six manager pages, the six common pages, the boundary-control panels,
the master-data approval notices and queue, role-based navigation, and that
cross-role access shows the refusal page.

### Integration — 242 checks, 100% pass

`python scripts/verify_integration.py` drives the API exactly as the frontend's
Axios layer does, through the Vite proxy, verifying every response shape the
React code depends on.

### Security verification — 67 tests

Includes a **sweep of the live route table** asserting that every non-public
route answers `401` without a token — rather than a hand-written list that could
drift. Also: forged and expired tokens refused, refresh tokens rejected as
access tokens, suspension immediate, bcrypt salting, no plaintext stored or
returned, customer data isolation, self-approval refused, PDF downloads scoped
to the owner, secrets read from the environment, no hard-coded secrets in the
source, and no write endpoint on the audit trail.

### The demonstration scenarios

The five workflow scenarios were verified live against the running stack on
2026-10-31 and are covered by 13 tests in `tests/test_end_to_end_scenarios.py`.
The demo guide's sixth scenario — master-data approval — is covered by the 48
tests in `tests/test_master_data_requests.py` and was verified live the same
day:

| Scenario | Result |
| --- | --- |
| 1 — valid request → verified quotation | `COMPLETED`, all six gate conditions met, PDF downloadable, publicly verifiable |
| 2 — invalid information | `VALIDATION_FAILED`, reason recorded, no document, gate unsatisfied |
| 3 — excessive discount | `PENDING_APPROVAL`, document step skipped, then completed on approval with an 8% override |
| 4 — manager rejection | `REJECTED`, reason mandatory, no document, re-run refused as settled |
| 5 — temporary failure | Retried within the limit; attempt ceiling escalates with `BUDGET_EXCEEDED` rather than looping |
| 6 — employee adds master data | Direct creation refused with the approval route named; proposal queued; manager's approval creates the record and the audit trail names both people |

---

## 6. Known limitations

Stated plainly. None of these are claimed as working.

### Not implemented

- **Email / SMS delivery.** `notifications` carries a `channel` field and only
  `IN_APP` is implemented. An SMTP sender would slot in behind
  `notification_service.notify`.
- **Multi-level approval chains.** One manager decision is final, for both
  quotation approvals and master-data additions. The `approvals` schema would
  need a `level` field for value-banded escalation.
- **Master-data *edits* are not gated.** Only adding a customer or product
  needs a manager; changing an existing record's price or credit limit does
  not. The `master_data_requests` model has room for an `UPDATE` action, but it
  is not implemented, so an employee can still change a price they could not
  have introduced.
- **Quotation revisions.** A new quotation is issued per approval; superseding
  an existing number (`QT-…-A`, `-B`) is not modelled.
- **Stock reservation on issue.** `reserved_quantity` is respected when quoting
  but not incremented when a quotation is issued, so two concurrent quotations
  can promise the same units. Deliberate: reservation belongs with order
  confirmation, which is out of scope.
- **Refresh-token revocation.** Refresh tokens are stateless and valid until
  expiry; there is no deny-list, so a password change does not invalidate
  outstanding refresh tokens.
- **Rate limiting** on the login and public verification endpoints. Belongs at
  the reverse proxy.
- **TLS termination.** Deploy behind a proxy that holds the certificates.

### Architectural constraints

- **No MongoDB transactions.** Multi-document writes (approval + quotation) are
  sequenced rather than atomic, because transactions need a replica set.
  Compensating paths exist: the approval task reopens if the re-run fails, the
  outstanding amount is derived rather than incremented, and the unique index
  prevents a duplicate quotation. A replica set would allow wrapping these
  properly.
- **The checker shares the rounding convention, not the arithmetic.** It writes
  the sums out longhand with `Decimal` and `ROUND_HALF_UP`, independently of
  `pricing_engine`. It would not catch a disagreement about the rounding
  *convention* itself — only about its application. A fully independent
  implementation would need a second specification to compare against.
- **Retries are in-process.** A crash between steps loses the run; the attempt
  is still counted (committed before work starts) and the request can be
  reprocessed by staff. There is no durable queue or outbox.
- **Horizontal scaling untested.** The app keeps no in-process state, so
  multiple backend replicas should work, but only the two-worker single-host
  configuration has been tested.

### Testing gaps

- **No automated browser test.** The frontend suite runs in jsdom, which
  executes React but does not paint. Layout and visual regressions are not
  covered — click through the three roles once before demonstrating.
- **The time-budget test overrides the clock** rather than sleeping, which is
  deterministic but means the real wall-clock path is exercised only by the
  arithmetic unit test.
- **Concurrency is tested by simulation.** The duplicate-quotation race is
  tested by provoking the duplicate-key error directly, not by two genuinely
  parallel requests.

---

## 7. Running locally

MongoDB must be running. Two terminals.

```bash
# Terminal 1 — backend on :8000
cd backend
py -3.12 -m venv .venv && .venv\Scripts\activate    # first run only
pip install -r requirements.txt                      # first run only
copy .env.example .env                               # first run only
python -m app.db.seed --reset
uvicorn app.main:app --reload --port 8000

# Terminal 2 — frontend
cd frontend
npm install                                          # first run only
copy .env.example .env                               # first run only
npm run dev
```

Open **the URL the dev server prints** — `http://localhost:5173` by default.

Optional demo data so the dashboards and approval queue have content:

```bash
cd backend && python scripts/demo_activity.py
```

### Accounts

Every seeded account uses `QuoteFlow@2026`. The development login page lists them
and fills the form on click.

| Role | Email |
| --- | --- |
| Sales Manager | `manager@quoteflow.example` |
| Sales Employee | `sales1@quoteflow.example` |
| Customer (Gold tier) | `rohit.desai@acme-process.example` |
| Customer (low credit limit) | `imran@sunrise-fab.example` |

### Two local gotchas

- `localhost` may resolve to IPv6 `::1`, and Vite binds only to what it prints,
  so `127.0.0.1` is not always interchangeable.
- If port 5173 is taken, Vite moves to the next free one and prints it. Nothing
  needs changing — the frontend reaches the API through the dev-server proxy
  rather than by absolute URL.

### Verifying the install

```bash
cd backend
pytest                                        # 470 tests
ruff check app/ tests/ scripts/
python scripts/test_report.py --output TEST_REPORT.md

cd ../frontend
npm run lint && npm run build
SMOKE_ORIGIN=http://localhost:5173 npm test   # 42 page tests, needs both servers

cd ../backend
python scripts/verify_integration.py --frontend http://localhost:5173   # 242 checks
```

---

## 8. Deployment

Full instructions, including the manual route and the MongoDB checklist, are in
**[DEPLOYMENT.md](DEPLOYMENT.md)**. The short version:

```bash
cp .env.docker.example .env      # then set the two secrets
docker compose up --build -d
docker compose exec backend python -m app.db.seed --reset
```

Application on **<http://localhost:8080>**.

| Service | Published | Notes |
| --- | --- | --- |
| `frontend` | `8080` → 80 | nginx serving the bundle, proxying `/api` |
| `backend` | — | uvicorn, 2 workers, non-root user |
| `mongo` | — | health-gated; the backend waits for it |

Only the frontend publishes a port — the API and database stay on the internal
network. Two volumes persist the database and the generated PDFs.

**Secrets.** `JWT_SECRET_KEY` and `VERIFICATION_SECRET` have no defaults;
compose uses `${VAR:?message}` so the stack refuses to start without them. A
test fails the build if a shipped template ever contains a usable key. Rotating
`VERIFICATION_SECRET` invalidates verification for every quotation already
issued, so treat it as permanent for a deployment.

---

## 9. Demonstration guide

Step-by-step script with the six scenarios, what to point at on each screen,
and the questions to expect: **[DEMO_GUIDE.md](DEMO_GUIDE.md)**.

The framing in one sentence:

> QuoteFlow turns a quotation request into a verified document using explicit
> business rules, and it can prove what it did at every step.

The three things worth showing if time is short:

1. **The success gate** on a completed request — six conditions, all ticked,
   with the point that the request could not have completed with any one
   unticked.
2. **The workflow trace** — expand `VERIFY_DOCUMENT` to show the checker tool
   re-reading the catalogue and recomputing every amount independently.
3. **Tamper with a stored total in the database and re-verify** — the integrity
   digest fails, the checker rejects it, and the request escalates rather than
   delivering the document.

And if the question is about who may change what: sign in as the sales employee,
press **Add customer**, and show that it goes to the manager's queue rather than
creating the record — then approve it as the manager and show the audit trail
naming both people.

---

## Documentation index

| Document | Contents |
| --- | --- |
| [README.md](README.md) | Project overview and how to run both halves |
| [backend/README.md](backend/README.md) | Architecture, the 8-step pipeline, the five boundaries, the action and checker tools, master-data authorisation, business rules, 12 schemas, the full API reference |
| [frontend/README.md](frontend/README.md) | Page map, Axios layer, status mapping, design tokens, validated chart palette |
| [DEPLOYMENT.md](DEPLOYMENT.md) | Docker Compose and manual deployment, secrets, MongoDB, what is not configured |
| [DEMO_GUIDE.md](DEMO_GUIDE.md) | The six scenarios, step by step |
| [backend/TEST_REPORT.md](backend/TEST_REPORT.md) | Generated test report with per-case results |
