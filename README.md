# QuoteFlow

**Automated Quotation Request and Approval Management System**

QuoteFlow automates a company's sales quotation process end to end. A customer
submits a quotation request; the system validates it, verifies product
availability, calculates prices, applies the company's discount policy, obtains
manager approval where the policy requires it, and issues a verified quotation
document.

Every decision is made by explicit, configurable business rules and recorded
step by step, so each outcome is reproducible and explainable. The system uses
deterministic programming logic throughout — no LLM, no generative model, no
inference.

---

## Running it

Two terminals. MongoDB must be running locally first.

### 1. Backend — FastAPI on port 8000

```bash
cd backend

py -3.12 -m venv .venv            # first run only
.venv\Scripts\activate            # Windows
# source .venv/bin/activate       # macOS / Linux

pip install -r requirements.txt   # first run only
copy .env.example .env            # first run only (cp on macOS / Linux)

python -m app.db.seed --reset     # products, customers and logins
uvicorn app.main:app --reload --port 8000
```

API docs: **<http://127.0.0.1:8000/docs>**

Optionally add demo activity, so the dashboards and approval queue have
something to show (leave the server running and use a third terminal):

```bash
cd backend
python scripts/demo_activity.py
```

### 2. Frontend — Vite dev server on port 5173

```bash
cd frontend

npm install                       # first run only
copy .env.example .env            # first run only

npm run dev
```

Open **the URL the dev server prints** — `http://localhost:5173` by default.

> Two things worth knowing. `localhost` may resolve to IPv6 `::1`, and Vite binds
> only to what it prints, so `127.0.0.1` is not always interchangeable. And if
> port 5173 is already in use, Vite moves to the next free one and prints it —
> nothing needs changing, because the frontend reaches the API through the
> dev-server proxy rather than by absolute URL.

### Sign in

Every seeded account uses the password `QuoteFlow@2026`. In development the login
page lists them and fills the form on click.

| Role | Email | What to look at |
| --- | --- | --- |
| Sales Manager | `manager@quoteflow.example` | Approvals, analytics, the rule book, audit logs |
| Sales Employee | `sales1@quoteflow.example` | Customers, products, exception management |
| Customer — Gold tier | `rohit.desai@acme-process.example` | Catalogue, requests, quotations |
| Customer — low credit limit | `imran@sunrise-fab.example` | Triggers the credit-limit rule |

### Verifying the install

```bash
# Backend: 470 tests
cd backend && pytest && ruff check app/ tests/ scripts/

# Frontend: lint, build, and 42 page smoke tests
cd frontend && npm run lint && npm run build
SMOKE_ORIGIN=http://localhost:5173 npm test     # needs both servers running
```

---

## What it does

```
Customer submits a request
        │
        ▼
  ┌──────────────────────────────────────────┐
  │  Deterministic workflow pipeline         │
  │                                          │
  │  1. Validate the request                 │
  │  2. Verify product availability          │
  │  3. Calculate pricing  (Decimal)         │
  │  4. Evaluate discount rules              │
  │  5. Determine the approval route         │
  │  6. Generate the document   (action)     │
  │  7. Verify it independently (checker)    │
  │  8. Finalise behind the success gate     │
  └──────────────────────────────────────────┘
        │                        │
   within policy            outside policy
        │                        │
        ▼                        ▼
  Quotation issued      Sales manager reviews
  automatically                  │
        │              ┌─────────┼──────────┐
        │              ▼         ▼          ▼
        │          Approve    Reject   Request changes
        │              │                    │
        └──────────────┴──> Verified PDF    └──> back to the customer
                             + verification code
```

Every stage is shown in the UI on the request detail page, derived from the
execution trace the engine actually recorded.

### Roles

| Role | Can do |
| --- | --- |
| **Customer** | Register, browse the catalogue, submit multi-product requests, track status, download approved quotations |
| **Sales employee** | Maintain customers and products, review availability, monitor the queue, re-run blocked requests, raise requests on a customer's behalf. **Adding** a customer or product goes to a manager for approval |
| **Sales manager** | Everything above, plus approve / reject / return requests, apply override discounts, authorise new customers and products, verify documents, view analytics, read the audit trail, and re-tune the business rules |

A sales employee fills in the normal form to add a customer or a product, but it
is submitted for approval rather than created: the catalogue and the customer
tiers are what the pricing and discount rules read, so the people who raise
quotations do not also get to write those numbers. A manager approves it from
their master-data queue and the record is created by exactly the same code, with
the audit trail naming both of them.

### Example business rules

Discount ceilings by quantity — the defaults, all editable through the UI
without a code change:

| Quantity | Max discount |
| --- | --- |
| 1 – 5 | 2% |
| 6 – 20 | 5% |
| 21 – 50 | 10% |
| 51+ | 15% |

Layered on top: a customer-tier bonus (Standard/Silver/Gold/Platinum),
per-product discount caps, an absolute policy ceiling, and a cost-price floor
that refuses any discount which would sell below cost. A request that exceeds
its ceiling is routed to a manager; one that exceeds the absolute ceiling or
breaches the cost floor is refused outright.

Requests are also escalated on order value, customer credit exposure and stock
shortfall.

---

## Technology

| Layer | Stack |
| --- | --- |
| Frontend | React 18, Vite 6, Tailwind CSS 4, React Router 7, Axios, Lucide React, Recharts 3 |
| Backend | Python 3.12, FastAPI, Pydantic v2 |
| Database | MongoDB (PyMongo async driver), BSON `Decimal128` for money |
| Auth | JWT access + refresh tokens, bcrypt |
| Documents | ReportLab (PDF), HMAC-SHA256 verification hashes |
| Testing | Pytest + httpx (backend), Vitest + Testing Library (frontend) |

---

## Status

| Area | State |
| --- | --- |
| Backend — 67 endpoints, 12 collections | Complete · **470 tests**, lint clean |
| Frontend — 24 pages, 3 role experiences | Complete · **42 page smoke tests**, 0 lint errors |
| Frontend ↔ backend integration | Verified · **242 checks** across auth, RBAC, workflow, approvals, master-data approval, PDFs, verification, analytics, audit |

Deferred items, with rationale, are listed at the end of
[backend/README.md](backend/README.md#10-status) — email delivery, multi-level
approval chains, stock reservation on issue, refresh-token revocation and
MongoDB transactions.

---

## Documentation

| Document | Contents |
| --- | --- |
| [FINAL_REPORT.md](FINAL_REPORT.md) | **Start here** — implemented features, workflow architecture, collections, endpoints, measured test results, known limitations, how to run, deployment, demonstration guide |
| [backend/README.md](backend/README.md) | Architecture, the 8-step pipeline, the five workflow boundaries, the action and checker tools, master-data authorisation, business rules, all 12 database schemas, the full API reference |
| [frontend/README.md](frontend/README.md) | Page map, the Axios layer, status mapping, design tokens, the validated chart palette, testing |
| [DEPLOYMENT.md](DEPLOYMENT.md) | Docker Compose and manual deployment, secrets, MongoDB, verification, and what is deliberately not configured |
| [DEMO_GUIDE.md](DEMO_GUIDE.md) | The six demonstration scenarios, step by step, with the questions to expect |
| [backend/TEST_REPORT.md](backend/TEST_REPORT.md) | Generated test report: totals, timings, per-case results |

---

## Repository layout

```
Hack4hire/
├── README.md                 This file — how to run both halves
├── .gitignore
├── backend/
│   ├── README.md             Architecture, schemas, API reference
│   ├── app/                  api · core · db · models · schemas · services · utils
│   ├── scripts/
│   │   └── demo_activity.py  Generates demo requests, approvals, quotations
│   ├── tests/                470 tests
│   ├── requirements.txt
│   └── .env.example
└── frontend/
    ├── README.md             Pages, API layer, design system, testing
    ├── src/
    │   ├── api/              One Axios module per domain
    │   ├── components/       layout · ui · workflow
    │   ├── context/          Auth and toast providers
    │   ├── hooks/ · lib/     Data hooks, formatting, status, charts
    │   ├── pages/            auth · customer · staff · manager · common
    │   └── routes/           Role guards
    ├── package.json
    └── .env.example
```
