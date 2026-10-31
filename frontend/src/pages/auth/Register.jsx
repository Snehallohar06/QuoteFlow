import { useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { AlertCircle, ArrowRight, Eye, EyeOff } from 'lucide-react'

import { useAuth } from '../../context/AuthContext'
import { useToast } from '../../context/ToastContext'
import { Button } from '../../components/ui/Button'
import { Input } from '../../components/ui/Field'
import { AuthLayout } from './AuthLayout'

const EMPTY = {
  full_name: '',
  company_name: '',
  email: '',
  phone: '',
  password: '',
  confirm_password: '',
  address_line1: '',
  city: '',
  state: '',
  postal_code: '',
  tax_id: '',
}

export function Register() {
  const { register } = useAuth()
  const toast = useToast()
  const navigate = useNavigate()

  const [form, setForm] = useState(EMPTY)
  const [errors, setErrors] = useState({})
  const [formError, setFormError] = useState(null)
  const [showPassword, setShowPassword] = useState(false)
  const [pending, setPending] = useState(false)

  function set(field, value) {
    setForm((current) => ({ ...current, [field]: value }))
    // Clear a field's error as soon as the user edits it.
    if (errors[field]) {
      setErrors((current) => {
        const next = { ...current }
        delete next[field]
        return next
      })
    }
  }

  /** Mirrors the backend's RegisterRequest constraints, so a valid form submits. */
  function validate() {
    const next = {}

    if (!form.full_name.trim()) next.full_name = 'Enter your full name.'
    else if (form.full_name.trim().length < 2) next.full_name = 'That name is too short.'

    if (!form.company_name.trim()) next.company_name = 'Enter your company name.'
    else if (form.company_name.trim().length < 2)
      next.company_name = 'That company name is too short.'

    if (!form.email.trim()) next.email = 'Enter an email address.'
    else if (!/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(form.email.trim()))
      next.email = 'Enter a valid email address.'

    if (!form.phone.trim()) next.phone = 'Enter a contact number.'
    else if (form.phone.trim().length < 6) next.phone = 'That number looks too short.'

    if (!form.password) next.password = 'Choose a password.'
    else if (form.password.length < 8)
      next.password = 'Use at least 8 characters.'

    if (!form.confirm_password) next.confirm_password = 'Re-enter your password.'
    else if (form.confirm_password !== form.password)
      next.confirm_password = 'The two passwords do not match.'

    setErrors(next)
    return Object.keys(next).length === 0
  }

  async function onSubmit(event) {
    event.preventDefault()
    setFormError(null)
    if (!validate()) return

    setPending(true)
    try {
      // confirm_password is a client-side check only; it is not sent.
      const { confirm_password: _ignored, ...payload } = form
      const user = await register({
        ...payload,
        full_name: payload.full_name.trim(),
        company_name: payload.company_name.trim(),
        email: payload.email.trim().toLowerCase(),
      })
      toast.success(
        'Account created',
        `Welcome, ${user.full_name}. Your customer record is ready.`
      )
      navigate('/dashboard', { replace: true })
    } catch (error) {
      // Field-level detail from the API's 422 response, when present.
      const fieldErrors = error.fieldErrors ?? {}
      if (Object.keys(fieldErrors).length > 0) {
        setErrors(fieldErrors)
        setFormError('Please correct the highlighted fields.')
      } else {
        setFormError(error.message)
      }
    } finally {
      setPending(false)
    }
  }

  return (
    <AuthLayout
      title="Create a customer account"
      description="Registering also creates your customer record, so you can submit quotation requests straight away."
      footer={
        <p className="text-center text-[13.5px] text-slate-500">
          Already registered?{' '}
          <Link
            to="/login"
            className="font-medium text-brand-700 underline-offset-2 hover:underline"
          >
            Sign in
          </Link>
        </p>
      }
    >
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
        <div className="grid gap-4 sm:grid-cols-2">
          <Input
            label="Full name"
            value={form.full_name}
            error={errors.full_name}
            required
            autoComplete="name"
            onChange={(event) => set('full_name', event.target.value)}
          />
          <Input
            label="Company name"
            value={form.company_name}
            error={errors.company_name}
            required
            autoComplete="organization"
            onChange={(event) => set('company_name', event.target.value)}
          />
        </div>

        <div className="grid gap-4 sm:grid-cols-2">
          <Input
            label="Email address"
            type="email"
            value={form.email}
            error={errors.email}
            required
            autoComplete="username"
            placeholder="you@company.com"
            onChange={(event) => set('email', event.target.value)}
          />
          <Input
            label="Contact number"
            value={form.phone}
            error={errors.phone}
            required
            autoComplete="tel"
            placeholder="+91 98765 43210"
            onChange={(event) => set('phone', event.target.value)}
          />
        </div>

        <div className="grid gap-4 sm:grid-cols-2">
          <div className="relative">
            <Input
              label="Password"
              type={showPassword ? 'text' : 'password'}
              value={form.password}
              error={errors.password}
              hint={errors.password ? undefined : 'At least 8 characters'}
              required
              autoComplete="new-password"
              onChange={(event) => set('password', event.target.value)}
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
          <Input
            label="Confirm password"
            type={showPassword ? 'text' : 'password'}
            value={form.confirm_password}
            error={errors.confirm_password}
            required
            autoComplete="new-password"
            onChange={(event) => set('confirm_password', event.target.value)}
          />
        </div>

        <fieldset className="rounded-md border border-slate-200 px-3.5 pb-3.5 pt-2">
          <legend className="px-1 text-[12px] font-medium text-slate-500">
            Billing address — optional, printed on your quotations
          </legend>
          <div className="space-y-3">
            <Input
              label="Address"
              value={form.address_line1}
              error={errors.address_line1}
              placeholder="Unit 7, Industrial Estate"
              onChange={(event) => set('address_line1', event.target.value)}
            />
            <div className="grid gap-3 sm:grid-cols-3">
              <Input
                label="City"
                value={form.city}
                onChange={(event) => set('city', event.target.value)}
              />
              <Input
                label="State"
                value={form.state}
                onChange={(event) => set('state', event.target.value)}
              />
              <Input
                label="Postal code"
                value={form.postal_code}
                onChange={(event) => set('postal_code', event.target.value)}
              />
            </div>
            <Input
              label="Tax ID / GSTIN"
              value={form.tax_id}
              error={errors.tax_id}
              onChange={(event) => set('tax_id', event.target.value)}
            />
          </div>
        </fieldset>

        <Button
          type="submit"
          size="lg"
          loading={pending}
          iconRight={ArrowRight}
          className="w-full justify-center"
        >
          Create account
        </Button>
      </form>
    </AuthLayout>
  )
}
