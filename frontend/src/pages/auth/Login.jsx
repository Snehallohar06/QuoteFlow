import { useState } from 'react'
import { Link, useLocation, useNavigate } from 'react-router-dom'
import { AlertCircle, ArrowRight, Eye, EyeOff, Info } from 'lucide-react'

import { useAuth } from '../../context/AuthContext'
import { Button } from '../../components/ui/Button'
import { Input } from '../../components/ui/Field'
import { AuthLayout } from './AuthLayout'

/**
 * The seeded demo accounts.
 *
 * Shown only in development, as a convenience for reviewing the three role
 * experiences without having to look up credentials. The password is the one
 * `app.db.seed` sets, so this leaks nothing that is not already in the repo.
 */
const DEMO_ACCOUNTS = [
  {
    role: 'Sales Manager',
    email: 'manager@quoteflow.example',
    note: 'Approvals, analytics, settings',
  },
  {
    role: 'Sales Employee',
    email: 'sales1@quoteflow.example',
    note: 'Customers, products, queue',
  },
  {
    role: 'Customer (Gold)',
    email: 'rohit.desai@acme-process.example',
    note: 'Catalogue, requests, quotations',
  },
]
const DEMO_PASSWORD = 'QuoteFlow@2026'

export function Login() {
  const { login, sessionExpired, clearSessionExpired } = useAuth()
  const navigate = useNavigate()
  const location = useLocation()

  const [form, setForm] = useState({ email: '', password: '' })
  const [errors, setErrors] = useState({})
  const [formError, setFormError] = useState(null)
  const [showPassword, setShowPassword] = useState(false)
  const [pending, setPending] = useState(false)

  const destination = location.state?.from?.pathname ?? '/dashboard'

  function validate() {
    const next = {}
    if (!form.email.trim()) next.email = 'Enter your email address.'
    else if (!/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(form.email.trim()))
      next.email = 'Enter a valid email address.'
    if (!form.password) next.password = 'Enter your password.'
    setErrors(next)
    return Object.keys(next).length === 0
  }

  async function onSubmit(event) {
    event.preventDefault()
    setFormError(null)
    clearSessionExpired()
    if (!validate()) return

    setPending(true)
    try {
      await login(form.email.trim(), form.password)
      navigate(destination, { replace: true })
    } catch (error) {
      // A wrong password is the expected case here, so it reads inline on the
      // form rather than as a toast that disappears.
      setFormError(error.message)
    } finally {
      setPending(false)
    }
  }

  function fillDemoAccount(email) {
    setForm({ email, password: DEMO_PASSWORD })
    setErrors({})
    setFormError(null)
  }

  return (
    <AuthLayout
      title="Sign in"
      description="Access your quotation requests, approvals and reports."
      footer={
        <p className="text-center text-[13.5px] text-slate-500">
          New customer?{' '}
          <Link
            to="/register"
            className="font-medium text-brand-700 underline-offset-2 hover:underline"
          >
            Create an account
          </Link>
        </p>
      }
    >
      {sessionExpired ? (
        <div
          className="mb-4 flex items-start gap-2.5 rounded-md border border-amber-200 bg-amber-50 px-3.5 py-3"
          role="status"
        >
          <Info size={15} className="mt-0.5 shrink-0 text-amber-600" aria-hidden="true" />
          <p className="text-[13px] leading-snug text-amber-900">
            Your session expired. Please sign in again to continue.
          </p>
        </div>
      ) : null}

      {formError ? (
        <div
          className="mb-4 flex items-start gap-2.5 rounded-md border border-rose-200 bg-rose-50 px-3.5 py-3"
          role="alert"
        >
          <AlertCircle
            size={15}
            className="mt-0.5 shrink-0 text-rose-600"
            aria-hidden="true"
          />
          <p className="text-[13px] leading-snug text-rose-800">{formError}</p>
        </div>
      ) : null}

      <form onSubmit={onSubmit} noValidate className="space-y-4">
        <Input
          label="Email address"
          type="email"
          name="email"
          autoComplete="username"
          placeholder="you@company.com"
          value={form.email}
          error={errors.email}
          required
          onChange={(event) => setForm({ ...form, email: event.target.value })}
        />

        <div>
          <div className="relative">
            <Input
              label="Password"
              type={showPassword ? 'text' : 'password'}
              name="password"
              autoComplete="current-password"
              placeholder="••••••••"
              value={form.password}
              error={errors.password}
              required
              onChange={(event) => setForm({ ...form, password: event.target.value })}
            />
            <button
              type="button"
              onClick={() => setShowPassword((value) => !value)}
              className="absolute right-2.5 top-[30px] rounded p-1 text-slate-400 transition hover:bg-slate-100 hover:text-slate-600"
              aria-label={showPassword ? 'Hide password' : 'Show password'}
            >
              {showPassword ? <EyeOff size={15} /> : <Eye size={15} />}
            </button>
          </div>
        </div>

        <Button
          type="submit"
          size="lg"
          loading={pending}
          iconRight={ArrowRight}
          className="w-full justify-center"
        >
          Sign in
        </Button>
      </form>

      {import.meta.env.DEV ? (
        <div className="mt-7 rounded-md border border-slate-200 bg-slate-50 p-3.5">
          <p className="text-[12px] font-semibold uppercase tracking-wide text-slate-500">
            Demo accounts
          </p>
          <p className="mt-1 text-[12px] text-slate-500">
            Seeded by{' '}
            <code className="font-mono text-[11.5px] text-slate-600">
              python -m app.db.seed
            </code>
            . Click to fill the form.
          </p>
          <div className="mt-2.5 space-y-1.5">
            {DEMO_ACCOUNTS.map((account) => (
              <button
                key={account.email}
                type="button"
                onClick={() => fillDemoAccount(account.email)}
                className="flex w-full items-center justify-between gap-3 rounded border border-slate-200 bg-white px-2.5 py-2 text-left transition hover:border-brand-300 hover:bg-brand-50/50"
              >
                <span className="min-w-0">
                  <span className="block text-[12.5px] font-medium text-slate-800">
                    {account.role}
                  </span>
                  <span className="block truncate font-mono text-[11px] text-slate-500">
                    {account.email}
                  </span>
                </span>
                <span className="shrink-0 text-[11px] text-slate-400">
                  {account.note}
                </span>
              </button>
            ))}
          </div>
        </div>
      ) : null}
    </AuthLayout>
  )
}
