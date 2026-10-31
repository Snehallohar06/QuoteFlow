# QuoteFlow — Frontend

React single-page application for the QuoteFlow quotation workflow. Every screen
reads and writes the live FastAPI backend; there is no mock data anywhere in the
running application.

---

## 1. Quick start

**Prerequisites:** Node 20+, and the backend running on port 8000.

```bash
cd frontend
npm install
copy .env.example .env     # cp on macOS / Linux
npm run dev
```

Open the URL the dev server prints — **<http://localhost:5173>** by default.

> **Use the hostname the dev server prints.** On this machine `localhost`
> resolves to IPv6 `::1`, and Vite binds only to that, so `http://127.0.0.1:5173`
> will *not* reach it. If something else already holds 5173, Vite moves to the
> next free port and prints it; nothing needs changing, because the API is
> reached through the dev-server proxy rather than by absolute URL.

### Scripts

| Command | What it does |
| --- | --- |
| `npm run dev` | Dev server with HMR and the `/api` proxy |
| `npm run build` | Production build into `dist/` |
| `npm run preview` | Serve the production build locally |
| `npm run lint` | ESLint — catches undefined/unused identifiers |
| `npm test` | Page smoke suite (needs both servers running) |

### Sign in

Seeded accounts all use the password `QuoteFlow@2026`. In development the login
page lists them and fills the form on click.

| Role | Email |
| --- | --- |
| Sales Manager | `manager@quoteflow.example` |
| Sales Employee | `sales1@quoteflow.example` |
| Customer (Gold tier) | `rohit.desai@acme-process.example` |
| Customer (low credit limit) | `imran@sunrise-fab.example` |

---

## 2. How it talks to the backend

**In development, requests go through the Vite proxy.** `vite.config.js` forwards
`/api` to `http://127.0.0.1:8000`, so the browser only ever makes same-origin
requests and CORS never enters the picture. That also means the frontend works on
whatever port Vite happens to pick.

**In production**, set `VITE_API_BASE_URL` to the API origin and the Axios client
uses it as an absolute base instead.

| Variable | Default | Purpose |
| --- | --- | --- |
| `VITE_API_BASE_URL` | *(blank)* | API origin for a production build. Blank means same-origin, i.e. use the proxy. |
| `VITE_PROXY_TARGET` | `http://127.0.0.1:8000` | Where the dev-server proxy forwards `/api`. |

### The Axios layer

`src/api/client.js` owns one Axios instance and three responsibilities:

- **Token attachment** — the bearer token goes on every request except the ones
  marked `skipAuth` (login, register, public verification).
- **Silent refresh** — a `401` triggers one refresh attempt, then replays the
  original request. Concurrent 401s share a single refresh call rather than
  firing several. If the refresh fails, the session is cleared and the user
  lands on the login page with an explanation.
- **Error normalisation** — the backend's `{error: {code, message, details}}`
  envelope becomes an `ApiError` with `isAuth` / `isForbidden` / `isNotFound`
  helpers and a `fieldErrors` map, so a form can show inline field errors and a
  toast can show the message without either knowing about Axios.

One module per domain sits on top (`auth`, `products`, `customers`, `requests`,
`approvals`, `quotations`, `analytics`, `notifications`, `audit`, `settings`) and
each function mirrors one endpoint.

---

## 3. Pages

24 screens, routed in `src/App.jsx`. `/dashboard` renders a different page per
role, so every post-login redirect and sidebar link points at one place.

### Authentication
| Page | Route |
| --- | --- |
| Login | `/login` |
| Customer registration | `/register` |

### Customer
| Page | Route |
| --- | --- |
| Customer dashboard | `/dashboard` |
| Product catalogue | `/catalogue` |
| Create / edit a request | `/requests/new` |
| My quotation requests | `/requests` |
| Request detail (workflow tracking) | `/requests/:id` |
| My quotations | `/quotations` |
| Quotation detail + PDF download | `/quotations/:id` |

### Sales employee
| Page | Route |
| --- | --- |
| Sales dashboard | `/dashboard` |
| Customer management | `/customers` |
| Customer detail | `/customers/:id` |
| Product management | `/products` |
| Quotation management | `/requests` |
| Request detail | `/requests/:id` |
| Exception management | `/exceptions` |
| My add requests (master data awaiting approval) | `/master-data-requests` |

### Manager
| Page | Route |
| --- | --- |
| Manager dashboard | `/dashboard` |
| Pending approvals | `/approvals` |
| Approval detail (the decision screen) | `/approvals/:id` |
| Quotation history | `/quotations` |
| Analytics dashboard | `/analytics` |
| Master data requests (the decision queue) | `/master-data-requests` |

### Common
| Page | Route | Access |
| --- | --- | --- |
| Notifications | `/notifications` | all roles |
| Workflow execution history | `/workflow-history` | staff |
| Audit logs | `/audit-logs` | manager |
| Company settings | `/settings` | all roles read, manager writes |
| My profile | `/profile` | all roles |
| Verify a quotation | `/verify`, `/verify/:code` | linked for managers |

Adding a customer or a product needs a manager's approval. A sales employee's
“Add customer” / “Add product” submits the same payload to
`/master-data-requests` instead of creating the record, and the page says so
before they start typing. A manager's form still creates it outright.

`/verify` is reachable by any signed-in role — the backend endpoint is public,
because anyone holding a printed quotation may check it — but it is only linked
in the manager's sidebar, where document verification actually belongs.

---

## 4. Workflow tracking

The brief's nine-stage process is rendered by
`src/components/workflow/WorkflowTimeline.jsx`. The five middle stages map
one-to-one onto steps the backend's rule engine actually recorded, which is why
the component takes the latest execution as well as the request — the timeline
reflects what ran, not an assumed happy path.

```
Customer Request → Input Validation → Product Verification → Price Calculation
  → Business Rule Validation → Manager Approval → Quotation Generation
  → Independent Verification → Customer Delivery
```

Each stage resolves to one of five states: `complete`, `current`, `failed`,
`skipped` (auto-approved requests legitimately skip the manager stage), or
`pending`.

### Status mapping

The backend's request lifecycle has ten states. Four of the labels the brief asks
for are **derived** in the display layer rather than stored as their own status —
the mapping lives in one place, `src/lib/status.js`:

| Label shown | Comes from |
| --- | --- |
| Submitted | `SUBMITTED` |
| Validating | `UNDER_VALIDATION` |
| Validation Failed | `VALIDATION_FAILED` |
| **Generating Quotation** | `PRICED` — the transient step between pricing and the outcome |
| Awaiting Approval | `PENDING_APPROVAL` |
| **Escalated** | a marker shown *alongside* `PENDING_APPROVAL` when a rule raised an exception |
| Approved | `APPROVED` with no quotation yet |
| **Completed** | `APPROVED` **and** a quotation has been issued |
| Rejected | `REJECTED` |
| Modification Required | `MODIFICATION_REQUESTED` |
| **Verification Failed** | not a request state — the result of checking an issued quotation's integrity hash via `GET /verify/{code}` |

Colour carries meaning throughout: a status tone is defined once in
`lib/status.js` and every badge, timeline dot and chart reads it from there, so
the same state always looks the same.

---

## 5. Design system

White surfaces, navy for structure, blue for action. Tokens live in
`src/index.css` under Tailwind v4's `@theme`.

- `navy-*` — sidebar, headings, table headers
- `brand-*` — primary buttons, links, focus rings
- semantic tones (`success` / `warning` / `danger` / `info`) are reserved for
  status meaning, never decoration

Typography is Inter, with JetBrains Mono for identifiers (SKUs, request numbers,
verification codes). Columns of money use `font-variant-numeric: tabular-nums`
so figures align on the decimal point.

### Charts

Chart parameters live in `src/lib/charts.js`. The palette was **validated with a
contrast/CVD checker against this app's actual white chart surface**, not
eyeballed — the file records the numbers.

Most charts deliberately use a **single series**, with identity carried by the
axis labels rather than by hue. That was a correction, not a preference: an
earlier draft coloured the request-trend chart by outcome using the four status
colours, and the validator failed it — `warning` and `serious` sit at a
normal-vision ΔE of 13.6, below the 15 floor, so "pending" and "failed" segments
were genuinely hard to tell apart. Splitting that into two single-series charts
(volume over time, and outcome mix) removed the problem instead of papering over
it. Where two series are unavoidable, slots 1–2 clear every gate.

Ranked comparisons ("which rule escalates most", "step timings") are plain HTML
bars rather than a charting library, because the categories are text: the label
sits beside the bar at full contrast and the value is a direct label.

---

## 6. Structure

```
frontend/
├── index.html
├── vite.config.js            Dev proxy, alias, chunk splitting
├── vitest.config.js          jsdom + live-backend smoke suite
├── eslint.config.js
└── src/
    ├── main.jsx              Providers and router mount
    ├── App.jsx               Every route, with its role guard
    ├── index.css             Tailwind v4 theme tokens
    ├── api/                  One Axios module per domain
    │   ├── client.js         Instance, interceptors, ApiError
    │   └── auth · products · customers · requests · approvals
    │       · quotations · analytics · notifications · audit · settings
    ├── context/
    │   ├── AuthContext.jsx   Session, roles, restore-on-refresh
    │   └── ToastContext.jsx  Toast queue and ApiError rendering
    ├── hooks/
    │   ├── useAsync.js       Loader state; discards superseded runs
    │   └── useDebounce.js
    ├── lib/
    │   ├── format.js         Money, dates, durations
    │   ├── status.js         Status → label/tone/icon, in one place
    │   └── charts.js         Validated palette and chart chrome
    ├── components/
    │   ├── layout/           AppShell, Sidebar, Topbar, PageHeader
    │   ├── ui/               Button, Field, Card, Table, Modal, Badge…
    │   └── workflow/         Timeline, ExecutionTrace, PricingBreakdown
    ├── routes/
    │   └── ProtectedRoute.jsx
    ├── pages/
    │   ├── auth/ · customer/ · staff/ · manager/ · common/
    └── pages.smoke.test.jsx  Mounts all 24 pages against the live API
```

---

## 7. Access control

`ProtectedRoute` gates each route on authentication and, where relevant, on role.
It is a **usability boundary, not the security boundary** — the backend checks
the role on every endpoint, so a user who reached a page their role cannot use
would simply receive 403s. The sidebar is likewise built from a per-role list for
convenience, not enforcement.

The signed-in user is re-read from `/auth/me` on every request rather than
trusted from the token's claims, so a suspension or role change takes effect
immediately instead of at token expiry.

---

## 8. Testing

```bash
npm run lint                  # 0 errors
npm run build                 # production build
npm test                      # 37 page smoke tests
```

The smoke suite (`src/pages.smoke.test.jsx`) mounts **every routed page, for
every role, against the live backend** and asserts it renders real data with no
`console.error`. jsdom's document URL is set to the dev server's origin, so the
relative `/api/v1/...` URLs the Axios client builds resolve through the Vite
proxy and reach the real API — same-origin, no request mocking.

It therefore requires both servers to be running:

```bash
# terminal 1
cd backend && uvicorn app.main:app --port 8000

# terminal 2
cd frontend && npm run dev

# terminal 3 — pass the origin the dev server printed
SMOKE_ORIGIN=http://localhost:5173 npm test
```

What it covers: both auth pages and the signed-out redirect; all seven customer
pages; all seven employee pages; all five manager pages; the six common pages;
role-based navigation for each role; and that a customer hitting a staff route
and an employee hitting a manager route both get the access-refused page.

The three `lint` warning categories that remain are advisory, not defects:
`react-hooks/set-state-in-effect` on ordinary "fetched data arrived, put it in
state" effects, and `react-refresh/only-export-components` where a file exports a
constant beside its component.
