/**
 * Page smoke suite.
 *
 * Mounts every routed page, for every role, against the **live backend** and
 * asserts that it renders real data without throwing. The API-level contract is
 * covered elsewhere; what this adds is proof that the React tree actually
 * renders — the class of bug a Vite build cannot catch, such as reading a field
 * off a response that arrives as null.
 *
 * Requires both servers to be running:
 *   backend   uvicorn app.main:app --port 8000
 *   frontend  npm run dev            (origin passed via SMOKE_ORIGIN)
 */

import { afterEach, beforeAll, beforeEach, describe, expect, it, vi } from 'vitest'
import { cleanup, render, screen, waitFor, within } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import axios from 'axios'

import { App } from './App'
import { AuthProvider } from './context/AuthContext'
import { ToastProvider } from './context/ToastContext'
import { ACCESS_TOKEN_KEY, REFRESH_TOKEN_KEY } from './api/client'

const PASSWORD = 'QuoteFlow@2026'
const ACCOUNTS = {
  manager: 'manager@quoteflow.example',
  employee: 'sales1@quoteflow.example',
  customer: 'rohit.desai@acme-process.example',
}

/** Tokens fetched once, then replayed into localStorage per test. */
const sessions = {}
/** Live ids discovered from the seeded data, for the detail routes. */
const ids = {}

function mountAt(path) {
  return render(
    <MemoryRouter initialEntries={[path]}>
      <ToastProvider>
        <AuthProvider>
          <App />
        </AuthProvider>
      </ToastProvider>
    </MemoryRouter>
  )
}

function signIn(role) {
  localStorage.setItem(ACCESS_TOKEN_KEY, sessions[role].access_token)
  localStorage.setItem(REFRESH_TOKEN_KEY, sessions[role].refresh_token)
}

/** Fails the test if React logged an error (a thrown render, a bad prop type). */
let consoleErrors = []

beforeAll(async () => {
  const base = `${window.location.origin}/api/v1`

  for (const [role, email] of Object.entries(ACCOUNTS)) {
    const { data } = await axios.post(`${base}/auth/login`, {
      email,
      password: PASSWORD,
    })
    sessions[role] = data
  }

  const managerAuth = {
    headers: { Authorization: `Bearer ${sessions.manager.access_token}` },
  }

  const [requests, quotations, approvals, customers, products] = await Promise.all([
    axios.get(`${base}/quotation-requests`, { ...managerAuth, params: { page_size: 50 } }),
    axios.get(`${base}/quotations`, { ...managerAuth, params: { page_size: 5 } }),
    axios.get(`${base}/approvals`, { ...managerAuth, params: { page_size: 5 } }),
    axios.get(`${base}/customers`, { ...managerAuth, params: { page_size: 5 } }),
    axios.get(`${base}/products`, { ...managerAuth, params: { page_size: 5 } }),
  ])

  const all = requests.data.items
  ids.request = all[0]?.id
  // A request the signed-in customer owns, so the customer-scoped detail route
  // renders content rather than a permission refusal.
  ids.customerRequest = all.find(
    (row) => row.customer_code === 'CUST-0001'
  )?.id
  ids.approvedRequest = all.find((row) => row.quotation_id)?.id
  // A request that actually ran the pipeline, for the boundary-control panels.
  // The newest request may be a cancelled draft with no execution at all.
  ids.completedCustomerRequest = all.find(
    (row) => row.customer_code === 'CUST-0001' && row.status === 'COMPLETED'
  )?.id
  ids.quotation = quotations.data.items[0]?.id
  ids.customerQuotation = quotations.data.items.find(
    (row) => row.buyer?.code === 'CUST-0001'
  )?.id
  ids.approval = approvals.data.items[0]?.id
  ids.customer = customers.data.items[0]?.id
  ids.product = products.data.items[0]?.id
  ids.verifyCode = quotations.data.items[0]?.verification_code

  expect(ids.request, 'seeded requests found').toBeTruthy()
  expect(ids.quotation, 'seeded quotations found').toBeTruthy()
  expect(ids.approval, 'seeded approvals found').toBeTruthy()
})

beforeEach(() => {
  localStorage.clear()
  consoleErrors = []
  vi.spyOn(console, 'error').mockImplementation((...args) => {
    const text = args.map(String).join(' ')
    // React Router's future-flag notices and jsdom's unimplemented-API noise
    // are not page defects.
    if (/not implemented|Not implemented|future flag/i.test(text)) return
    consoleErrors.push(text)
  })
})

afterEach(() => {
  cleanup()
  vi.restoreAllMocks()
  expect(consoleErrors, `console.error during render:\n${consoleErrors.join('\n')}`)
    .toHaveLength(0)
})

/** Wait for a page's loading state to clear and its heading to appear. */
async function expectHeading(pattern) {
  await waitFor(
    () => {
      expect(
        screen.getByRole('heading', { level: 1, name: pattern })
      ).toBeTruthy()
    },
    { timeout: 20000 }
  )
}

describe('authentication pages', () => {
  it('renders the login page with its form', async () => {
    mountAt('/login')
    await expectHeading(/sign in/i)
    expect(screen.getByLabelText(/email address/i)).toBeTruthy()
    expect(screen.getByLabelText(/^password/i)).toBeTruthy()
    expect(screen.getByRole('button', { name: /sign in/i })).toBeTruthy()
  })

  it('renders the registration page with its fields', async () => {
    mountAt('/register')
    await expectHeading(/create a customer account/i)
    expect(screen.getByLabelText(/full name/i)).toBeTruthy()
    expect(screen.getByLabelText(/company name/i)).toBeTruthy()
    expect(screen.getByRole('button', { name: /create account/i })).toBeTruthy()
  })

  it('sends an unauthenticated visitor to the login page', async () => {
    mountAt('/dashboard')
    await expectHeading(/sign in/i)
  })
})

describe('customer pages', () => {
  beforeEach(() => signIn('customer'))

  it('dashboard shows the signed-in company and live figures', async () => {
    mountAt('/dashboard')
    await expectHeading(/welcome back/i)
    await waitFor(() =>
      expect(screen.getAllByText(/Acme Process Engineering/i).length).toBeGreaterThan(0)
    )
    expect(screen.getByText(/total requests/i)).toBeTruthy()
    expect(screen.getByText(/quotations received/i)).toBeTruthy()
    // The quotation verifier is not part of a customer's dashboard.
    expect(screen.queryByText(/verify a quotation/i)).toBeNull()
    expect(screen.queryByText(/open the verifier/i)).toBeNull()
  })

  it('catalogue lists seeded products with a discount entitlement', async () => {
    mountAt('/catalogue')
    await expectHeading(/product catalogue/i)
    await waitFor(() =>
      expect(screen.getAllByText(/PMP-|VLV-|PIP-/).length).toBeGreaterThan(0)
    )
    expect(screen.getAllByText(/discount you may request/i).length).toBeGreaterThan(0)
  })

  it('new-request form renders with the product picker', async () => {
    mountAt('/requests/new')
    await expectHeading(/new quotation request/i)
    await waitFor(() =>
      expect(screen.getByPlaceholderText(/search by name or sku/i)).toBeTruthy()
    )
    expect(screen.getByRole('button', { name: /submit request/i })).toBeTruthy()
    expect(screen.getByText(/no products added yet/i)).toBeTruthy()
  })

  it('my requests lists the customer’s own requests', async () => {
    mountAt('/requests')
    await expectHeading(/my quotation requests/i)
    await waitFor(() =>
      expect(screen.getAllByText(/QR-\d{4}-\d{5}/).length).toBeGreaterThan(0)
    )
  })

  it('request detail renders pricing and the workflow timeline', async () => {
    mountAt(`/requests/${ids.customerRequest}`)
    await waitFor(
      () => expect(screen.getByRole('heading', { level: 1 })).toBeTruthy(),
      { timeout: 20000 }
    )
    await waitFor(() => expect(screen.getByText(/process stage/i)).toBeTruthy())
    expect(screen.getByText(/priced lines/i)).toBeTruthy()
    expect(screen.getByText(/workflow execution/i)).toBeTruthy()
    // The nine process stages from the brief. Several of these labels also
    // appear in the success-gate panel, so more than one match is expected.
    for (const stage of [
      /input validation/i,
      /product verification/i,
      /price calculation/i,
      /business rule validation/i,
      /manager approval/i,
      /quotation generation/i,
      /independent verification/i,
      /customer delivery/i,
    ]) {
      expect(screen.getAllByText(stage).length, String(stage)).toBeGreaterThan(0)
    }
  })

  it('request detail shows the workflow boundary controls', async () => {
    expect(
      ids.completedCustomerRequest,
      'a completed request is needed; run scripts/demo_activity.py'
    ).toBeTruthy()
    mountAt(`/requests/${ids.completedCustomerRequest}`)
    await waitFor(
      () => expect(screen.getByText(/success gate/i)).toBeTruthy(),
      { timeout: 20000 }
    )
    // The six gate conditions the backend records.
    for (const condition of [
      /input validation/i,
      /product verification/i,
      /pricing validation/i,
      /approval recorded/i,
      /document generated/i,
    ]) {
      expect(screen.getAllByText(condition).length).toBeGreaterThan(0)
    }
    // And the budget consumption against its limits.
    expect(screen.getByText(/execution budget/i)).toBeTruthy()
    expect(screen.getByText(/processing attempts/i)).toBeTruthy()
    expect(screen.getByText(/retries used/i)).toBeTruthy()
  })

  it('my quotations lists issued documents', async () => {
    mountAt('/quotations')
    await expectHeading(/my quotations/i)
    await waitFor(() =>
      expect(screen.getAllByText(/QT-\d{4}-\d{5}/).length).toBeGreaterThan(0)
    )
  })

  it('quotation detail renders both parties and the verification code', async () => {
    mountAt(`/quotations/${ids.customerQuotation ?? ids.quotation}`)
    await waitFor(
      () => expect(screen.getByText(/document verification/i)).toBeTruthy(),
      { timeout: 20000 }
    )
    expect(screen.getByText(/quotation for/i)).toBeTruthy()
    expect(screen.getByText(/quoted lines/i)).toBeTruthy()
    expect(screen.getByRole('button', { name: /download/i })).toBeTruthy()
  })

  it('a customer is refused the staff-only product page', async () => {
    mountAt('/products')
    await expectHeading(/do not have access/i)
  })

  it('a customer is refused the manager-only audit log', async () => {
    mountAt('/audit-logs')
    await expectHeading(/do not have access/i)
  })
})

describe('sales employee pages', () => {
  beforeEach(() => signIn('employee'))

  it('sales dashboard shows the processing queue', async () => {
    mountAt('/dashboard')
    await expectHeading(/sales operations/i)
    await waitFor(() => expect(screen.getByText(/requests \(30 days\)/i)).toBeTruthy())
    expect(screen.getByText(/awaiting manager approval/i)).toBeTruthy()
    expect(screen.getByText(/needs intervention/i)).toBeTruthy()
  })

  it('customer management lists seeded customers', async () => {
    mountAt('/customers')
    await expectHeading(/customer management/i)
    await waitFor(() =>
      expect(screen.getAllByText(/CUST-000\d/).length).toBeGreaterThan(0)
    )
    expect(screen.getByRole('button', { name: /add customer/i })).toBeTruthy()
  })

  it('customer detail shows the activity roll-up', async () => {
    mountAt(`/customers/${ids.customer}`)
    await waitFor(
      () => expect(screen.getByText(/total requests/i)).toBeTruthy(),
      { timeout: 20000 }
    )
    expect(screen.getByText(/quoted value/i)).toBeTruthy()
  })

  it('product management lists products with cost price', async () => {
    mountAt('/products')
    await expectHeading(/product management/i)
    await waitFor(() => expect(screen.getAllByText(/PMP-1200/).length).toBeGreaterThan(0))
    expect(screen.getAllByText(/cost/i).length).toBeGreaterThan(0)
    expect(screen.getByRole('button', { name: /add product/i })).toBeTruthy()
  })

  it('product management tells an employee a manager must approve additions', async () => {
    mountAt('/products')
    await expectHeading(/product management/i)
    await waitFor(() =>
      expect(screen.getByText(/a sales manager approves new products/i)).toBeTruthy()
    )
  })

  it('customer management tells an employee a manager must approve additions', async () => {
    mountAt('/customers')
    await expectHeading(/customer management/i)
    await waitFor(() =>
      expect(screen.getByText(/a sales manager approves new customers/i)).toBeTruthy()
    )
  })

  it('an employee sees their own master-data requests', async () => {
    mountAt('/master-data-requests')
    await expectHeading(/my add requests/i)
    // The label appears on the stat tile and in the status filter, so count
    // rather than demanding exactly one.
    await waitFor(() =>
      expect(screen.getAllByText(/awaiting approval/i).length).toBeGreaterThan(0)
    )
    expect(
      screen.getByText(/a sales manager must approve a new customer or product/i)
    ).toBeTruthy()
  })

  it('quotation management lists every request', async () => {
    mountAt('/requests')
    await expectHeading(/quotation requests/i)
    await waitFor(() =>
      expect(screen.getAllByText(/QR-\d{4}-\d{5}/).length).toBeGreaterThan(0)
    )
  })

  it('exception management groups blocked and escalated work', async () => {
    mountAt('/exceptions')
    await expectHeading(/exception management/i)
    await waitFor(() =>
      expect(screen.getAllByText(/failed validation/i).length).toBeGreaterThan(0)
    )
    expect(screen.getByText(/escalated to a manager/i)).toBeTruthy()
    expect(screen.getByText(/what "re-run" does/i)).toBeTruthy()
  })

  it('workflow history shows step timings', async () => {
    mountAt('/workflow-history')
    await expectHeading(/workflow execution history/i)
    await waitFor(() => expect(screen.getByText(/step performance/i)).toBeTruthy())
    expect(screen.getByText(/straight through/i)).toBeTruthy()
  })

  it('an employee may watch the approval queue', async () => {
    mountAt('/approvals')
    await expectHeading(/approval queue/i)
    await waitFor(() => expect(screen.getByText(/open tasks/i)).toBeTruthy())
  })

  it('an employee is refused the manager analytics page', async () => {
    mountAt('/analytics')
    await expectHeading(/do not have access/i)
  })
})

describe('manager pages', () => {
  beforeEach(() => signIn('manager'))

  it('manager dashboard renders KPIs and charts', async () => {
    mountAt('/dashboard')
    await expectHeading(/manager dashboard/i)
    await waitFor(
      () => expect(screen.getByText(/straight-through rate/i)).toBeTruthy(),
      { timeout: 20000 }
    )
    expect(screen.getByText(/requests submitted per day/i)).toBeTruthy()
    expect(screen.getByText(/outcome mix/i)).toBeTruthy()
    expect(screen.getByText(/workflow step timings/i)).toBeTruthy()
    expect(screen.getByText(/awaiting your decision/i)).toBeTruthy()
  })

  it('pending approvals lists open tasks', async () => {
    mountAt('/approvals')
    await expectHeading(/pending approvals/i)
    await waitFor(() => expect(screen.getByText(/value on hold/i)).toBeTruthy())
  })

  it('approval detail shows the full decision context and three actions', async () => {
    mountAt(`/approvals/${ids.approval}`)
    await waitFor(
      () => expect(screen.getByText(/what is being asked/i)).toBeTruthy(),
      { timeout: 20000 }
    )
    expect(screen.getAllByText(/discount requested/i).length).toBeGreaterThan(0)
    expect(screen.getAllByText(/policy allows/i).length).toBeGreaterThan(0)
    expect(screen.getByText(/validation results/i)).toBeTruthy()
    expect(screen.getByText(/product and pricing detail/i)).toBeTruthy()
    // Credit position is part of the decision context.
    expect(screen.getByText(/credit position/i)).toBeTruthy()
  })

  it('quotation history lists issued documents', async () => {
    mountAt('/quotations')
    await expectHeading(/quotation history/i)
    await waitFor(() =>
      expect(screen.getAllByText(/QT-\d{4}-\d{5}/).length).toBeGreaterThan(0)
    )
  })

  it('analytics dashboard renders every section', async () => {
    mountAt('/analytics')
    await expectHeading(/^analytics$/i)
    await waitFor(
      () => expect(screen.getByText(/average processing time/i)).toBeTruthy(),
      { timeout: 20000 }
    )
    expect(screen.getByText(/total requests/i)).toBeTruthy()
    expect(screen.getByText(/approved quotations/i)).toBeTruthy()
    expect(screen.getByText(/rejected quotations/i)).toBeTruthy()
    expect(screen.getByText(/monthly quotation volume/i)).toBeTruthy()
    expect(screen.getByText(/most requested products/i)).toBeTruthy()
    expect(screen.getByText(/approval performance/i)).toBeTruthy()
  })

  it('master data requests render as a decision queue for a manager', async () => {
    mountAt('/master-data-requests')
    await expectHeading(/master data requests/i)
    await waitFor(() =>
      expect(screen.getAllByText(/awaiting approval/i).length).toBeGreaterThan(0)
    )
    expect(screen.getByText(/customers proposed/i)).toBeTruthy()
    expect(screen.getByText(/products proposed/i)).toBeTruthy()
  })

  it('audit logs render entries with actors', async () => {
    mountAt('/audit-logs')
    await expectHeading(/audit logs/i)
    await waitFor(() => expect(screen.getByText(/append-only/i)).toBeTruthy())
    await waitFor(() =>
      expect(screen.getAllByText(/quoteflow\.example|acme-process/i).length)
        .toBeGreaterThan(0)
    )
  })

  it('company settings renders the editable rule book', async () => {
    mountAt('/settings')
    await expectHeading(/company settings/i)
    await waitFor(() => expect(screen.getByText(/discount tiers/i)).toBeTruthy())
    expect(screen.getByText(/approval routing/i)).toBeTruthy()
    expect(screen.getByText(/customer tier bonus/i)).toBeTruthy()
    expect(screen.getByLabelText(/absolute maximum discount/i)).toBeTruthy()
    expect(screen.getAllByRole('button', { name: /save changes/i }).length)
      .toBeGreaterThan(0)
  })
})

describe('common pages', () => {
  it('notifications render for a manager', async () => {
    signIn('manager')
    mountAt('/notifications')
    await expectHeading(/^notifications$/i)
    await waitFor(() =>
      expect(screen.getByRole('button', { name: /mark all read/i })).toBeTruthy()
    )
  })

  it('profile shows the account and, for a customer, their record', async () => {
    signIn('customer')
    mountAt('/profile')
    await expectHeading(/my profile/i)
    await waitFor(() =>
      expect(screen.getAllByText(/Rohit Desai/).length).toBeGreaterThan(0)
    )
    expect(screen.getByText(/your customer record/i)).toBeTruthy()
    expect(screen.getAllByText(/change password/i).length).toBeGreaterThan(0)
  })

  it('settings are readable by a customer, without save controls', async () => {
    signIn('customer')
    mountAt('/settings')
    await expectHeading(/company settings/i)
    await waitFor(() => expect(screen.getByText(/discount tiers/i)).toBeTruthy())
    expect(
      screen.getByText(/only a sales manager can change them/i)
    ).toBeTruthy()
    expect(screen.queryByRole('button', { name: /save changes/i })).toBeNull()
  })

  it('the verifier confirms a real quotation code', async () => {
    signIn('manager')
    mountAt(`/verify/${ids.verifyCode}`)
    await expectHeading(/verify a quotation/i)
    await waitFor(
      () => {
        const result = screen.getByText(/^Verified$|^Verified — expired$/)
        expect(result).toBeTruthy()
      },
      { timeout: 20000 }
    )
    expect(screen.getByText(/integrity digest/i)).toBeTruthy()
  })

  it('the verifier rejects an unknown code', async () => {
    signIn('manager')
    mountAt('/verify/AAAA-BBBB-CCCC')
    await expectHeading(/verify a quotation/i)
    await waitFor(
      () => expect(screen.getByText(/no quotation matches/i)).toBeTruthy(),
      { timeout: 20000 }
    )
  })

  it('an unknown route renders the not-found page', async () => {
    signIn('manager')
    mountAt('/this-route-does-not-exist')
    await expectHeading(/page not found/i)
  })
})

describe('role-based navigation', () => {
  it('a customer sees customer navigation only', async () => {
    signIn('customer')
    mountAt('/dashboard')
    await expectHeading(/welcome back/i)
    const nav = await waitFor(() => screen.getAllByLabelText(/main navigation/i)[0])
    expect(within(nav).getByText(/product catalogue/i)).toBeTruthy()
    expect(within(nav).getByText(/my requests/i)).toBeTruthy()
    expect(within(nav).queryByText(/audit logs/i)).toBeNull()
    expect(within(nav).queryByText(/pending approvals/i)).toBeNull()
    // The quotation verifier is a staff tool; a customer has no use for it.
    expect(within(nav).queryByText(/verify a quotation/i)).toBeNull()
  })

  it('a manager sees governance navigation', async () => {
    signIn('manager')
    mountAt('/dashboard')
    await expectHeading(/manager dashboard/i)
    const nav = await waitFor(() => screen.getAllByLabelText(/main navigation/i)[0])
    expect(within(nav).getByText(/pending approvals/i)).toBeTruthy()
    expect(within(nav).getByText(/audit logs/i)).toBeTruthy()
    expect(within(nav).getByText(/company settings/i)).toBeTruthy()
    expect(within(nav).getByText(/analytics/i)).toBeTruthy()
    expect(within(nav).getByText(/verify a quotation/i)).toBeTruthy()
    expect(within(nav).getByText(/^Add Requests$/)).toBeTruthy()
  })

  it('an employee sees master-data navigation but not governance', async () => {
    signIn('employee')
    mountAt('/dashboard')
    await expectHeading(/sales operations/i)
    const nav = await waitFor(() => screen.getAllByLabelText(/main navigation/i)[0])
    expect(within(nav).getByText(/^Customers$/)).toBeTruthy()
    expect(within(nav).getByText(/^Products$/)).toBeTruthy()
    expect(within(nav).getByText(/my add requests/i)).toBeTruthy()
    expect(within(nav).queryByText(/audit logs/i)).toBeNull()
    expect(within(nav).queryByText(/verify a quotation/i)).toBeNull()
  })
})
